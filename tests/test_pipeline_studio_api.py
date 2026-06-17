"""H6 B17 — F.9 Pipeline Studio API tests (5 tests).

Covers: /runs/ab-test endpoint, /drafts/{id}/clone, /drafts?status filter,
        caller_chapter propagation in invoke_tool.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# DB + App fixtures
# ---------------------------------------------------------------------------

_PIPELINE_DDL = """
CREATE TABLE IF NOT EXISTS pipeline_drafts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    yaml_blob TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft',
    tags TEXT,
    ab_group TEXT,
    owner TEXT NOT NULL DEFAULT 'caio',
    cloned_from_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_executed_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pipeline_runs_granular (
    run_id TEXT NOT NULL,
    draft_id TEXT NOT NULL,
    step_idx INTEGER NOT NULL,
    step_name TEXT NOT NULL,
    tool_invoked TEXT,
    status TEXT NOT NULL,
    output_json TEXT,
    error TEXT,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    latency_ms INTEGER,
    cost_credits REAL DEFAULT 0,
    ab_group TEXT,
    PRIMARY KEY (run_id, step_idx)
);
"""


def _make_db(tmp_path: Path) -> Path:
    db = tmp_path / "ps_api_test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(_PIPELINE_DDL)
    conn.commit()
    conn.close()
    return db


def _insert_draft(db: Path, draft_id: str, status: str = "draft", ab_group: str | None = None) -> str:
    conn = sqlite3.connect(str(db))
    conn.execute(
        """INSERT INTO pipeline_drafts (id, name, yaml_blob, status, ab_group)
           VALUES (?, ?, ?, ?, ?)""",
        (draft_id, f"draft-{draft_id[:8]}", "steps:\n  - name: s1\n    tool: t.s\n    args: {}\n",
         status, ab_group),
    )
    conn.commit()
    conn.close()
    return draft_id


@pytest.fixture
def db_path(tmp_path):
    return _make_db(tmp_path)


@pytest.fixture
def client(db_path, monkeypatch):
    monkeypatch.setattr("api.pipeline_studio.DB_PATH", db_path)
    monkeypatch.setattr("core.state.DB_PATH", db_path)
    from server import app
    return TestClient(app)


@pytest.fixture
def auth_headers():
    from core.state import AUTH_TOKEN
    return {"X-Hermes-Token": AUTH_TOKEN}


# ---------------------------------------------------------------------------
# T1: /runs/ab-test returns run_id_a + run_id_b
# ---------------------------------------------------------------------------

def test_runs_ab_test_endpoint_returns_run_ids(db_path, client, auth_headers):
    a_id = str(uuid.uuid4())
    b_id = str(uuid.uuid4())
    _insert_draft(db_path, a_id)
    _insert_draft(db_path, b_id)

    _fake_result = {
        "ab_test_started": True,
        "run_a_id": "run-a-fake",
        "run_b_id": "run-b-fake",
        "errors": [],
    }

    with patch(
        "core.pipeline_engine.execute_ab_test",
        new=AsyncMock(return_value=_fake_result),
    ):
        resp = client.post(
            "/api/pipeline-studio/runs/ab-test",
            json={"draft_a_id": a_id, "draft_b_id": b_id},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "run_id_a" in data
    assert "run_id_b" in data
    assert data["run_id_a"] != data["run_id_b"]


# ---------------------------------------------------------------------------
# T2: /runs/ab-test returns 404 if variant draft missing
# ---------------------------------------------------------------------------

def test_runs_ab_test_validates_variant_templates_exist(db_path, client, auth_headers):
    a_id = str(uuid.uuid4())
    _insert_draft(db_path, a_id)
    missing_id = str(uuid.uuid4())  # not in DB

    resp = client.post(
        "/api/pipeline-studio/runs/ab-test",
        json={"draft_a_id": a_id, "draft_b_id": missing_id},
        headers=auth_headers,
    )
    assert resp.status_code == 404
    assert "draft_b_id" in resp.json().get("detail", "")


# ---------------------------------------------------------------------------
# T3: caller_chapter='F.9' propagated in _dispatch_route_skill_run
# ---------------------------------------------------------------------------

def test_runs_ab_test_caller_chapter_f9_logged():
    """_dispatch_route_skill_run passes caller_chapter='F.9' to invoke_tool."""
    import asyncio
    from brain.dispatch import GatewayDispatcher

    chapter_captured = []

    async def _spy_invoke(server, tool, args, caller_chapter=None, **kw):
        chapter_captured.append(caller_chapter)
        return {"ok": True, "response": {}}

    d = MagicMock(spec=GatewayDispatcher)
    d.invoke_tool = _spy_invoke

    import brain.intents as intents_mod
    asyncio.run(
        intents_mod._dispatch_route_skill_run({"server": "srv", "tool": "t", "args": {}}, d)
    )

    assert chapter_captured == ["F.9"], f"caller_chapter not F.9: {chapter_captured}"


# ---------------------------------------------------------------------------
# T4: /drafts/{id}/clone increments version to 1 and preserves cloned_from_id
# ---------------------------------------------------------------------------

def test_clone_endpoint_increments_version(db_path, client, auth_headers):
    original_id = str(uuid.uuid4())
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO pipeline_drafts (id, name, yaml_blob, version, status) VALUES (?, ?, ?, 5, 'draft')",
        (original_id, "v5-draft", "steps:\n  - {name: s, tool: t.s, args: {}}\n"),
    )
    conn.commit()
    conn.close()

    resp = client.post(
        f"/api/pipeline-studio/drafts/{original_id}/clone",
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    # Clone always resets version to 1 (server-side reset)
    assert data["version"] == 1
    assert data["cloned_from_id"] == original_id
    assert "(copy)" in data["name"]


# ---------------------------------------------------------------------------
# T5: GET /drafts?status=active filters by status
# ---------------------------------------------------------------------------

def test_pipeline_drafts_list_filters_by_status(db_path, client, auth_headers):
    active_id = str(uuid.uuid4())
    archived_id = str(uuid.uuid4())
    draft_id = str(uuid.uuid4())
    _insert_draft(db_path, active_id, status="active")
    _insert_draft(db_path, archived_id, status="archived")
    _insert_draft(db_path, draft_id, status="draft")

    resp = client.get("/api/pipeline-studio/drafts?status=active", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    ids = [item["id"] for item in data.get("items", [])]
    assert active_id in ids
    assert archived_id not in ids
    assert draft_id not in ids
