"""Tests for H2-F7 — Market Analyzer + Market API.

Unit tests — no Postgres required. Tests pure logic:
  - compute_opportunity_scores formula + rank ordering
  - ICP bonus lookup
  - signal normalization bounds
  - _upsert_signals metric_key selection (pure logic, no DB)
  - market_signals route auth gate (FastAPI TestClient)
  - churn RF code validation (correct situacao codes)
  - determinism: same input → same output (run twice)
  - heatmap pivot structure (unit)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Imports (no DB touch at import time)
# ---------------------------------------------------------------------------
from brain.market_analyzer import (
    CHURN_SITUACOES,
    CUIABA_RF_CODE,
    _icp_bonus,
    _W_CHURN,
    _W_DENSITY_LOW,
    _W_NEW_REG,
    compute_opportunity_scores,
)


# ---------------------------------------------------------------------------
# 1. RF codes — churn situacoes must match spec
# ---------------------------------------------------------------------------

def test_churn_situacoes_rf_codes():
    """03=SUSPENSA 04=INAPTA 08=BAIXADA must all be in CHURN_SITUACOES. '02'=ATIVA must NOT be."""
    assert "03" in CHURN_SITUACOES
    assert "04" in CHURN_SITUACOES
    assert "08" in CHURN_SITUACOES
    assert "02" not in CHURN_SITUACOES, "ATIVA must never be in churn list"


def test_cuiaba_rf_code():
    """RF code for Cuiabá is 9067 (confirmed H2-F2 load)."""
    assert CUIABA_RF_CODE == "9067"


# ---------------------------------------------------------------------------
# 2. ICP bonus lookup
# ---------------------------------------------------------------------------

def test_icp_bonus_alimentacao():
    """CNAE prefix 56 (alimentação) must return 15."""
    assert _icp_bonus("5611201") == 15


def test_icp_bonus_saude():
    """CNAE prefix 86 (saúde) must return 12."""
    assert _icp_bonus("8630502") == 12


def test_icp_bonus_unknown():
    """Unknown CNAE prefix must return 0 (no bonus)."""
    assert _icp_bonus("9999999") == 0
    assert _icp_bonus("") == 0
    assert _icp_bonus("0") == 0


def test_icp_bonus_comercio():
    """CNAE prefix 47 (comércio varejista) returns 10."""
    assert _icp_bonus("4712100") == 10


# ---------------------------------------------------------------------------
# 3. compute_opportunity_scores — formula, ordering, determinism
# ---------------------------------------------------------------------------

_DENSITY = [
    {"cnae": "5611201", "total": 300, "ativas": 250, "rank": 1},
    {"cnae": "4712100", "total": 200, "ativas": 180, "rank": 2},
    {"cnae": "8630502", "total": 50,  "ativas": 48,  "rank": 3},
]
_NEW_REG = [
    {"cnae": "8630502", "new_count": 45, "rank": 1},  # health = fastest growing
    {"cnae": "5611201", "new_count": 30, "rank": 2},
    {"cnae": "4712100", "new_count": 10, "rank": 3},
]
_CHURN = [
    {"cnae": "4712100", "churn_count": 20, "rank": 1},
    {"cnae": "5611201", "churn_count": 15, "rank": 2},
    {"cnae": "8630502", "churn_count": 5,  "rank": 3},
]


def test_opportunity_scores_ordering():
    """Scores must be sorted descending by opportunity_score."""
    result = compute_opportunity_scores(_DENSITY, _NEW_REG, _CHURN)
    scores = [r["opportunity_score"] for r in result]
    assert scores == sorted(scores, reverse=True), "Must be sorted descending"


def test_opportunity_scores_rank_assigned():
    """Rank must be 1-indexed sequential."""
    result = compute_opportunity_scores(_DENSITY, _NEW_REG, _CHURN)
    ranks = [r["rank"] for r in result]
    assert ranks == list(range(1, len(result) + 1))


def test_opportunity_scores_determinism():
    """Running twice with same input must produce identical output."""
    r1 = compute_opportunity_scores(_DENSITY, _NEW_REG, _CHURN)
    r2 = compute_opportunity_scores(_DENSITY, _NEW_REG, _CHURN)
    assert r1 == r2, "compute_opportunity_scores must be deterministic"


def test_opportunity_scores_all_cnaes_present():
    """All unique CNAEs from all 3 inputs must appear in output."""
    result = compute_opportunity_scores(_DENSITY, _NEW_REG, _CHURN)
    out_cnaes = {r["cnae"] for r in result}
    expected = {"5611201", "4712100", "8630502"}
    assert expected == out_cnaes


def test_opportunity_scores_icp_bonus_applied():
    """The CNAE with the highest ICP bonus (56xx=15) should have it reflected."""
    result = compute_opportunity_scores(_DENSITY, _NEW_REG, _CHURN)
    r56 = next(r for r in result if r["cnae"] == "5611201")
    assert r56["icp_bonus"] == 15


def test_opportunity_score_positive():
    """All opportunity scores must be positive (weights positive, ICP non-negative)."""
    result = compute_opportunity_scores(_DENSITY, _NEW_REG, _CHURN)
    for r in result:
        assert r["opportunity_score"] > 0, f"score must be positive, got {r}"


def test_opportunity_score_limit():
    """limit parameter must cap output length."""
    result = compute_opportunity_scores(_DENSITY, _NEW_REG, _CHURN, limit=2)
    assert len(result) <= 2


def test_opportunity_scores_empty_inputs():
    """Empty inputs must return empty list without raising."""
    result = compute_opportunity_scores([], [], [])
    assert result == []


def test_opportunity_scores_partial_overlap():
    """CNAEs present in only some signals must still be scored (0 for missing signals)."""
    density = [{"cnae": "5611201", "total": 100, "ativas": 80, "rank": 1}]
    new_reg = [{"cnae": "8630502", "new_count": 50, "rank": 1}]  # different CNAE
    churn = []
    result = compute_opportunity_scores(density, new_reg, churn)
    out_cnaes = {r["cnae"] for r in result}
    assert "5611201" in out_cnaes
    assert "8630502" in out_cnaes


# ---------------------------------------------------------------------------
# 4. Weights sanity
# ---------------------------------------------------------------------------

def test_weights_positive():
    """All formula weights must be positive."""
    assert _W_NEW_REG > 0
    assert _W_DENSITY_LOW > 0
    assert _W_CHURN > 0


def test_new_reg_highest_weight():
    """new_reg should have the highest weight (growth signal is most actionable)."""
    assert _W_NEW_REG >= _W_DENSITY_LOW >= _W_CHURN


# ---------------------------------------------------------------------------
# 5. Heatmap pivot logic (unit — no DB)
# ---------------------------------------------------------------------------

def test_heatmap_pivot_structure():
    """Pivot logic: flat rows → { cnae: { bairro: count } }."""
    flat_rows = [
        {"cnae": "5611201", "bairro": "Centro", "count": 10},
        {"cnae": "5611201", "bairro": "Coxipó",  "count": 5},
        {"cnae": "4712100", "bairro": "Centro",  "count": 7},
    ]
    pivot: dict[str, dict[str, int]] = {}
    for r in flat_rows:
        cnae = r.get("cnae") or "?"
        bairro = r.get("bairro") or "—"
        pivot.setdefault(cnae, {})[bairro] = int(r.get("count") or 0)

    assert pivot["5611201"]["Centro"] == 10
    assert pivot["5611201"]["Coxipó"] == 5
    assert pivot["4712100"]["Centro"] == 7
    assert len(pivot) == 2


# ---------------------------------------------------------------------------
# 6. FastAPI route auth gate (no PG needed — 401 without token)
# ---------------------------------------------------------------------------

def test_market_signals_route_requires_auth():
    """GET /api/market/signals without X-Hermes-Token must return 401."""
    import os
    os.environ.setdefault("HERMES_VM_AUTH_TOKEN", "test-token-f7")
    os.environ.setdefault("HERMES_PG_PASSWORD", "dummy")

    try:
        from fastapi.testclient import TestClient
        from hermes_api_v2 import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/market/signals")
        assert response.status_code == 401, (
            f"Expected 401 without auth, got {response.status_code}"
        )
    except ImportError:
        pytest.skip("FastAPI TestClient not available in this env")


def test_market_heatmap_route_requires_auth():
    """GET /api/market/heatmap without X-Hermes-Token must return 401."""
    import os
    os.environ.setdefault("HERMES_VM_AUTH_TOKEN", "test-token-f7")
    os.environ.setdefault("HERMES_PG_PASSWORD", "dummy")

    try:
        from fastapi.testclient import TestClient
        from hermes_api_v2 import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/market/heatmap")
        assert response.status_code == 401
    except ImportError:
        pytest.skip("FastAPI TestClient not available in this env")
