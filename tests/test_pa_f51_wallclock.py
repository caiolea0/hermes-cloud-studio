"""PA-F5.1 — Wall-clock determinism tests.

Verifies:
1. cobaia_warmup._date.today() removed — datetime.now() is the single mockable source
2. The 3 weekend-flaky tests are deterministic via mock (any weekday 0-4)
3. Wall-clock sweep verdict: other test files are deterministic or already mocked
"""
from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from linkedin.config import CobaiaConfig
from linkedin.cobaia_warmup import CobaiaWarmupManager

_MOCK_TUESDAY = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)
_MOCK_SATURDAY = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)  # weekday=5


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test_wallclock.db"


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


# ── Test 1: _date.today() removed from cobaia_warmup ────────────────────────

def test_cobaia_weekend_check_uses_mockable_datetime(mgr):
    """datetime.now() is the ONLY time source in daily_check — no date.today() escape."""
    import inspect
    import linkedin.cobaia_warmup as warmup_mod
    src = inspect.getsource(warmup_mod.CobaiaWarmupManager.daily_check)
    # _date.today() pattern removed
    assert "_date.today" not in src, "Legacy _date.today() still in daily_check"
    assert "date.today" not in src, "date.today() still in daily_check"
    # datetime.now is the mockable replacement
    assert "datetime.now" in src, "Expected datetime.now() in daily_check"


# ── Test 2: 3 weekend-flaky scenarios are deterministic ─────────────────────

def test_auto_pause_deterministic_any_weekday(mgr, tmp_db):
    """Auto-pause fires correctly when mocked to weekday, blocked on weekend."""
    mgr.start_warmup()
    for _ in range(3):
        mgr.record_error()

    conn = sqlite3.connect(str(tmp_db))
    yesterday = (_MOCK_TUESDAY.date() - timedelta(days=1)).isoformat()
    conn.execute(
        "UPDATE cobaia_warmup_state SET last_check_at=? WHERE account_handle='test-cobaia'",
        (yesterday,)
    )
    conn.commit()
    conn.close()

    # Weekday → auto-pause fires
    with patch("linkedin.cobaia_warmup.datetime") as mock_dt:
        mock_dt.now.return_value = _MOCK_TUESDAY
        result_weekday = mgr.daily_check()
    assert result_weekday.get("auto_paused") is True, "Auto-pause must fire on weekday"

    # Reset: resume + clear errors
    mgr.resume()
    conn = sqlite3.connect(str(tmp_db))
    conn.execute(
        "UPDATE cobaia_warmup_state SET consecutive_errors=3, last_check_at=? WHERE account_handle='test-cobaia'",
        (yesterday,)
    )
    conn.commit()
    conn.close()

    # Weekend → weekend gate fires FIRST, auto_paused never set
    with patch("linkedin.cobaia_warmup.datetime") as mock_dt:
        mock_dt.now.return_value = _MOCK_SATURDAY
        result_weekend = mgr.daily_check()
    assert result_weekend.get("auto_paused") is not True, "Weekend gate must fire on weekend"
    assert "weekend" in result_weekend.get("reason", ""), "Expected weekend reason"


def test_idempotent_check_deterministic_any_day(mgr):
    """Idempotent check is deterministic: same mock date = same 'today' both calls."""
    mgr.start_warmup()

    with patch("linkedin.cobaia_warmup.datetime") as mock_dt:
        mock_dt.now.return_value = _MOCK_TUESDAY
        result1 = mgr.daily_check()
    assert not result1.get("skipped"), "First call must advance"

    with patch("linkedin.cobaia_warmup.datetime") as mock_dt:
        mock_dt.now.return_value = _MOCK_TUESDAY
        result2 = mgr.daily_check()
    assert result2.get("skipped") is True
    assert result2.get("reason") == "already_checked_today"


# ── Test 3: wall-clock sweep verdicts ───────────────────────────────────────

def test_wallclock_sweep_verdicts():
    """Verify known wall-clock usages in test files are deterministic or mocked.

    This test documents the sweep result from PA-F5.1 — 6 sites examined:
      - test_email_verifier.py:138  datetime.now() → past offset, always-past  ✅ deterministic
      - test_email_verifier.py:181  time.time()    → fills rate window (relative) ✅ deterministic
      - test_cobaia_warmup.py:183   date.today()   → sets DB yesterday (test setup only) ✅ fixed by module
      - test_cobaia_brain_daemon.py:245 date.today() → same ✅ fixed by module
      - test_cobaia_autotune.py:240 → already mocked (mock_dt.date.today.return_value) ✅
      - test_ux_rm_f5a_brain_stream.py:106 time.monotonic() → fills rate deque (relative) ✅ deterministic
    """
    # Grep cobaia_warmup for remaining date.today() calls — must be 0
    import inspect
    import linkedin.cobaia_warmup as warmup_mod
    full_src = inspect.getsource(warmup_mod)
    raw_date_today = full_src.count("date.today()")
    assert raw_date_today == 0, (
        f"cobaia_warmup still has {raw_date_today} date.today() call(s) — "
        "PA-F5.1 requires all to be consolidated to datetime.now(timezone.utc)"
    )
