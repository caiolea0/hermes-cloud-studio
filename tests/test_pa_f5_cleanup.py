"""PA-F5 — Test debt + dead code cleanup.

Tests (8):
1. cobaia_intent args has NO stub key (dead field removed)
2. hermes-skills stub is nested metadata (not top-level runtime gate)
3. orchestrator run_forever processes one task then stops
4. orchestrator run_forever sleeps 30s when decide returns None
5. GET /api/brain/intents returns count + intents list
6. No duplicate pipeline ab_group index across migrations
7. Inbox index dup is idempotent — both sources identical
8. All 5 orphan endpoints exist with documented callers (not removed)
"""
from __future__ import annotations

import asyncio
import re
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).parent.parent
MIGRATIONS = ROOT / "migrations"


# ─────────────────────────────────────────────────────────────────────────────
# ITEM 1A — stub:True removed from cobaia_intent args
# ─────────────────────────────────────────────────────────────────────────────

def test_cobaia_intent_args_no_stub_key():
    """decide_cobaia_warmup_action must NOT have 'stub' in returned args (dead field removed)."""
    from brain.cobaia_intent import decide_cobaia_warmup_action

    context = {
        "current_day": 3,
        "phase": "lurking",
        "caps_today": {"views": 5, "connects": 0, "engagements": 3},
        "today_metrics": {"views_count": 0, "connects_sent": 0, "engagements_count": 0},
    }
    result = decide_cobaia_warmup_action(context)
    args = result.get("args", {})
    assert "stub" not in args, (
        f"'stub' key must be removed from cobaia_intent args — found: {args}"
    )
    # Verify expected keys still present
    assert "phase" in args, "args must still have 'phase'"
    assert "day" in args, "args must still have 'day'"


# ─────────────────────────────────────────────────────────────────────────────
# ITEM 1B — hermes-skills stub is descriptive metadata (nested, not top-level)
# ─────────────────────────────────────────────────────────────────────────────

def test_hermes_skills_stub_is_nested_not_top_level():
    """hermes-skills server.py 'stub' key must be inside llm_response, NOT at top-level return."""
    src = (ROOT / "mcps" / "hermes-skills" / "server.py").read_text(encoding="utf-8")
    # Find the mock_llm return block
    # Should have stub inside llm_response dict
    assert '"stub": True' in src or "'stub': True" in src, "stub key must remain as descriptive metadata"
    # Verify it's nested inside llm_response (not a bare top-level key)
    # Pattern: "llm_response": { ... "stub": True ... }
    llm_response_block = re.search(
        r'"llm_response"\s*:\s*\{[^}]*"stub"\s*:', src, re.DOTALL
    )
    assert llm_response_block is not None, (
        "stub must be INSIDE llm_response dict — it's descriptive metadata, not a runtime gate"
    )


# ─────────────────────────────────────────────────────────────────────────────
# ITEM 2 — daemon run_forever loop
# ─────────────────────────────────────────────────────────────────────────────

def _make_daemon_bare():
    """Create HermesDaemon without calling __init__ (skips _init_db)."""
    from daemon.orchestrator import HermesDaemon, DaemonState, DaemonStats
    daemon = HermesDaemon.__new__(HermesDaemon)
    daemon.state = DaemonState.IDLE
    daemon._running = False
    daemon.paused_until = None
    daemon.consecutive_errors = 0
    daemon.stats_today = DaemonStats()
    daemon.last_heartbeat = None
    return daemon


