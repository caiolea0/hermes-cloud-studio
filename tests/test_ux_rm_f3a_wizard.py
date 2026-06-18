"""UX-RM-F3-A — Onboarding Wizard tests.

Tests:
  1. test_onboarding_state_migration_idempotent
  2. test_onboarding_state_endpoint_get_returns_data
  3. test_onboarding_state_endpoint_post_upserts
  4. test_onboarding_state_endpoint_complete_marks_done
  5. test_wizard_files_exist
  6. test_channels_test_endpoint_returns_501_for_unconfigured

Run:
  pytest tests/test_ux_rm_f3a_wizard.py -v
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent
COMP = ROOT / "dashboard" / "components"
STEPS = COMP / "onboarding_steps"


# ── T1: migration idempotent ──────────────────────────────────────────────────

def test_onboarding_state_migration_idempotent():
    """Running the migration SQL twice must not raise."""
    sql_path = ROOT / "migrations" / "2026_06_onboarding_state.sql"
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
        # Second run — idempotent (CREATE TABLE IF NOT EXISTS)
        conn.executescript(sql)
        conn.commit()
        # Table must exist
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='onboarding_state'").fetchone()
        assert row is not None, "onboarding_state table not created"
        # Default row insertable
        conn.execute("INSERT OR IGNORE INTO onboarding_state (user_id) VALUES ('owner')")
        conn.commit()
        row2 = conn.execute("SELECT * FROM onboarding_state WHERE user_id='owner'").fetchone()
        assert row2 is not None
        assert row2["completed"] == 0
        assert row2["last_step"] == 0
    finally:
        conn.close()


# ── T2: GET /api/onboarding/state returns data ───────────────────────────────

def test_onboarding_state_endpoint_get_returns_data():
    """GET /api/onboarding/state must return {data: ...}."""
    from fastapi.testclient import TestClient

    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = None
    mock_conn.close = MagicMock()

    with patch("api.onboarding._ensure_table"), \
         patch("api.onboarding._get_state", return_value=None):
        from api.onboarding import router
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        r = client.get("/api/onboarding/state")
        assert r.status_code == 200
        body = r.json()
        assert "data" in body


# ── T3: POST /api/onboarding/state upserts ───────────────────────────────────

def test_onboarding_state_endpoint_post_upserts():
    """POST /api/onboarding/state must return {status: 'saved'}."""
    from fastapi.testclient import TestClient

    with patch("api.onboarding._ensure_table"), \
         patch("api.onboarding._upsert_state") as mock_upsert:
        from api.onboarding import router
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        payload = {"lastStep": 1, "state": {"photo_done": True}}
        r = client.post("/api/onboarding/state", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "saved"
        mock_upsert.assert_called_once()
        call_args = mock_upsert.call_args
        assert call_args.kwargs.get("last_step") == 1


# ── T4: POST /api/onboarding/complete marks done ─────────────────────────────

def test_onboarding_state_endpoint_complete_marks_done():
    """POST /api/onboarding/complete must return {status: 'completed'} and call upsert with completed=True."""
    from fastapi.testclient import TestClient

    with patch("api.onboarding._ensure_table"), \
         patch("api.onboarding._upsert_state") as mock_upsert:
        from api.onboarding import router
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        r = client.post("/api/onboarding/complete")
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "completed"
        mock_upsert.assert_called_once()
        call_args = mock_upsert.call_args
        assert call_args.kwargs.get("completed") is True


# ── T5: wizard + step files exist ────────────────────────────────────────────

def test_wizard_files_exist():
    """All expected onboarding JS files must be present."""
    expected = [
        COMP / "onboarding_wizard.js",
        STEPS / "welcome.js",
        STEPS / "profile.js",
        STEPS / "channels.js",
    ]
    for path in expected:
        assert path.exists(), f"Missing file: {path}"


# ── T6: channels test endpoint returns 501 for unconfigured channel ───────────

def test_channels_test_endpoint_returns_501_for_unconfigured():
    """GET /api/channels/email/test must return 501 (email not yet configured)."""
    from fastapi.testclient import TestClient
    from api.onboarding import router
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/channels/email/test")
    assert r.status_code == 501, f"Expected 501, got {r.status_code}: {r.text}"
    r2 = client.get("/api/channels/whatsapp/test")
    assert r2.status_code == 501
    r3 = client.get("/api/channels/linkedin/test")
    assert r3.status_code == 501
