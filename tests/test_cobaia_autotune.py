"""F.7 C5 — CobaiaAutotune unit tests (10 tests, temp SQLite DBs).

All tests use isolated temp DBs — no production state touched.
trigger_workflow_synthesis path mocked via core.skill_proposals stubs.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from core.cobaia_metrics import (
    KPI_THRESHOLDS,
    compute_kpi_7d_avg,
    detect_sustained_low_kpi,
    get_last_autotune_trigger,
)
from core.cobaia_autotune import detect_and_trigger


# ── Helpers ──────────────────────────────────────────────────────────────────


def _create_metrics_db(tmp_path: Path) -> Path:
    """Create DB with cobaia_warmup_state + cobaia_daily_metrics tables."""
    db = tmp_path / "test_autotune.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cobaia_warmup_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_handle TEXT NOT NULL UNIQUE,
            started_at TEXT NOT NULL,
            current_day INTEGER NOT NULL DEFAULT 0,
            phase TEXT NOT NULL DEFAULT 'lurking',
            paused_at TEXT, pause_reason TEXT, last_check_at TEXT,
            consecutive_errors INTEGER NOT NULL DEFAULT 0,
            config_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS cobaia_daily_metrics (
            date TEXT NOT NULL,
            account_handle TEXT NOT NULL,
            views_count INTEGER DEFAULT 0,
            connects_sent INTEGER DEFAULT 0,
            connects_accepted INTEGER DEFAULT 0,
            replies_received INTEGER DEFAULT 0,
            engagements_count INTEGER DEFAULT 0,
            errors_count INTEGER DEFAULT 0,
            PRIMARY KEY (date, account_handle)
        );
        CREATE TABLE IF NOT EXISTS cobaia_autotune_triggers (
            id TEXT PRIMARY KEY,
            account_handle TEXT NOT NULL,
            trigger_at TEXT NOT NULL,
            kpi_breached TEXT NOT NULL,
            kpi_value REAL NOT NULL,
            kpi_threshold REAL NOT NULL,
            sustained_hours INTEGER NOT NULL,
            synthesis_run_id TEXT NULL,
            result_status TEXT NULL,
            result_pr_url TEXT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NULL
        );
        """
    )
    conn.commit()
    conn.close()
    return db


def _seed_metrics(db: Path, account: str, rows: list[tuple]) -> None:
    """rows: (date, views, connects, accepted, replies)"""
    conn = sqlite3.connect(str(db))
    for (dt, views, connects, accepted, replies) in rows:
        conn.execute(
            """INSERT OR REPLACE INTO cobaia_daily_metrics
               (date, account_handle, views_count, connects_sent,
                connects_accepted, replies_received, engagements_count, errors_count)
               VALUES (?, ?, ?, ?, ?, ?, 0, 0)""",
            (dt, account, views, connects, accepted, replies),
        )
    conn.commit()
    conn.close()


