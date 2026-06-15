"""F.4.3 C2 — smoke tests for new endpoints + reject WS emit.

Validates:
  /api/config whitelist (HERMES_F43_WS_LISTENER)
  /api/skills/synthesis-runs/{id} GET (404 on missing, 200 on present)
  /api/skills/proposals/{id}/reject body {reason} persists
"""
from __future__ import annotations

import os
import sqlite3
import uuid
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from server import app
    return TestClient(app)


@pytest.fixture
def auth_token():
    from core.state import AUTH_TOKEN
    return AUTH_TOKEN


@pytest.fixture
def auth_headers(auth_token):
    return {"X-Hermes-Token": auth_token, "Content-Type": "application/json"}


def _ensure_tables():
    from core.skill_proposals import ensure_synthesis_runs_table
    ensure_synthesis_runs_table()


def _create_proposal(name: str = "test_f43_c2") -> str:
    from core.state import DB_PATH
    pid = str(uuid.uuid4())
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(
            "INSERT INTO skill_proposals (id, name, description, yaml_blob, source_pattern) VALUES (?,?,?,?,?)",
            (pid, name, "F.4.3 C2 smoke", "name: test\nactive: true", "owner_manual"),
        )
        conn.commit()
    finally:
        conn.close()
    return pid


def _cleanup_proposal(pid: str) -> None:
    from core.state import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("DELETE FROM skill_proposals WHERE id=?", (pid,))
        conn.commit()
    finally:
        conn.close()


def _cleanup_synthesis(run_id: str) -> None:
    from core.state import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("DELETE FROM synthesis_runs WHERE id=?", (run_id,))
        conn.commit()
    finally:
        conn.close()


def test_config_endpoint_flag_off_by_default(client, auth_headers):
    """HERMES_F43_WS_LISTENER default OFF when env var absent."""
    os.environ.pop("HERMES_F43_WS_LISTENER", None)
    r = client.get("/api/config", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body == {"HERMES_F43_WS_LISTENER": False}


def test_config_endpoint_flag_on_when_env_true(client, auth_headers):
    """HERMES_F43_WS_LISTENER=1 → True."""
    os.environ["HERMES_F43_WS_LISTENER"] = "1"
    try:
        r = client.get("/api/config", headers=auth_headers)
        assert r.status_code == 200
        assert r.json() == {"HERMES_F43_WS_LISTENER": True}
    finally:
        os.environ.pop("HERMES_F43_WS_LISTENER", None)


def test_synthesis_run_not_found_404(client, auth_headers):
    _ensure_tables()
    r = client.get("/api/skills/synthesis-runs/does-not-exist", headers=auth_headers)
    assert r.status_code == 404
    assert r.json() == {"detail": "synthesis_run_not_found"}


def test_synthesis_run_persists_and_reads_back(client, auth_headers):
    """generate POST creates row, synthesis-runs GET reads it back."""
    _ensure_tables()
    r = client.post(
        "/api/skills/proposals/generate",
        headers=auth_headers,
        json={"trigger_source": "ui_button"},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    run_id = body["run_id"]
    try:
        r2 = client.get(f"/api/skills/synthesis-runs/{run_id}", headers=auth_headers)
        assert r2.status_code == 200
        row = r2.json()
        assert row["id"] == run_id
        assert row["status"] == "queued"
        assert row["requester"] == "brain-f4"
        assert row["trigger_source"] == "ui_button"
    finally:
        _cleanup_synthesis(run_id)


def test_reject_persists_reason_and_status_archived(client, auth_headers):
    """Reject with reason → status='archived' + owner_decision_reason persisted."""
    pid = _create_proposal("test_f43_reject_reason")
    try:
        r = client.post(
            f"/api/skills/proposals/{pid}/reject",
            headers=auth_headers,
            json={"reason": "logic conflicts with skill X"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["decision"] == "reject"
        assert body["status"] == "archived"
        assert body["reason"] == "logic conflicts with skill X"

        # Verify persistence in DB
        from core.skill_proposals import manager
        row = manager.get(pid)
        assert row["status"] == "archived"
        assert row["owner_decision_reason"] == "logic conflicts with skill X"
    finally:
        _cleanup_proposal(pid)


def test_reject_empty_reason_ok(client, auth_headers):
    """Reject without reason still works (reason optional)."""
    pid = _create_proposal("test_f43_reject_empty")
    try:
        r = client.post(
            f"/api/skills/proposals/{pid}/reject",
            headers=auth_headers,
            json={},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["decision"] == "reject"
        assert body["status"] == "archived"
        assert body["reason"] is None
    finally:
        _cleanup_proposal(pid)


def test_yaml_preview_returns_expected_keys(client, auth_headers):
    """yaml-preview returns base keys (existing_yaml only when match found)."""
    pid = _create_proposal("test_f43_yaml_preview")
    try:
        r = client.get(f"/api/skills/proposals/{pid}/yaml-preview", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        for key in ("id", "name", "status", "yaml_blob", "chars"):
            assert key in body
        # existing_yaml / existing_filename only populated when AutoSkillRunner
        # finds a close match in skills/ — best-effort, not asserted.
    finally:
        _cleanup_proposal(pid)
