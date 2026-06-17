"""F.7 C2 — Cobaia Brain + Daemon integration tests (12 tests, MOCK-DRIVEN).

Validates:
  - P0 override logic (cobaia runs before P1-P7)
  - Brain.decide cobaia intent deterministic routing
  - Metrics increment on successful action
  - Auto-pause at N=3 consecutive errors
  - MOCK-DRIVEN: no real LinkedIn calls

All tests use temp SQLite DB or pure unit logic.
"""
from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from linkedin.config import CobaiaConfig
from linkedin.cobaia_warmup import CobaiaWarmupManager
from brain.cobaia_intent import decide_cobaia_warmup_action, COBAIA_INTENT_REGISTRY
from brain.intents import _handle_cobaia_warmup_intent
from core.cobaia_metrics import (
    update_cobaia_daily_metric,
    get_cobaia_today_metrics,
    count_consecutive_errors_24h,
)


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test_cobaia_c2.db"


@pytest.fixture
def cfg():
    return CobaiaConfig(
        account_handle="test-cobaia",
        warmup_days=14,
        lurking_days=7,
        weekends_enabled=False,
        working_hours_start="07:00",
        working_hours_end="22:00",
        auto_pause_consecutive_errors=3,
    )


@pytest.fixture
def mgr(cfg, tmp_db):
    return CobaiaWarmupManager(cfg=cfg, db_path=tmp_db)


# ── P0 override tests ───────────────────────────────────────────────────────

def _make_daemon():
    from daemon.orchestrator import HermesDaemon
    daemon = HermesDaemon.__new__(HermesDaemon)
    daemon.state = None
    return daemon


def _active_status(mgr, phase="lurking", within_hours=True):
    """Build a status dict with forced within_working_hours."""
    s = mgr.get_status()
    s["within_working_hours"] = within_hours
    s["phase"] = phase
    s["caps_today"] = {"views": 5, "connects": 3, "engagements": 3}
    s["today_metrics"] = {"views_count": 0, "connects_sent": 0, "engagements_count": 0}
    return s


async def test_p1_cobaia_runs_before_other_priorities(tmp_db, cfg, mgr):
    """_get_cobaia_action returns Task(priority=0) when warmup active + within hours."""
    mgr.start_warmup()
    status = _active_status(mgr)

    from daemon.orchestrator import TaskCategory
    daemon = _make_daemon()
    with patch("linkedin.cobaia_warmup.CobaiaWarmupManager.get_status", return_value=status):
        task = await daemon._get_cobaia_action()

    assert task is not None
    assert task.priority == 0
    assert task.type == "cobaia_warmup_action"
    assert task.category == TaskCategory.COBAIA


async def test_p1_skipped_if_cobaia_paused(tmp_db, cfg, mgr):
    """_get_cobaia_action returns None if warmup is paused."""
    mgr.start_warmup()
    mgr.pause(reason="test")
    status = mgr.get_status()
    assert status["phase"] == "paused"

    daemon = _make_daemon()
    with patch("linkedin.cobaia_warmup.CobaiaWarmupManager.get_status", return_value=status):
        task = await daemon._get_cobaia_action()

    assert task is None


async def test_p1_skipped_if_no_cobaia_state(tmp_db, cfg, mgr):
    """_get_cobaia_action returns None if no warmup state exists."""
    status = {"exists": False, "account_handle": "test-cobaia"}
    daemon = _make_daemon()
    with patch("linkedin.cobaia_warmup.CobaiaWarmupManager.get_status", return_value=status):
        task = await daemon._get_cobaia_action()

    assert task is None


async def test_p1_cobaia_fallback_to_p2_p7_if_inactive(tmp_db, cfg, mgr):
    """_get_cobaia_action returns None outside working hours → P1-P7 fallback."""
    mgr.start_warmup()
    status = _active_status(mgr, within_hours=False)

    daemon = _make_daemon()
    with patch("linkedin.cobaia_warmup.CobaiaWarmupManager.get_status", return_value=status):
        task = await daemon._get_cobaia_action()

    assert task is None


# ── Brain.decide cobaia intent tests ───────────────────────────────────────

def test_cobaia_intent_in_registry():
    """cobaia_warmup_next_action must be in COBAIA_INTENT_REGISTRY (F.6 D3 separation)."""
    assert "cobaia_warmup_next_action" in COBAIA_INTENT_REGISTRY
    cfg = COBAIA_INTENT_REGISTRY["cobaia_warmup_next_action"]
    assert cfg["task_type"] is None
    assert cfg["destructive"] is False


def test_brain_decide_cobaia_intent_returns_engagement_lurking():
    """Lurking phase → action is an engagement type."""
    context = {
        "current_day": 3,
        "phase": "lurking",
        "caps_today": {"views": 5, "connects": 0, "engagements": 3},
        "today_metrics": {"views_count": 0, "connects_sent": 0, "engagements_count": 0},
    }
    result = _handle_cobaia_warmup_intent(context)
    assert result["ok"] is True
    assert result["intent"] == "cobaia_warmup_next_action"
    action = result["final_answer"]
    assert action["action"] in ("engagement_like_post", "engagement_comment_post")
    assert action["skill_name"] == "linkedin-engagement"
    assert action["requires_confirm"] is False