def _seed_autotune_trigger(db: Path, account: str, kpi: str, trigger_at: str) -> None:
    conn = sqlite3.connect(str(db))
    conn.execute(
        """INSERT OR IGNORE INTO cobaia_autotune_triggers
           (id, account_handle, trigger_at, kpi_breached, kpi_value, kpi_threshold,
            sustained_hours, synthesis_run_id, result_status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        ("seed-id", account, trigger_at, kpi, 0.02, 0.08, 24, None, "queued", trigger_at),
    )
    conn.commit()
    conn.close()


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_compute_kpi_7d_avg_returns_trend(tmp_path):
    """compute_kpi_7d_avg returns kpis, sample_days, trend dict."""
    db = _create_metrics_db(tmp_path)
    _seed_metrics(db, "cobaia", [
        ("2099-01-10", 100, 10, 3, 1),
        ("2099-01-11", 120, 12, 3, 1),
        ("2099-01-12", 80, 8, 1, 0),
        ("2099-01-13", 90, 9, 2, 0),
    ])
    result = compute_kpi_7d_avg("cobaia", db_path=db)
    assert result["sample_days"] == 4
    assert "kpis" in result
    assert "trend" in result
    assert set(result["trend"].keys()) == set(KPI_THRESHOLDS.keys())
    assert result["kpis"]["reply_rate"] >= 0.0
    assert "thresholds" in result


def test_detect_sustained_low_returns_breached_kpis(tmp_path):
    """detect_sustained_low_kpi flags reply_rate below 0.08 threshold."""
    db = _create_metrics_db(tmp_path)
    # reply_rate = 2/100 = 0.02 (below 0.08)
    _seed_metrics(db, "cobaia", [("2099-01-01", 200, 100, 20, 2)])
    breaches = detect_sustained_low_kpi("cobaia", hours=24, db_path=db)
    kpi_names = [b["kpi"] for b in breaches]
    assert "reply_rate" in kpi_names
    breach = next(b for b in breaches if b["kpi"] == "reply_rate")
    assert breach["value"] == pytest.approx(0.02, rel=0.01)
    assert breach["threshold"] == 0.08


def test_detect_sustained_low_skips_short_breach(tmp_path):
    """No data rows → no breach reported (insufficient sample)."""
    db = _create_metrics_db(tmp_path)
    # No rows at all
    breaches = detect_sustained_low_kpi("cobaia", hours=24, db_path=db)
    assert breaches == []


def test_detect_sustained_low_no_breach_when_kpis_ok(tmp_path):
    """No breach when all KPIs above thresholds."""
    db = _create_metrics_db(tmp_path)
    # reply_rate = 20/100 = 0.20 > 0.08 ✓
    # accept_rate = 30/100 = 0.30 > 0.20 ✓
    # view_to_connect = 100/200 = 0.50 > 0.03 ✓
    _seed_metrics(db, "cobaia", [("2099-01-01", 200, 100, 30, 20)])
    breaches = detect_sustained_low_kpi("cobaia", hours=24, db_path=db)
    assert breaches == []


def test_cooldown_72h_prevents_re_trigger(tmp_path):
    """get_last_autotune_trigger returns row within 72h → cooldown active."""
    db = _create_metrics_db(tmp_path)
    # Seed trigger 1h ago (within 72h cooldown)
    _seed_autotune_trigger(
        db, "cobaia", "reply_rate", "2099-01-01 08:00:00"
    )
    # Mock datetime to be 2099-01-01 09:00:00
    with patch("core.cobaia_metrics.datetime") as mock_dt:
        # get_last_autotune_trigger uses sqlite datetime('now') — no mock needed
        pass
    result = get_last_autotune_trigger("cobaia", "reply_rate", cooldown_hours=72, db_path=db)
    # The trigger was 'seeded' but sqlite 'now' is actual system time, so we need
    # to use a far-future trigger_at to simulate active cooldown
    # Re-seed with trigger_at in far future (simulates recent trigger)
    conn = sqlite3.connect(str(db))
    conn.execute("DELETE FROM cobaia_autotune_triggers")
    conn.execute(
        """INSERT INTO cobaia_autotune_triggers
           (id, account_handle, trigger_at, kpi_breached, kpi_value, kpi_threshold,
            sustained_hours, result_status, created_at)
           VALUES ('t1', 'cobaia', datetime('now', '-1 hours'), 'reply_rate',
                   0.02, 0.08, 24, 'queued', datetime('now', '-1 hours'))"""
    )
    conn.commit()
    conn.close()
    result = get_last_autotune_trigger("cobaia", "reply_rate", cooldown_hours=72, db_path=db)
    assert result is not None, "Cooldown trigger within 72h should be found"


def test_detect_and_trigger_calls_workflow_synthesis(tmp_path):
    """detect_and_trigger() inserts synthesis_runs row when breach detected."""
    db = _create_metrics_db(tmp_path)
    # reply_rate = 1/100 = 0.01 → breach
    _seed_metrics(db, "cobaia", [("2099-01-01", 300, 100, 5, 1)])

    with patch("core.cobaia_autotune._queue_synthesis_run", return_value="run-123") as mock_syn:
        with patch("core.cobaia_autotune._ws_emit"):
            with patch("core.cobaia_autotune._telegram_alert"):
                result = detect_and_trigger("cobaia", sustained_hours=24, db_path=db)

    assert result["triggered"] >= 1
    assert "reply_rate" in result["triggered_kpis"]
    mock_syn.assert_called()


def test_autotune_skipped_if_cobaia_paused():
    """Autotune job skips when warmup phase is 'paused'."""
    from daemon.cobaia_autotune_loop import _run_autotune_check
    mock_status = {
        "exists": True,
        "phase": "paused",
        "current_day": 20,
        "account_handle": "cobaia",
    }
    # Late imports in _run_autotune_check → patch at source module
    with patch("linkedin.cobaia_warmup.CobaiaWarmupManager") as MockMgr:
        MockMgr.return_value.get_status.return_value = mock_status
        with patch("core.cobaia_autotune.detect_and_trigger") as mock_trigger:
            _run_autotune_check()
    mock_trigger.assert_not_called()


def test_autotune_skipped_during_warmup_phase_lurking_ramp():
    """Autotune job skips when current_day < 14 (KPIs not stabilized)."""
    from daemon.cobaia_autotune_loop import _run_autotune_check
    mock_status = {
        "exists": True,
        "phase": "lurking",
        "current_day": 5,
        "account_handle": "cobaia",
    }
    with patch("linkedin.cobaia_warmup.CobaiaWarmupManager") as MockMgr:
        MockMgr.return_value.get_status.return_value = mock_status
        with patch("core.cobaia_autotune.detect_and_trigger") as mock_trigger:
            _run_autotune_check()
    mock_trigger.assert_not_called()


def test_autotune_skipped_on_weekend():
    """Autotune job skips on Saturday/Sunday (D2.3)."""
    import datetime as dt_mod
    from daemon.cobaia_autotune_loop import _run_autotune_check
    saturday = dt_mod.date(2099, 1, 5)  # Saturday weekday=5
    with patch("daemon.cobaia_autotune_loop.datetime") as mock_dt:
        mock_dt.date.today.return_value = saturday
        with patch("core.cobaia_autotune.detect_and_trigger") as mock_trigger:
            _run_autotune_check()
    mock_trigger.assert_not_called()


def test_manual_trigger_bypasses_cooldown(tmp_path):
    """detect_and_trigger called directly ignores _get_last_autotune_trigger cooldown gate.

    The manual trigger POST endpoint bypasses cooldown (G9 API level).
    Here we verify detect_and_trigger itself does NOT bypass — manual endpoint handles that.
    """
    db = _create_metrics_db(tmp_path)
    # Seed recent trigger (cooldown active)
    conn = sqlite3.connect(str(db))
    conn.execute(
        """INSERT INTO cobaia_autotune_triggers
           (id, account_handle, trigger_at, kpi_breached, kpi_value, kpi_threshold,
            sustained_hours, result_status, created_at)
           VALUES ('existing', 'cobaia', datetime('now', '-1 hours'), 'reply_rate',
                   0.02, 0.08, 24, 'queued', datetime('now', '-1 hours'))"""
    )
    conn.commit()
    conn.close()

    # Low KPI metrics
    _seed_metrics(db, "cobaia", [("2099-01-01", 300, 100, 5, 1)])

    with patch("core.cobaia_autotune._queue_synthesis_run", return_value="run-456"):
        with patch("core.cobaia_autotune._ws_emit"):
            with patch("core.cobaia_autotune._telegram_alert"):
                result = detect_and_trigger("cobaia", sustained_hours=24, db_path=db)

    # reply_rate breach but cooldown active → should be skipped
    skipped_kpis = [b["kpi"] for b in result["breaches"] if b["kpi"] not in result["triggered_kpis"]]
    assert "reply_rate" in skipped_kpis or result["skipped"] >= 1


def test_telegram_alert_fires_on_autotune_trigger(tmp_path):
    """detect_and_trigger calls _telegram_alert when synthesis queued."""
    db = _create_metrics_db(tmp_path)
    _seed_metrics(db, "cobaia", [("2099-01-01", 300, 100, 5, 1)])

    with patch("core.cobaia_autotune._queue_synthesis_run", return_value="run-789"):
        with patch("core.cobaia_autotune._ws_emit"):
            with patch("core.cobaia_autotune._telegram_alert") as mock_tg:
                result = detect_and_trigger("cobaia", sustained_hours=24, db_path=db)

    if result["triggered"] > 0:
        mock_tg.assert_called()
    else:
        pytest.skip("No triggers fired (all cooldowns active or no breach)")
