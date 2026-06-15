"""F.4.2 C1 — AutoSkillRunner unit tests (PIVOT D1 inline YAML validation)."""
from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

import core.skill_proposals as skill_proposals_module
import core.state as state_module
from core.auto_skill_runner import AutoSkillRunner, _shortid, _slugify
from core.skill_proposals import SkillProposalsManager


@pytest.fixture
def runner_with_tmp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "f42c1.db"
    sql = Path(__file__).parent.parent.joinpath(
        "migrations", "2026_06_skill_proposals.sql"
    ).read_text(encoding="utf-8")
    conn = sqlite3.connect(str(db_path))
    conn.executescript(sql)
    conn.close()

    monkeypatch.setattr(state_module, "DB_PATH", db_path)
    monkeypatch.setattr(skill_proposals_module, "DB_PATH", db_path)

    manager = SkillProposalsManager()
    runner = AutoSkillRunner(dispatcher=None, manager=manager)
    return runner, manager, db_path


# ---------------------------------------------------------------------------
# D1 PIVOT — inline YAML validation
# ---------------------------------------------------------------------------

def test_validate_yaml_inline_valid():
    runner = AutoSkillRunner(dispatcher=None, manager=None)
    yaml_blob = (
        "name: cobaia-daily\n"
        "version: 0.1\n"
        "provider: openrouter\n"
        "model: deepseek-chat:free\n"
    )
    result = runner._validate_yaml_inline(yaml_blob)
    assert result["status"] == "passed"
    assert result["exit_code"] == 0
    assert result["mock"] is True
    assert "Validation OK" in result["stdout"]
    assert result["stderr"] == ""
    assert result["latency_ms"] >= 0


def test_validate_yaml_inline_invalid_missing_key():
    runner = AutoSkillRunner(dispatcher=None, manager=None)
    yaml_blob = "name: only-name\n"
    result = runner._validate_yaml_inline(yaml_blob)
    assert result["status"] == "failed"
    assert result["exit_code"] == 1
    assert "version" in result["stderr"]


def test_validate_yaml_inline_malformed_yaml():
    runner = AutoSkillRunner(dispatcher=None, manager=None)
    yaml_blob = "name: foo\n  bad: indentation\n: : : invalid"
    result = runner._validate_yaml_inline(yaml_blob)
    assert result["status"] == "failed"
    assert result["exit_code"] == 1
    assert (
        "YAMLError" in result["stderr"]
        or "must be a mapping" in result["stderr"]
        or "Missing required" in result["stderr"]
    )


def test_validate_yaml_inline_missing_provider_and_steps():
    runner = AutoSkillRunner(dispatcher=None, manager=None)
    yaml_blob = "name: foo\nversion: 0.1\n"
    result = runner._validate_yaml_inline(yaml_blob)
    assert result["status"] == "failed"
    assert "provider" in result["stderr"]


def test_validate_yaml_inline_steps_only_ok():
    runner = AutoSkillRunner(dispatcher=None, manager=None)
    yaml_blob = "name: pipeline-skill\nversion: 0.2\nsteps:\n  - id: a\n"
    result = runner._validate_yaml_inline(yaml_blob)
    assert result["status"] == "passed"


# ---------------------------------------------------------------------------
# D3 — slugify / shortid helpers
# ---------------------------------------------------------------------------

def test_slugify_basic():
    assert _slugify("Cobaia Monitor Daily") == "cobaia-monitor-daily"
    assert _slugify("UPPER lower 123") == "upper-lower-123"
    assert _slugify("special!@#$chars") == "special-chars"
    assert _slugify("") == "unnamed"


def test_slugify_truncates_40():
    long_name = "a" * 100
    out = _slugify(long_name)
    assert len(out) <= 40


def test_shortid_six_chars():
    full = "a3f9c2d4-1234-5678-9abc-def012345678"
    assert _shortid(full) == "a3f9c2"
    assert _shortid("") == "000000"


# ---------------------------------------------------------------------------
# dispatch_sandbox_test — integration with tmp DB
# ---------------------------------------------------------------------------

def test_dispatch_sandbox_test_persists_passed(runner_with_tmp_db):
    runner, manager, _ = runner_with_tmp_db
    created = manager.create(
        name="dispatch-smoke",
        description="C1 smoke pass",
        yaml_blob=(
            "name: dispatch-smoke\n"
            "version: 0.1\n"
            "provider: openrouter\n"
        ),
    )
    proposal_id = created["id"]
    manager.owner_decision(proposal_id, decision="accept", reason="t")

    result = asyncio.run(runner.dispatch_sandbox_test(proposal_id))
    assert result["ok"] is True
    assert result["new_status"] == "lab_passed"
    assert result["lab_test_result"]["status"] == "passed"

    updated = manager.get(proposal_id)
    assert updated["status"] == "lab_passed"
    assert updated["lab_test_status"] == "passed"
    lab_blob = json.loads(updated["lab_test_result"])
    assert lab_blob["mock"] is True


