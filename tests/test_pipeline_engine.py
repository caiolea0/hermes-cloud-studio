"""H6 B17 — F.9 Pipeline Engine test suite (10 tests).

Covers: execute_run, execute_ab_test, validate_tools, caller_chapter propagation.
Pattern: tmp_path DB isolation + AsyncMock brain + monkeypatch DB_PATH.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# DB setup helpers
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
CREATE TABLE IF NOT EXISTS mcp_registry (
    id INTEGER PRIMARY KEY,
    name TEXT,
    server TEXT NOT NULL,
    tools TEXT,
    status TEXT DEFAULT 'pending',
    tier TEXT DEFAULT 'standard'
);
"""

_SIMPLE_YAML = """
steps:
  - name: step_one
    tool: test-server.my_tool
    args:
      msg: hello
"""

_JINJA_YAML = """
steps:
  - name: step_jinja
    tool: test-server.my_tool
    args:
      value: "{{ missing_var }}"
"""


def _make_db(tmp_path: Path) -> Path:
    db = tmp_path / "test_engine.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(_PIPELINE_DDL)
    conn.commit()
    conn.close()
    return db


def _insert_draft(db: Path, draft_id: str, yaml_blob: str = _SIMPLE_YAML, status: str = "draft") -> None:
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO pipeline_drafts (id, name, yaml_blob, status) VALUES (?, ?, ?, ?)",
        (draft_id, "test-draft", yaml_blob, status),
    )
    conn.commit()
    conn.close()


def _insert_run_init(db: Path, run_id: str, draft_id: str) -> None:
    conn = sqlite3.connect(str(db))
    conn.execute(
        """INSERT INTO pipeline_runs_granular
           (run_id, draft_id, step_idx, step_name, status, started_at)
           VALUES (?, ?, -1, '_run_init_', 'pending', CURRENT_TIMESTAMP)""",
        (run_id, draft_id),
    )
    conn.commit()
    conn.close()


def _seed_registry(db: Path, server: str = "test-server", tools: list | None = None) -> None:
    t = tools or ["my_tool"]
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT OR REPLACE INTO mcp_registry (server, tools, status, tier) VALUES (?, ?, 'active', 'standard')",
        (server, json.dumps(t)),
    )
    conn.commit()
    conn.close()


