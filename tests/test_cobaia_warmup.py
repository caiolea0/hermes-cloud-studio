"""F.7 C1 — CobaiaWarmupManager unit tests (12 tests, MOCK-DRIVEN).

All tests use a temp SQLite DB — no production state touched.
LinkedIn execution is stubbed throughout.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from datetime import date, datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from linkedin.config import CobaiaConfig
from linkedin.cobaia_warmup import (
    CobaiaWarmupManager,
    _compute_phase,
    _compute_caps,
    _is_within_working_hours,
)


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test_cobaia.db"


@pytest.fixture
def cfg():
    return CobaiaConfig(
        account_handle="test-cobaia",
        warmup_days=14,
        lurking_days=7,
        weekends_enabled=False,
        working_hours_start="07:00",
        working_hours_end="22:00",
        timezone="America/Cuiaba",
        auto_pause_consecutive_errors=3,
    )


@pytest.fixture
def mgr(cfg, tmp_db):
    return CobaiaWarmupManager(cfg=cfg, db_path=tmp_db)


# ── Phase transition tests ──────────────────────────────────────────────────

def test_warmup_state_starts_lurking_day_0(mgr):
    state = mgr.start_warmup()
    assert state["exists"] is True
    assert state["phase"] == "lurking"
    assert state["current_day"] == 0


def test_phase_transition_lurking_to_ramp_day_7(cfg):
    assert _compute_phase(7, cfg) == "ramp"


def test_phase_transition_ramp_to_normal_day_14(cfg):
    assert _compute_phase(14, cfg) == "normal"


def test_phase_stays_lurking_day_6(cfg):
    assert _compute_phase(6, cfg) == "lurking"


# ── Caps tests ──────────────────────────────────────────────────────────────

def test_caps_zero_connects_during_lurking(cfg):
    caps = _compute_caps("lurking", 0, cfg)
    assert caps["connects"] == 0


def test_caps_views_positive_during_lurking(cfg):
    caps = _compute_caps("lurking", 0, cfg)
    assert caps["views"] > 0


def test_caps_scale_during_ramp(cfg):
    caps_ramp_start = _compute_caps("ramp", 7, cfg)
    caps_ramp_end = _compute_caps("ramp", 13, cfg)
    caps_normal = _compute_caps("normal", 14, cfg)
    # ramp caps should be between lurking and normal
    assert caps_ramp_start["connects"] >= 0
    assert caps_ramp_end["connects"] < caps_normal["connects"]
    assert caps_ramp_end["connects"] > caps_ramp_start["connects"]


def test_caps_full_in_normal(cfg):
    caps = _compute_caps("normal", 14, cfg)
    assert caps["views"] == 70
    assert caps["connects"] == 10
    assert caps["engagements"] == 15


# ── Working hours tests ─────────────────────────────────────────────────────

def test_within_working_hours_07_22():
    cfg = CobaiaConfig(
        working_hours_start="07:00",
        working_hours_end="22:00",
        weekends_enabled=True,  # disable weekend check so we only test hours
        timezone="UTC",
    )
    # Mock datetime to a Tuesday 12:00 UTC
    tuesday_noon = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    with patch("linkedin.cobaia_warmup.datetime") as mock_dt:
        mock_dt.now.return_value = tuesday_noon
        ok, reason = _is_within_working_hours(cfg)
    assert ok is True, f"Expected allowed at 12:00 but got: {reason}"


def test_outside_working_hours_22_07():
    cfg = CobaiaConfig(
        working_hours_start="07:00",
        working_hours_end="22:00",
        weekends_enabled=True,
        timezone="UTC",
    )
    # Mock datetime to a Tuesday 23:00 UTC
    tuesday_night = datetime(2026, 6, 16, 23, 0, tzinfo=timezone.utc)
    with patch("linkedin.cobaia_warmup.datetime") as mock_dt:
        mock_dt.now.return_value = tuesday_night
        ok, reason = _is_within_working_hours(cfg)
    assert ok is False, f"Expected blocked at 23:00 but got: {reason}"


def test_weekend_disabled_skips():
    cfg = CobaiaConfig(
        working_hours_start="07:00",
        working_hours_end="22:00",
        weekends_enabled=False,
        timezone="UTC",
    )
    # Saturday 2026-06-20 12:00 UTC (weekday=5)
    saturday = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)
    with patch("linkedin.cobaia_warmup.datetime") as mock_dt:
        mock_dt.now.return_value = saturday
        ok, reason = _is_within_working_hours(cfg)
    assert ok is False
    assert "fim_de_semana" in reason


# ── Pause/resume tests ──────────────────────────────────────────────────────

def test_pause_endpoint_persists_state(mgr):
    mgr.start_warmup()
    state = mgr.pause(reason="test_pause")
    assert state["phase"] == "paused"
    assert state["pause_reason"] == "test_pause"
    assert state["paused_at"] is not None


def test_resume_endpoint_computes_phase_by_day(mgr, tmp_db):
    mgr.start_warmup()
    mgr.pause(reason="test")
    # Manually set current_day=10 (should resume to 'ramp')
    conn = sqlite3.connect(str(tmp_db))
    conn.row_factory = sqlite3.Row
    conn.execute("UPDATE cobaia_warmup_state SET current_day=10 WHERE account_handle='test-cobaia'")
    conn.commit()
    conn.close()
    state = mgr.resume()
    assert state["phase"] == "ramp"
    assert state["paused_at"] is None


# ── Auto-pause test ─────────────────────────────────────────────────────────

def test_auto_pause_3_consecutive_errors(mgr, tmp_db):
    mgr.start_warmup()
    # Record 3 errors (threshold = 3)
    mgr.record_error()
    mgr.record_error()
    mgr.record_error()
    # daily_check should trigger auto-pause
    # Force last_check_at to yesterday so increment runs
    conn = sqlite3.connect(str(tmp_db))
    conn.row_factory = sqlite3.Row
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    conn.execute(
        "UPDATE cobaia_warmup_state SET last_check_at=? WHERE account_handle='test-cobaia'",
        (yesterday,)
    )
    conn.commit()
    conn.close()
    # Mock to weekday so weekend gate doesn't fire before auto-pause check
    _mock_tuesday = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)
    with patch("linkedin.cobaia_warmup.datetime") as mock_dt:
        mock_dt.now.return_value = _mock_tuesday
        result = mgr.daily_check()
    assert result.get("auto_paused") is True
    state = mgr.get_status()
    assert state["phase"] == "paused"
    assert "errors" in state["pause_reason"]


# ── Idempotency test ────────────────────────────────────────────────────────

def test_daily_check_idempotent_same_day(mgr):
    mgr.start_warmup()
    # Mock to weekday so both calls see the same "today" regardless of real date
    _mock_tuesday = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)
    with patch("linkedin.cobaia_warmup.datetime") as mock_dt:
        mock_dt.now.return_value = _mock_tuesday
        # First call on a fresh state (no last_check_at) — advances
        result1 = mgr.daily_check()
    with patch("linkedin.cobaia_warmup.datetime") as mock_dt:
        mock_dt.now.return_value = _mock_tuesday
        # Second call same day — skips
        result2 = mgr.daily_check()
    assert result2.get("skipped") is True
    assert result2.get("reason") == "already_checked_today"