def test_dispatch_sandbox_test_failed_yaml(runner_with_tmp_db):
    runner, manager, _ = runner_with_tmp_db
    created = manager.create(
        name="bad-yaml",
        description="C1 smoke fail",
        yaml_blob="name: bad\n",
    )
    proposal_id = created["id"]
    manager.owner_decision(proposal_id, decision="accept", reason="t")

    result = asyncio.run(runner.dispatch_sandbox_test(proposal_id))
    assert result["ok"] is False
    assert result["new_status"] == "lab_failed"
    assert result["lab_test_result"]["status"] == "failed"

    updated = manager.get(proposal_id)
    assert updated["status"] == "lab_failed"


def test_dispatch_sandbox_test_proposal_not_found(runner_with_tmp_db):
    runner, _manager, _ = runner_with_tmp_db
    with pytest.raises(LookupError):
        asyncio.run(runner.dispatch_sandbox_test("does-not-exist"))


# ---------------------------------------------------------------------------
# C2 — dispatch_github_pr (mock dispatcher — no real GitHub API hits)
# ---------------------------------------------------------------------------

class _MockDispatcher:
    """Capture-only dispatcher for C2 tests. Records invoke_tool calls."""

    def __init__(self, response: dict | None = None, raise_exc: Exception | None = None):
        self.response = response
        self.raise_exc = raise_exc
        self.calls: list[dict] = []

    async def invoke_tool(self, server, tool, args, requester="brain"):
        self.calls.append({
            "server": server, "tool": tool, "args": args, "requester": requester,
        })
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.response or {"ok": True, "response": {}}


def _make_passed_proposal(manager, name="cobaia-daily"):
    """Helper — create proposal + force lab_passed via runner inline validation."""
    created = manager.create(
        name=name,
        description="C2 fixture rationale",
        yaml_blob=(
            f"name: {name}\n"
            "version: 0.1\n"
            "provider: openrouter\n"
        ),
    )
    manager.owner_decision(created["id"], decision="accept", reason="t")
    # Persist lab_passed directly (skip runner; we test dispatch_github_pr unit).
    manager.update_lab_result(
        created["id"],
        {
            "status": "passed", "stdout": "ok", "stderr": "",
            "latency_ms": 5, "exit_code": 0, "mock": True,
        },
        lab_test_status="passed",
    )
    return created["id"]


def test_dispatch_github_pr_blocks_on_lab_failed(runner_with_tmp_db):
    runner, manager, _ = runner_with_tmp_db
    dispatcher = _MockDispatcher(response={"ok": True, "response": {"html_url": "x"}})
    runner.dispatcher = dispatcher
    created = manager.create(
        name="bad", description="r", yaml_blob="name: bad\n",
    )
    manager.owner_decision(created["id"], decision="accept", reason="t")
    manager.update_lab_result(
        created["id"],
        {"status": "failed", "stdout": "", "stderr": "missing version",
         "latency_ms": 1, "exit_code": 1, "mock": True},
        lab_test_status="failed",
    )
    result = asyncio.run(runner.dispatch_github_pr(created["id"]))
    assert result["status"] == "blocked"
    assert result["reason"] == "lab_not_passed"
    # D4 — no GitHub MCP call attempted.
    assert dispatcher.calls == []


def test_dispatch_github_pr_success_full_template(runner_with_tmp_db):
    runner, manager, _ = runner_with_tmp_db
    dispatcher = _MockDispatcher(response={
        "ok": True,
        "response": {
            "html_url": "https://github.com/caiolea0/hermes-cloud-studio/pull/42",
            "number": 42,
        },
    })
    runner.dispatcher = dispatcher
    proposal_id = _make_passed_proposal(manager, name="cobaia-daily")

    result = asyncio.run(runner.dispatch_github_pr(proposal_id))
    assert result["status"] == "ok"
    assert result["pr_url"] == "https://github.com/caiolea0/hermes-cloud-studio/pull/42"
    assert result["pr_number"] == 42
    assert result["branch"].startswith("skill/proposal-cobaia-daily-")

    # D2 template fields present in body.
    body = dispatcher.calls[0]["args"]["body"]
    assert "Skill Proposal: cobaia-daily" in body
    assert "Lab test result" in body
    assert "YAML diff" in body
    assert "Brain rationale" in body


