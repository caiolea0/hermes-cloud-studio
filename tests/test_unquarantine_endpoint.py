"""F.4.4 C2 — POST /api/skills/{name}/unquarantine endpoint tests.

Validates:
  - 404 when no proposal found for skill_name
  - 409 when proposal exists but not currently quarantined
  - 200 success: clears quarantine_at + quarantine_reason (PC state)
  - WS emit brain.skill_unquarantined on success
  - Audit trail: skill_sync_runs row with trigger_type='manual_unquarantine'
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.skills import router


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path: Path, *, quarantined: bool = False, insert_proposal: bool = True) -> Path:
    db = tmp_path / "hermes_local.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS skill_proposals (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'draft',
            description TEXT,
            yaml_blob TEXT NOT NULL DEFAULT '',
            source_pattern TEXT NOT NULL DEFAULT 'owner_manual',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            quarantine_at TEXT,
            quarantine_reason TEXT
        );
        CREATE TABLE IF NOT EXISTS skill_sync_runs (
            id TEXT PRIMARY KEY,
            trigger_type TEXT NOT NULL,
            pr_number INTEGER,
            pr_url TEXT,
            sync_status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            error_message TEXT,
            affected_skills TEXT
        );
    """)
    if insert_proposal:
        quarantine_at = "2026-06-16T10:00:00" if quarantined else None
        quarantine_reason = "success_rate=0.20 < 0.5 (last 10)" if quarantined else None
        status = "archived" if quarantined else "deployed"
        conn.execute(
            """INSERT INTO skill_proposals
               (id, name, status, yaml_blob, source_pattern, quarantine_at, quarantine_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), "cobaia-daily", status, "name: cobaia-daily\n", "owner_manual",
             quarantine_at, quarantine_reason),
        )
    conn.commit()
    conn.close()
    return db


# ---------------------------------------------------------------------------
# test_unquarantine_404_if_proposal_not_found
# ---------------------------------------------------------------------------

def test_unquarantine_404_if_proposal_not_found(client, tmp_path):
    """POST /api/skills/nonexistent/unquarantine → 404 (no proposal row)."""
    db = _make_db(tmp_path, insert_proposal=False)
    with patch("core.skill_proposals.DB_PATH", db):
        resp = client.post("/api/skills/nonexistent/unquarantine", json={"reason": "test"})
    assert resp.status_code == 404
    assert "No skill proposal found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# test_unquarantine_409_if_not_quarantined
# ---------------------------------------------------------------------------

def test_unquarantine_409_if_not_quarantined(client, tmp_path):
    """POST with existing proposal that has quarantine_at=NULL → 409."""
    db = _make_db(tmp_path, quarantined=False)
    with patch("core.skill_proposals.DB_PATH", db):
        resp = client.post("/api/skills/cobaia-daily/unquarantine", json={"reason": "oops"})
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "not quarantined" in detail or "quarantine_at is NULL" in detail


# ---------------------------------------------------------------------------
# test_unquarantine_success_clears_quarantine_at
# ---------------------------------------------------------------------------

def test_unquarantine_success_clears_quarantine_at(client, tmp_path):
    """POST on quarantined skill → 200 + quarantine_at cleared in DB."""
    db = _make_db(tmp_path, quarantined=True)
    with patch("core.skill_proposals.DB_PATH", db):
        resp = client.post("/api/skills/cobaia-daily/unquarantine", json={"reason": "fixed"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["skill_name"] == "cobaia-daily"
    assert "run_id" in body

    # Verify DB state — quarantine_at must be NULL after unquarantine
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT quarantine_at, quarantine_reason, status FROM skill_proposals WHERE name='cobaia-daily'"
    ).fetchone()
    conn.close()
    assert row[0] is None, "quarantine_at must be cleared"
    assert row[1] is None, "quarantine_reason must be cleared"
    assert row[2] == "deployed"


# ---------------------------------------------------------------------------
# test_unquarantine_ws_emit_brain_skill_unquarantined
# ---------------------------------------------------------------------------

def test_unquarantine_ws_emit_brain_skill_unquarantined(client, tmp_path):
    """Successful unquarantine must emit brain.skill_unquarantined WS event."""
    db = _make_db(tmp_path, quarantined=True)

    mock_ws = AsyncMock()

    with patch("core.skill_proposals.DB_PATH", db), \
         patch("core.state.ws_manager") as mock_mgr:
        mock_mgr.broadcast = mock_ws
        resp = client.post("/api/skills/cobaia-daily/unquarantine", json={"reason": "manual"})

    assert resp.status_code == 200
    # broadcast called at least once (fire-and-forget via asyncio.create_task)
    mock_mgr.broadcast.assert_called_once()
    call_payload = mock_mgr.broadcast.call_args[0][0]
    assert call_payload["type"] == "brain.skill_unquarantined"
    assert call_payload["skill_name"] == "cobaia-daily"


# ---------------------------------------------------------------------------
# test_unquarantine_audit_trail_in_skill_sync_runs
# ---------------------------------------------------------------------------

def test_unquarantine_audit_trail_in_skill_sync_runs(client, tmp_path):
    """Successful unquarantine inserts row in skill_sync_runs with trigger_type='manual_unquarantine'."""
    db = _make_db(tmp_path, quarantined=True)
    reason = "owner decided to restore"

    with patch("core.skill_proposals.DB_PATH", db):
        resp = client.post(
            "/api/skills/cobaia-daily/unquarantine",
            json={"reason": reason},
        )

    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT trigger_type, sync_status, affected_skills, error_message FROM skill_sync_runs WHERE id=?",
        (run_id,),
    ).fetchone()
    conn.close()

    assert row is not None, "skill_sync_runs row must exist"
    assert row[0] == "manual_unquarantine"
    assert row[1] == "unquarantined"
    skills = json.loads(row[2])
    assert "cobaia-daily" in skills
    assert row[3] == reason