@pytest.mark.asyncio
async def test_orchestrator_run_forever_processes_one_task():
    """run_forever: when decide_next_action returns a Task, execute_task is called and state → WORKING → IDLE."""
    from daemon.orchestrator import Task, TaskCategory, DaemonState

    daemon = _make_daemon_bare()
    task = Task(
        type="cobaia_warmup_action",
        description="test task",
        priority=0,
        category=TaskCategory.COBAIA,
    )

    call_log: list[str] = []

    async def fake_set_state(new_state, task=None):
        call_log.append(f"set_state:{new_state.value}")

    async def fake_decide():
        # After first real call, stop the loop
        daemon._running = False
        return task

    async def fake_execute(t):
        call_log.append("execute_task")
        return True

    async def fake_log_decision(**kwargs):
        call_log.append("log_decision")

    daemon.set_state = fake_set_state
    daemon.decide_next_action = fake_decide
    daemon.execute_task = fake_execute
    daemon.log_decision = fake_log_decision

    with (
        patch("daemon.orchestrator.HermesDaemon._should_sleep", return_value=False),
        patch("daemon.orchestrator.HermesDaemon._check_daily_reset"),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        await daemon.run_forever()

    assert "execute_task" in call_log, "execute_task must be called when task returned"
    assert any("working" in s for s in call_log), "state must transition through WORKING"
    assert any("idle" in s for s in call_log), "state must return to IDLE after task"


@pytest.mark.asyncio
async def test_orchestrator_run_forever_idle_when_no_task():
    """run_forever: when decide_next_action returns None, loop sleeps 30s and returns to IDLE."""
    from daemon.orchestrator import DaemonState

    daemon = _make_daemon_bare()
    call_log: list[str] = []

    async def fake_set_state(new_state, task=None):
        call_log.append(f"set_state:{new_state.value}")

    async def fake_decide():
        daemon._running = False
        return None

    daemon.set_state = fake_set_state
    daemon.decide_next_action = fake_decide

    sleep_calls: list[float] = []

    async def fake_sleep(secs: float):
        sleep_calls.append(secs)

    with (
        patch("daemon.orchestrator.HermesDaemon._should_sleep", return_value=False),
        patch("daemon.orchestrator.HermesDaemon._check_daily_reset"),
        patch("asyncio.sleep", side_effect=fake_sleep),
    ):
        await daemon.run_forever()

    assert 30 in sleep_calls or any(s >= 30 for s in sleep_calls), (
        "run_forever must sleep ≥30s when no task available"
    )
    assert not any("working" in s for s in call_log), "no WORKING state when no task"


# ─────────────────────────────────────────────────────────────────────────────
# ITEM 2 — brain list_intents endpoint
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def brain_client():
    """TestClient for brain router tests."""
    from server import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth_headers():
    from core.state import AUTH_TOKEN
    return {"X-Hermes-Token": AUTH_TOKEN}


def test_brain_list_intents_returns_registry(brain_client, auth_headers):
    """GET /api/brain/intents returns count + list with required fields."""
    r = brain_client.get("/api/brain/intents", headers=auth_headers)
    assert r.status_code == 200, f"list_intents failed: {r.text}"
    data = r.json()
    assert "count" in data, "response must have 'count'"
    assert "intents" in data, "response must have 'intents'"
    assert isinstance(data["count"], int), "'count' must be int"
    assert data["count"] >= 6, "INTENT_REGISTRY must have at least 6 canonical intents (F.6 D3)"
    assert isinstance(data["intents"], list), "'intents' must be list"
    # Verify schema of each intent entry
    for intent in data["intents"]:
        for field in ("name", "description", "task_type", "destructive", "tools_available"):
            assert field in intent, f"intent entry missing field '{field}': {intent}"


# ─────────────────────────────────────────────────────────────────────────────
# ITEM 3 — Dup index verification
# ─────────────────────────────────────────────────────────────────────────────

def test_no_duplicate_pipeline_ab_group_index_across_migrations():
    """idx_pipeline_runs_granular_ab_group must appear only once as actual SQL (not in comments)."""
    index_name = "idx_pipeline_runs_granular_ab_group"
    sql_occurrences = []
    for sql_file in MIGRATIONS.glob("*.sql"):
        content = sql_file.read_text(encoding="utf-8")
        for lineno, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            # Only count non-comment lines with the index name
            if index_name in stripped and not stripped.startswith("--"):
                sql_occurrences.append((sql_file.name, lineno, stripped[:80]))
    assert len(sql_occurrences) == 1, (
        f"idx_pipeline_runs_granular_ab_group must appear exactly once as SQL "
        f"(not in comments) across migrations; found {len(sql_occurrences)}: {sql_occurrences}"
    )


def test_inbox_index_dup_is_idempotent():
    """idx_inbox_replies_handled in orchestrator._init_db matches migration — both IF NOT EXISTS (safe dup)."""
    orch_src = (ROOT / "daemon" / "orchestrator.py").read_text(encoding="utf-8")
    mig_src = (MIGRATIONS / "2026_06_daemon_sequence_inbox.sql").read_text(encoding="utf-8")

    orch_has = "idx_inbox_replies_handled" in orch_src
    mig_has = "idx_inbox_replies_handled" in mig_src
    assert orch_has and mig_has, (
        "idx_inbox_replies_handled must be in both orchestrator._init_db and migration (idempotent dup)"
    )
    # Both must use CREATE INDEX IF NOT EXISTS (not bare CREATE INDEX)
    assert "CREATE INDEX IF NOT EXISTS idx_inbox_replies_handled" in orch_src, (
        "orchestrator._init_db must use IF NOT EXISTS for inbox index"
    )
    assert "CREATE INDEX IF NOT EXISTS idx_inbox_replies_handled" in mig_src, (
        "migration must use IF NOT EXISTS for inbox index"
    )
    # Verify dup is documented in orchestrator
    assert "also defined in migrations" in orch_src or "idempotent" in orch_src, (
        "orchestrator._init_db must document the intentional dup with a comment"
    )


# ─────────────────────────────────────────────────────────────────────────────
# ITEM 4 — Orphan endpoints triaged (documented, not removed)
# ─────────────────────────────────────────────────────────────────────────────

def test_orphan_endpoints_documented_not_removed():
    """All 5 orphan endpoints must exist with caller/intent documentation in their files."""
    brain_src = (ROOT / "api" / "brain.py").read_text(encoding="utf-8")
    templates_src = (ROOT / "api" / "templates.py").read_text(encoding="utf-8")
    sequences_src = (ROOT / "api" / "sequences.py").read_text(encoding="utf-8")

    # 1. POST /api/brain/decide — must exist + documented as backend-to-backend
    assert '@router.post("/decide"' in brain_src, "brain /decide endpoint must exist"
    assert "backend-to-backend" in brain_src or "daemon" in brain_src, (
        "brain /decide must document its backend-caller context"
    )

    # 2. POST /api/brain/replay — must exist + documented as admin/debug
    assert '@router.post("/replay/{run_id}")' in brain_src, "brain /replay endpoint must exist"
    assert "Admin" in brain_src or "admin" in brain_src or "debug" in brain_src, (
        "brain /replay must document admin/debug context"
    )

    # 3. GET /api/brain/intents — must exist + documented
    assert '@router.get("/intents")' in brain_src, "brain /intents endpoint must exist"
    assert "no dashboard SPA caller" in brain_src or "Admin" in brain_src or "debug" in brain_src, (
        "brain /intents must document no-frontend-caller context"
    )

    # 4. POST /api/templates/render — must exist + documented
    assert '@router.post("/api/templates/render")' in templates_src, "/templates/render must exist"
    assert "Internal" in templates_src or "internal" in templates_src or "preview" in templates_src, (
        "/templates/render must document its internal/preview use"
    )

    # 5. DELETE /api/sequences/{seq_id} — must exist + documented
    assert '@router.delete("/api/sequences/{seq_id}")' in sequences_src, "DELETE /sequences must exist"
    assert "CLI" in sequences_src or "admin" in sequences_src or "archive" in sequences_src, (
        "DELETE /sequences must document its soft-delete / CLI context"
    )