def test_dispatch_github_pr_branch_naming_correct(runner_with_tmp_db):
    runner, manager, _ = runner_with_tmp_db
    dispatcher = _MockDispatcher(response={
        "ok": True, "response": {"html_url": "u", "number": 1},
    })
    runner.dispatcher = dispatcher
    proposal_id = _make_passed_proposal(manager, name="Cobaia Monitor Daily")
    result = asyncio.run(runner.dispatch_github_pr(proposal_id))
    # D3 — skill/proposal-{slug}-{shortid first 6 chars uuid}
    branch = result["branch"]
    assert branch.startswith("skill/proposal-cobaia-monitor-daily-")
    suffix = branch.split("-")[-1]
    assert len(suffix) == 6


def test_dispatch_github_pr_yaml_diff_no_existing(runner_with_tmp_db, tmp_path, monkeypatch):
    runner, manager, _ = runner_with_tmp_db
    dispatcher = _MockDispatcher(response={
        "ok": True, "response": {"html_url": "u", "number": 1},
    })
    runner.dispatcher = dispatcher
    # Force closest-skill lookup to a non-existent dir → fallback message.
    monkeypatch.setattr(
        "core.auto_skill_runner.AutoSkillRunner._find_closest_skill_yaml",
        staticmethod(lambda name, skills_dir=None: None),
    )
    proposal_id = _make_passed_proposal(manager, name="brand-new-skill")
    asyncio.run(runner.dispatch_github_pr(proposal_id))
    body = dispatcher.calls[0]["args"]["body"]
    assert "no diff available" in body


def test_dispatch_github_pr_yaml_diff_with_existing(runner_with_tmp_db, tmp_path, monkeypatch):
    runner, manager, _ = runner_with_tmp_db
    dispatcher = _MockDispatcher(response={
        "ok": True, "response": {"html_url": "u", "number": 1},
    })
    runner.dispatcher = dispatcher
    existing_yaml = "name: cobaia-daily\nversion: 0.1\nprovider: ollama\n"
    monkeypatch.setattr(
        "core.auto_skill_runner.AutoSkillRunner._find_closest_skill_yaml",
        staticmethod(lambda name, skills_dir=None: ("cobaia-daily.yaml", existing_yaml)),
    )
    proposal_id = _make_passed_proposal(manager, name="cobaia-daily")
    asyncio.run(runner.dispatch_github_pr(proposal_id))
    body = dispatcher.calls[0]["args"]["body"]
    assert "-provider: ollama" in body or "+provider: openrouter" in body


def test_dispatch_github_pr_github_429_fail_fast(runner_with_tmp_db):
    runner, manager, _ = runner_with_tmp_db
    dispatcher = _MockDispatcher(response={
        "ok": False, "status_code": 429,
        "error": "rate limit exceeded",
    })
    runner.dispatcher = dispatcher
    proposal_id = _make_passed_proposal(manager, name="rl-test")
    result = asyncio.run(runner.dispatch_github_pr(proposal_id))
    # D5 — fail-fast, NO retry, returns status='failed'.
    assert result["status"] == "failed"
    assert result["status_code"] == 429
    assert len(dispatcher.calls) == 1


def test_dispatch_github_pr_github_401_fail_fast(runner_with_tmp_db):
    runner, manager, _ = runner_with_tmp_db
    dispatcher = _MockDispatcher(response={
        "ok": False, "status_code": 401, "error": "bad credentials",
    })
    runner.dispatcher = dispatcher
    proposal_id = _make_passed_proposal(manager, name="auth-test")
    result = asyncio.run(runner.dispatch_github_pr(proposal_id))
    assert result["status"] == "failed"
    assert result["status_code"] == 401
    assert len(dispatcher.calls) == 1


def test_dispatch_github_pr_persists_pr_url_on_success(runner_with_tmp_db):
    runner, manager, _ = runner_with_tmp_db
    dispatcher = _MockDispatcher(response={
        "ok": True,
        "response": {
            "html_url": "https://github.com/o/r/pull/7", "number": 7,
        },
    })
    runner.dispatcher = dispatcher
    proposal_id = _make_passed_proposal(manager, name="persist-test")
    asyncio.run(runner.dispatch_github_pr(proposal_id))
    updated = manager.get(proposal_id)
    assert updated["status"] == "pr_open"
    assert updated["pr_url"] == "https://github.com/o/r/pull/7"
    assert updated["pr_branch"].startswith("skill/proposal-persist-test-")
    assert updated["pr_status"] == "open"


def test_dispatch_github_pr_requester_brain_f4(runner_with_tmp_db):
    """D7 PIVOT — dispatcher.invoke_tool receives requester='brain-f4'."""
    runner, manager, _ = runner_with_tmp_db
    dispatcher = _MockDispatcher(response={
        "ok": True, "response": {"html_url": "u", "number": 1},
    })
    runner.dispatcher = dispatcher
    proposal_id = _make_passed_proposal(manager, name="d7-test")
    asyncio.run(runner.dispatch_github_pr(proposal_id))
    assert dispatcher.calls[0]["requester"] == "brain-f4"
    assert dispatcher.calls[0]["server"] == "github"
    assert dispatcher.calls[0]["tool"] == "create_pull_request"


