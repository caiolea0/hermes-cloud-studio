"""UX-RM-F3-B — ICP Profile + Launch Preflight tests.

Tests:
  1. test_icp_profile_migration_idempotent
  2. test_icp_get_profile_returns_data
  3. test_icp_post_profile_upserts
  4. test_icp_presets_returns_3_templates
  5. test_wizard_icp_step_file_exists
  6. test_wizard_launch_step_file_exists

Run:
  pytest tests/test_ux_rm_f3b_icp_launch.py -v
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent
STEPS = ROOT / "dashboard" / "components" / "onboarding_steps"


# ── T1: migration idempotent ──────────────────────────────────────────────────

def test_icp_profile_migration_idempotent():
    """Running migration SQL twice must not raise; table + default row OK."""
    sql_path = ROOT / "migrations" / "2026_06_icp_profile.sql"
    assert sql_path.exists(), f"Migration file missing: {sql_path}"
    sql = sql_path.read_text(encoding="utf-8")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        conn.executescript(sql)
        conn.commit()
        # Second run — idempotent
        conn.executescript(sql)
        conn.commit()
        # Table must exist
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='icp_profile'"
        ).fetchone()
        assert row is not None, "icp_profile table not created"
        # Insert default owner row
        conn.execute(
            "INSERT OR IGNORE INTO icp_profile (user_id) VALUES ('owner')"
        )
        conn.commit()
        row2 = conn.execute(
            "SELECT * FROM icp_profile WHERE user_id='owner'"
        ).fetchone()
        assert row2 is not None
        assert row2["max_prospects_per_day"] == 5
    finally:
        conn.close()


# ── T2: GET /api/icp/profile returns data ────────────────────────────────────

def test_icp_get_profile_returns_data():
    """GET /api/icp/profile must return {data: ...}."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.icp import router

    with patch("core.icp_store.get_current_user_profile", return_value=None):
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        r = client.get("/api/icp/profile")
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert body["data"] == {}


def test_icp_get_profile_returns_saved_data():
    """GET /api/icp/profile returns saved profile when it exists."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.icp import router

    saved = {"industries": ["Software"], "job_titles": ["Founder"], "max_prospects_per_day": 5}
    with patch("core.icp_store.get_current_user_profile", return_value=saved):
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        r = client.get("/api/icp/profile")
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["industries"] == ["Software"]


# ── T3: POST /api/icp/profile upserts ────────────────────────────────────────

def test_icp_post_profile_upserts():
    """POST /api/icp/profile must return {status: 'saved'} and call upsert."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.icp import router

    with patch("core.icp_store.upsert_profile") as mock_upsert:
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        payload = {
            "industries": ["SaaS", "Software"],
            "job_titles": ["Founder", "CEO"],
            "states": ["MT"],
            "countries": ["BR"],
            "max_prospects_per_day": 5,
        }
        r = client.post("/api/icp/profile", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "saved"
        mock_upsert.assert_called_once()
        call_data = mock_upsert.call_args[0][0]
        assert call_data["industries"] == ["SaaS", "Software"]
        assert call_data["max_prospects_per_day"] == 5


# ── T4: GET /api/icp/presets returns 3 templates ─────────────────────────────

def test_icp_presets_returns_3_templates():
    """GET /api/icp/presets must return exactly 3 preset templates."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.icp import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    r = client.get("/api/icp/presets")
    assert r.status_code == 200
    body = r.json()
    assert "presets" in body
    presets = body["presets"]
    assert len(presets) == 3, f"Expected 3 presets, got {len(presets)}"
    ids = {p["id"] for p in presets}
    assert "cuiaba_saas_founders" in ids
    assert "mt_marketing_agencies" in ids
    assert "br_growth_directors" in ids
    # Each preset must have id, name, icp with required fields
    for p in presets:
        assert "id" in p
        assert "name" in p
        assert "icp" in p
        icp = p["icp"]
        assert "max_prospects_per_day" in icp
        assert "countries" in icp
        assert icp["max_prospects_per_day"] <= 5  # safe limit for cobaia


# ── T5: icp.js step file exists ──────────────────────────────────────────────

def test_wizard_icp_step_file_exists():
    """dashboard/components/onboarding_steps/icp.js must exist."""
    path = STEPS / "icp.js"
    assert path.exists(), f"Missing ICP step file: {path}"
    content = path.read_text(encoding="utf-8")
    # Must register with HermesOnboardingWizard
    assert "HermesOnboardingWizard" in content, "Step must reference HermesOnboardingWizard"
    assert "register" in content, "Step must call register()"
    # Must expose loadPreset
    assert "_OnboardingIcpLoadPreset" in content, "Must expose _OnboardingIcpLoadPreset"


# ── T6: launch.js step file exists ───────────────────────────────────────────

def test_wizard_launch_step_file_exists():
    """dashboard/components/onboarding_steps/launch.js must exist."""
    path = STEPS / "launch.js"
    assert path.exists(), f"Missing launch step file: {path}"
    content = path.read_text(encoding="utf-8")
    assert "HermesOnboardingWizard" in content, "Step must reference HermesOnboardingWizard"
    assert "register" in content, "Step must call register()"
    # Must expose warmup starter
    assert "_HermesStartWarmup" in content, "Must expose _HermesStartWarmup"
    # Must check hermes health
    assert "hermes" in content.lower(), "Must include hermes health check"