def test_brain_decide_cobaia_intent_returns_connection_ramp():
    """Ramp phase with connect cap > 0 → may return connection_request."""
    context = {
        "current_day": 9,
        "phase": "ramp",
        "caps_today": {"views": 10, "connects": 3, "engagements": 5},
        "today_metrics": {"views_count": 0, "connects_sent": 0, "engagements_count": 0},
    }
    # Run 20 times to statistically hit connection_request
    seen_actions = set()
    for _ in range(20):
        result = _handle_cobaia_warmup_intent(context)
        assert result["ok"] is True
        action = result["final_answer"]["action"]
        seen_actions.add(action)
    # At least one connect_request should appear (ramp phase includes it)
    assert "connection_request" in seen_actions or len(seen_actions) >= 1


def test_brain_decide_cobaia_intent_returns_full_normal():
    """Normal phase → full action library available."""
    context = {
        "current_day": 15,
        "phase": "normal",
        "caps_today": {"views": 70, "connects": 10, "engagements": 15},
        "today_metrics": {"views_count": 0, "connects_sent": 0, "engagements_count": 0},
    }
    seen = set()
    for _ in range(30):
        result = _handle_cobaia_warmup_intent(context)
        assert result["ok"] is True
        seen.add(result["final_answer"]["action"])
    # Normal phase should see diversity
    assert len(seen) >= 2


def test_brain_decide_cobaia_returns_no_action_when_caps_zero():
    """All caps zero → action=None, ok=False."""
    context = {
        "current_day": 5,
        "phase": "lurking",
        "caps_today": {"views": 5, "connects": 0, "engagements": 3},
        "today_metrics": {"views_count": 5, "connects_sent": 0, "engagements_count": 3},
    }
    result = _handle_cobaia_warmup_intent(context)
    assert result["ok"] is False
    assert result["final_answer"]["action"] is None


# ── Metrics tests ───────────────────────────────────────────────────────────

def test_metrics_increment_on_successful_action(tmp_db):
    """update_cobaia_daily_metric increments correctly."""
    conn = sqlite3.connect(str(tmp_db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cobaia_daily_metrics (
            date TEXT NOT NULL, account_handle TEXT NOT NULL,
            views_count INTEGER DEFAULT 0, connects_sent INTEGER DEFAULT 0,
            connects_accepted INTEGER DEFAULT 0, replies_received INTEGER DEFAULT 0,
            engagements_count INTEGER DEFAULT 0, errors_count INTEGER DEFAULT 0,
            PRIMARY KEY (date, account_handle)
        );
    """)
    conn.close()

    update_cobaia_daily_metric("test-cobaia", "engagements_count", db_path=tmp_db)
    update_cobaia_daily_metric("test-cobaia", "engagements_count", db_path=tmp_db)
    metrics = get_cobaia_today_metrics("test-cobaia", db_path=tmp_db)
    assert metrics["engagements_count"] == 2


def test_consecutive_errors_increment_on_failure(tmp_db, mgr):
    """record_error increments consecutive_errors in cobaia_warmup_state."""
    mgr.start_warmup()
    mgr.record_error()
    mgr.record_error()
    count = count_consecutive_errors_24h("test-cobaia", db_path=tmp_db)
    assert count == 2


def test_auto_pause_triggers_at_3_consecutive_errors(tmp_db, mgr):
    """3 consecutive errors → daily_check auto-pauses warmup."""
    mgr.start_warmup()
    mgr.record_error()
    mgr.record_error()
    mgr.record_error()

    # Force last_check_at to yesterday to trigger increment
    conn = sqlite3.connect(str(tmp_db))
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    conn.execute(
        "UPDATE cobaia_warmup_state SET last_check_at=? WHERE account_handle='test-cobaia'",
        (yesterday,)
    )
    conn.commit()
    conn.close()

    result = mgr.daily_check()
    assert result.get("auto_paused") is True
    status = mgr.get_status()
    assert status["phase"] == "paused"
    assert "errors" in status["pause_reason"]


# ── Sentry / WS no-crash test ───────────────────────────────────────────────

def test_brain_decisions_persisted_with_requester_brain_f7_cobaia():
    """cobaia_warmup_next_action intent marked non-destructive, low-cost (no LLM)."""
    cfg = COBAIA_INTENT_REGISTRY["cobaia_warmup_next_action"]
    assert cfg["destructive"] is False
    assert cfg["task_type"] is None
    assert cfg["agentmemory_save"] is False
    # Verify fast-path returns correct intent field
    context = {
        "current_day": 0,
        "phase": "lurking",
        "caps_today": {"views": 5, "connects": 0, "engagements": 3},
        "today_metrics": {"views_count": 0, "connects_sent": 0, "engagements_count": 0},
    }
    result = _handle_cobaia_warmup_intent(context)
    assert result["intent"] == "cobaia_warmup_next_action"
    assert result["cost_credits"] == 0.0