# ---------------------------------------------------------------------------
# C3 — trigger_workflow_synthesis (PIVOT D6 honest scaffold)
# ---------------------------------------------------------------------------

def test_trigger_workflow_synthesis_persists_synthesis_runs(runner_with_tmp_db):
    runner, _manager, db_path = runner_with_tmp_db
    result = asyncio.run(runner.trigger_workflow_synthesis(
        manual=True, trigger_source="api_manual",
    ))
    assert result["status"] == "queued"
    assert "scaffold_notice" in result
    assert "F.4.6" in result["scaffold_notice"]

    import sqlite3 as sq
    conn = sq.connect(str(db_path))
    conn.row_factory = sq.Row
    row = conn.execute(
        "SELECT * FROM synthesis_runs WHERE id = ?", (result["run_id"],),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["status"] == "queued"
    assert row["trigger_type"] == "manual"
    assert row["trigger_source"] == "api_manual"
    assert row["requester"] == "brain-f4"


def test_trigger_workflow_synthesis_emits_ws_queued_event(runner_with_tmp_db, monkeypatch):
    runner, _manager, _ = runner_with_tmp_db
    captured: list[dict] = []

    async def _capture_emit(event_type, payload):
        captured.append({"event_type": event_type, "payload": payload})

    monkeypatch.setattr(runner, "_ws_emit", _capture_emit)
    asyncio.run(runner.trigger_workflow_synthesis(
        manual=True, trigger_source="api_manual",
    ))
    assert len(captured) == 1
    assert captured[0]["event_type"] == "brain.skill_synthesis_queued"
    assert "run_id" in captured[0]["payload"]
    assert captured[0]["payload"]["trigger_type"] == "manual"
    assert "F.4.3 UI" in captured[0]["payload"]["next_action"]


def test_trigger_workflow_synthesis_manual_default_true(runner_with_tmp_db):
    runner, _manager, _ = runner_with_tmp_db
    result = asyncio.run(runner.trigger_workflow_synthesis())
    assert result["trigger_type"] == "manual"
    assert result["trigger_source"] == "api_manual"


def test_trigger_workflow_synthesis_trigger_source_propagated(runner_with_tmp_db):
    runner, _manager, db_path = runner_with_tmp_db
    result = asyncio.run(runner.trigger_workflow_synthesis(
        manual=False, trigger_source="cron_auto",
    ))
    assert result["trigger_type"] == "cron"
    assert result["trigger_source"] == "cron_auto"

    import sqlite3 as sq
    conn = sq.connect(str(db_path))
    conn.row_factory = sq.Row
    row = conn.execute(
        "SELECT trigger_type, trigger_source FROM synthesis_runs WHERE id = ?",
        (result["run_id"],),
    ).fetchone()
    conn.close()
    assert row["trigger_type"] == "cron"
    assert row["trigger_source"] == "cron_auto"


def test_trigger_workflow_synthesis_requester_brain_f4(runner_with_tmp_db):
    """D7 PIVOT enforce — synthesis_runs.requester='brain-f4' persisted."""
    runner, _manager, db_path = runner_with_tmp_db
    result = asyncio.run(runner.trigger_workflow_synthesis(manual=True))

    import sqlite3 as sq
    conn = sq.connect(str(db_path))
    row = conn.execute(
        "SELECT requester FROM synthesis_runs WHERE id = ?", (result["run_id"],),
    ).fetchone()
    conn.close()
    assert row[0] == "brain-f4"


def test_ensure_synthesis_runs_table_idempotent(runner_with_tmp_db):
    """G9 — ensure_synthesis_runs_table CREATE IF NOT EXISTS safe re-run."""
    from core.skill_proposals import ensure_synthesis_runs_table
    runner, _manager, db_path = runner_with_tmp_db

    # First call (via trigger_workflow_synthesis indirectly).
    asyncio.run(runner.trigger_workflow_synthesis())

    import sqlite3 as sq
    # Second call direct should not error.
    conn = sq.connect(str(db_path))
    ensure_synthesis_runs_table(conn)
    # Verify table + 2 indexes exist.
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='synthesis_runs'"
    ).fetchall()]
    idxs = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='synthesis_runs'"
    ).fetchall()]
    conn.close()
    assert "synthesis_runs" in tables
    assert "idx_synthesis_runs_status" in idxs
    assert "idx_synthesis_runs_queued_at" in idxs
