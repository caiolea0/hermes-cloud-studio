"""F.7 C3 — Cobaia dashboard API smoke tests (8 tests, MOCK-DRIVEN).

Validates:
  GET  /api/linkedin/cobaia/status      → 200 exists=False when not started
  POST /api/linkedin/cobaia/start-warmup → 200 phase=lurking day=0
  POST /api/linkedin/cobaia/start-warmup → 409 duplicate
  GET  /api/linkedin/cobaia/metrics      → 200 has kpis + daily keys
  GET  /api/linkedin/cobaia/timeline     → 200 exists=False when not started
  GET  /api/linkedin/cobaia/timeline     → 200 exists=True after start
  POST /api/linkedin/cobaia/emergency-stop → 200 phase=paused emergency=True
  POST /api/linkedin/cobaia/resume        → 200 phase returned (lurking/ramp/normal)
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "cobaia_smoke.db"


@pytest.fixture
def cobaia_cfg():
    from linkedin.config import CobaiaConfig
    return CobaiaConfig(
        account_handle="smoke-cobaia",
        warmup_days=14,
        lurking_days=7,
        weekends_enabled=True,  # always allowed in tests
        working_hours_start="00:00",
        working_hours_end="23:59",
        timezone="America/Cuiaba",
        auto_pause_consecutive_errors=3,
    )


@pytest.fixture
def client(tmp_db, cobaia_cfg):
    from linkedin.cobaia_warmup import CobaiaWarmupManager
    mgr = CobaiaWarmupManager(cfg=cobaia_cfg, db_path=tmp_db)

    def _mock_manager():
        return CobaiaWarmupManager(cfg=cobaia_cfg, db_path=tmp_db)

    with patch("api.cobaia._manager", _mock_manager):
        from server import app
        yield TestClient(app), mgr


@pytest.fixture
def auth_headers():
    from core.state import AUTH_TOKEN
    return {"X-Hermes-Token": AUTH_TOKEN, "Content-Type": "application/json"}


# ── Tests ───────────────────────────────────────────────────────────────────

def test_status_not_started(client, auth_headers):
    """GET /status → 200, exists=False when warmup not yet started."""
    c, _ = client
    r = c.get("/api/linkedin/cobaia/status", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is False


def test_start_warmup_returns_lurking(client, auth_headers):
    """POST /start-warmup → 200, phase=lurking, day=0."""
    c, _ = client
    r = c.post("/api/linkedin/cobaia/start-warmup", headers=auth_headers, json={})
    assert r.status_code == 200
    data = r.json()
    assert data["phase"] == "lurking"
    assert data["current_day"] == 0
    assert data["exists"] is True


def test_start_warmup_duplicate_409(client, auth_headers):
    """POST /start-warmup twice → 409 on duplicate."""
    c, _ = client
    c.post("/api/linkedin/cobaia/start-warmup", headers=auth_headers, json={})
    r = c.post("/api/linkedin/cobaia/start-warmup", headers=auth_headers, json={})
    assert r.status_code == 409


def test_metrics_endpoint_structure(client, auth_headers):
    """GET /metrics → 200, response has kpis + daily + totals keys."""
    c, _ = client
    r = c.get("/api/linkedin/cobaia/metrics?days=7", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "kpis" in data
    assert "daily" in data
    assert "totals" in data
    assert "reply_rate" in data["kpis"]
    assert "accept_rate" in data["kpis"]
    assert "view_to_connect" in data["kpis"]


def test_timeline_not_started(client, auth_headers):
    """GET /timeline → 200, exists=False when warmup not started."""
    c, _ = client
    r = c.get("/api/linkedin/cobaia/timeline", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is False


def test_timeline_after_start(client, auth_headers):
    """GET /timeline → 200, exists=True with days list after start-warmup."""
    c, _ = client
    c.post("/api/linkedin/cobaia/start-warmup", headers=auth_headers, json={})
    r = c.get("/api/linkedin/cobaia/timeline", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is True
    assert isinstance(data["days"], list)
    assert len(data["days"]) > 0
    day0 = data["days"][0]
    assert "day" in day0
    assert "phase" in day0


def test_emergency_stop(client, auth_headers):
    """POST /emergency-stop → 200, phase=paused, emergency=True."""
    c, _ = client
    c.post("/api/linkedin/cobaia/start-warmup", headers=auth_headers, json={})
    r = c.post("/api/linkedin/cobaia/emergency-stop", headers=auth_headers, json={"reason": "test"})
    assert r.status_code == 200
    data = r.json()
    assert data["phase"] == "paused"
    assert data.get("emergency") is True


def test_resume_after_emergency_stop(client, auth_headers):
    """POST /resume after emergency-stop → 200, phase not paused."""
    c, _ = client
    c.post("/api/linkedin/cobaia/start-warmup", headers=auth_headers, json={})
    c.post("/api/linkedin/cobaia/emergency-stop", headers=auth_headers, json={})
    r = c.post("/api/linkedin/cobaia/resume", headers=auth_headers, json={})
    assert r.status_code == 200
    data = r.json()
    assert data["phase"] != "paused"
    assert data["phase"] in ("lurking", "ramp", "normal")