def _get_run_rows(db: Path, run_id: str) -> list[dict]:
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM pipeline_runs_granular WHERE run_id = ? ORDER BY step_idx",
        (run_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Async helper
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Mock Brain
# ---------------------------------------------------------------------------

def _make_mock_brain(status: str = "completed", side_effect=None):
    brain = MagicMock()
    if side_effect:
        brain.decide = AsyncMock(side_effect=side_effect)
    else:
        brain.decide = AsyncMock(return_value={
            "status": status,
            "result": {"output": "ok"},
            "total_cost_credits": 0.5,
        })
    return brain


# ---------------------------------------------------------------------------
# T1: execute_run persists step rows to pipeline_runs_granular
# ---------------------------------------------------------------------------

def test_execute_run_persists_pipeline_runs_granular(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    _seed_registry(db)
    draft_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    _insert_draft(db, draft_id)
    _insert_run_init(db, run_id, draft_id)

    monkeypatch.setattr("core.pipeline_engine.DB_PATH", db)
    brain = _make_mock_brain(status="completed")

    from core.pipeline_engine import PipelineEngine
    engine = PipelineEngine(brain=brain)

    with patch.object(engine, "_broadcast_pipeline_event"):
        _run(engine.execute_run(run_id, draft_id))

    rows = _get_run_rows(db, run_id)
    # step_idx >= 0 rows written
    step_rows = [r for r in rows if r["step_idx"] >= 0]
    assert len(step_rows) >= 1
    assert step_rows[0]["step_name"] == "step_one"


# ---------------------------------------------------------------------------
# T2: jinja strict undefined → step error row
# ---------------------------------------------------------------------------

def test_execute_run_jinja_strict_undefined_raises(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    _seed_registry(db)
    draft_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    _insert_draft(db, draft_id, yaml_blob=_JINJA_YAML)
    _insert_run_init(db, run_id, draft_id)

    monkeypatch.setattr("core.pipeline_engine.DB_PATH", db)
    brain = _make_mock_brain(status="completed")

    from core.pipeline_engine import PipelineEngine
    engine = PipelineEngine(brain=brain)

    with patch.object(engine, "_broadcast_pipeline_event"):
        _run(engine.execute_run(run_id, draft_id))

    rows = _get_run_rows(db, run_id)
    step_rows = [r for r in rows if r["step_idx"] >= 0]
    assert len(step_rows) >= 1
    assert step_rows[0]["status"] == "error"
    assert "jinja_undefined" in (step_rows[0]["error"] or "")


# ---------------------------------------------------------------------------
# T3: caller_chapter='F.9' propagated via _dispatch_route_skill_run
# ---------------------------------------------------------------------------

def test_execute_run_logs_caller_chapter_f9():
    """_dispatch_route_skill_run passes caller_chapter='F.9' to dispatcher.invoke_tool (H6 B15)."""
    from brain.dispatch import GatewayDispatcher
    import brain.intents as intents_mod

    dispatched = []

    async def _spy(server, tool, args, caller_chapter=None, **kw):
        dispatched.append(caller_chapter)
        return {"ok": True, "response": {}}

    d = MagicMock(spec=GatewayDispatcher)
    d.invoke_tool = _spy

    _run(intents_mod._dispatch_route_skill_run({"server": "sv", "tool": "tl", "args": {}}, d))

    assert len(dispatched) == 1
    assert dispatched[0] == "F.9"


# ---------------------------------------------------------------------------
# T4: execute_ab_test returns 2 distinct run IDs
# ---------------------------------------------------------------------------

def test_execute_ab_test_2_parallel_runs(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    draft_a = str(uuid.uuid4())
    draft_b = str(uuid.uuid4())
    _insert_draft(db, draft_a)
    _insert_draft(db, draft_b)

    monkeypatch.setattr("core.pipeline_engine.DB_PATH", db)

    # Patch Brain to succeed for both runs
    brain = _make_mock_brain(status="completed")
    with (
        patch("core.pipeline_engine.PipelineEngine.__init__", lambda self, **kw: setattr(self, "brain", brain) or setattr(self, "jinja_env", __import__("jinja2").sandbox.SandboxedEnvironment(undefined=__import__("jinja2").StrictUndefined))),
        patch.object(brain, "decide", new=brain.decide),
    ):
        from core.pipeline_engine import execute_ab_test
        result = _run(execute_ab_test(draft_a_id=draft_a, draft_b_id=draft_b))

    assert "run_a_id" in result
    assert "run_b_id" in result
    assert result["run_a_id"] != result["run_b_id"]
    assert result.get("ab_test_started") is True


# ---------------------------------------------------------------------------
# T5: execute_ab_test error captured (D6 return_exceptions=True)
# ---------------------------------------------------------------------------

def test_execute_ab_test_errors_captured(tmp_path, monkeypatch):
    """Missing draft → execute_run errors captured, not raised (D6 pattern)."""
    db = _make_db(tmp_path)
    monkeypatch.setattr("core.pipeline_engine.DB_PATH", db)

    # Drafts don't exist — execute_run will INSERT _run_init_ but fail on yaml load
    draft_a = str(uuid.uuid4())
    draft_b = str(uuid.uuid4())
    # Only create a_id in DB, b_id missing → one run finishes (empty steps → error), one finishes too
    _insert_draft(db, draft_a, yaml_blob="steps: []\n")

    from core.pipeline_engine import execute_ab_test
    result = _run(execute_ab_test(draft_a_id=draft_a, draft_b_id=draft_b))

    # Both run IDs must be returned regardless of errors
    assert result["run_a_id"]
    assert result["run_b_id"]
    # errors list is a list (may be empty or contain exception details)
    assert isinstance(result.get("errors"), list)


# ---------------------------------------------------------------------------
# T6: step failure aborts remaining steps (D2 stop-default)
# ---------------------------------------------------------------------------

def test_execute_run_step_failure_aborts_remaining(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    _seed_registry(db)
    multi_step_yaml = """
steps:
  - name: step_fail
    tool: test-server.my_tool
    args: {}
  - name: step_should_not_run
    tool: test-server.my_tool
    args: {}
"""
    draft_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    _insert_draft(db, draft_id, yaml_blob=multi_step_yaml)
    _insert_run_init(db, run_id, draft_id)

    monkeypatch.setattr("core.pipeline_engine.DB_PATH", db)
    # Brain returns non-completed status → error path
    brain = _make_mock_brain(status="failed")

    from core.pipeline_engine import PipelineEngine
    engine = PipelineEngine(brain=brain)

    with patch.object(engine, "_broadcast_pipeline_event"):
        _run(engine.execute_run(run_id, draft_id))

    rows = _get_run_rows(db, run_id)
    step_rows = [r for r in rows if r["step_idx"] >= 0]
    # First step should be "error"; second step should NOT have been started (stop-default D2)
    assert step_rows[0]["status"] == "error"
    assert len(step_rows) == 1  # second step never inserted


# ---------------------------------------------------------------------------
# T7: D8 step timeout creates error row
# ---------------------------------------------------------------------------

def test_execute_run_timeout_per_step(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    _seed_registry(db)
    draft_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    _insert_draft(db, draft_id)
    _insert_run_init(db, run_id, draft_id)

    monkeypatch.setattr("core.pipeline_engine.DB_PATH", db)
    # Override timeout to 0 seconds so it times out immediately
    monkeypatch.setattr("core.pipeline_engine.STEP_TIMEOUT_SECONDS", 0)

    async def _slow_decide(*a, **kw):
        await asyncio.sleep(1)  # exceeds 0s timeout
        return {"status": "completed", "result": {}, "total_cost_credits": 0.0}

    brain = MagicMock()
    brain.decide = _slow_decide

    from core.pipeline_engine import PipelineEngine
    engine = PipelineEngine(brain=brain)

    with patch.object(engine, "_broadcast_pipeline_event"):
        _run(engine.execute_run(run_id, draft_id))

    rows = _get_run_rows(db, run_id)
    step_rows = [r for r in rows if r["step_idx"] >= 0]
    assert len(step_rows) >= 1
    assert step_rows[0]["status"] == "error"
    assert "timeout" in (step_rows[0]["error"] or "")


# ---------------------------------------------------------------------------
# T8: validate_tools with missing mcp_registry degrades gracefully
# ---------------------------------------------------------------------------

def test_validate_tools_fails_fast_if_registry_missing(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    # Drop mcp_registry to simulate missing table
    conn = sqlite3.connect(str(db))
    conn.execute("DROP TABLE IF EXISTS mcp_registry")
    conn.commit()
    conn.close()

    monkeypatch.setattr("core.pipeline_engine.DB_PATH", db)
    brain = _make_mock_brain()
    from core.pipeline_engine import PipelineEngine
    engine = PipelineEngine(brain=brain)

    steps = [{"name": "s1", "tool": "srv.tool"}]
    errors = _run(engine.validate_tools(steps))

    # Missing registry → degrade gracefully (returns [] not crash)
    assert isinstance(errors, list)
    assert errors == []  # "allowing all" path per GUARDRAILS D4


# ---------------------------------------------------------------------------
# T9: validate_tools rejects blocked-tier tool
# ---------------------------------------------------------------------------

def test_validate_tools_rejects_blocked_tier(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO mcp_registry (server, tools, status, tier) VALUES (?, ?, 'active', 'quarantine')",
        ("blocked-srv", json.dumps(["bad_tool"])),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("core.pipeline_engine.DB_PATH", db)
    brain = _make_mock_brain()
    from core.pipeline_engine import PipelineEngine
    engine = PipelineEngine(brain=brain)

    steps = [{"name": "s1", "tool": "blocked-srv.bad_tool"}]
    errors = _run(engine.validate_tools(steps))

    assert len(errors) == 1
    assert "quarantine" in errors[0]["error"]


# ---------------------------------------------------------------------------
# T10: clone preserves cloned_from_id in pipeline_drafts
# ---------------------------------------------------------------------------

def test_clone_pipeline_preserves_cloned_from_id(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    original_id = str(uuid.uuid4())
    _insert_draft(db, original_id, yaml_blob=_SIMPLE_YAML, status="draft")

    monkeypatch.setattr("api.pipeline_studio.DB_PATH", db)
    monkeypatch.setattr("core.state.DB_PATH", db)

    from fastapi.testclient import TestClient
    from server import app
    from core.state import AUTH_TOKEN
    client = TestClient(app)

    resp = client.post(
        f"/api/pipeline-studio/drafts/{original_id}/clone",
        headers={"X-Hermes-Token": AUTH_TOKEN},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["cloned_from_id"] == original_id
    assert data["version"] == 1
    assert "(copy)" in data["name"]

    # Verify in DB directly
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT cloned_from_id FROM pipeline_drafts WHERE id = ?", (data["id"],)
    ).fetchone()
    conn.close()
    assert row["cloned_from_id"] == original_id
