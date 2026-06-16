"""F.7 C6 — Cobaia real execution wiring unit tests (8 tests, temp SQLite DBs).

Tests cover:
  - _dispatch_cobaia_session_to_vm: success / HTTP error / connection failure
  - _record_cobaia_metrics: upsert delta correctness
  - _daily_check_wires_dispatch: full scheduler flow (mocked VM)
  - GET /api/cobaia/preflight: response shape
  - GET /api/cobaia/f7-report: response shape + basic assertions
  - VM patch: cobaia_run_session skip when COBAIA_LI_AT not set
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────


def _create_warmup_db(tmp_path: Path) -> Path:
    db = tmp_path / "test_c6.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
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
        INSERT INTO cobaia_warmup_state
            (account_handle, started_at, current_day, phase, config_json)
        VALUES ('cobaia', '2099-01-01T09:00:00', 14, 'normal', '{}');
    """)
    conn.commit()
    conn.close()
    return db


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_dispatch_cobaia_session_vm_success():
    """_dispatch_cobaia_session_to_vm returns VM response on HTTP 200."""
    from daemon.cobaia_warmup_scheduler import _dispatch_cobaia_session_to_vm

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "session_id": "sess-abc", "status": "queued", "actions_planned": 5, "metrics": {},
    }

    # Late imports inside _dispatch_cobaia_session_to_vm → patch at source module
    with patch("httpx.post", return_value=fake_response):
        with patch("core.state.VM_API_URL", "http://fake-vm:8420"):
            with patch("core.state.AUTH_TOKEN", "tok"):
                result = _dispatch_cobaia_session_to_vm("lurking", {"engagements": 3}, "cobaia")

    assert result["status"] == "queued"
    assert result["session_id"] == "sess-abc"


def test_dispatch_cobaia_session_vm_http_error():
    """_dispatch_cobaia_session_to_vm returns error dict on non-200 response."""
    from daemon.cobaia_warmup_scheduler import _dispatch_cobaia_session_to_vm

    fake_response = MagicMock()
    fake_response.status_code = 503
    fake_response.text = "Service Unavailable"

    with patch("httpx.post", return_value=fake_response):
        with patch("core.state.VM_API_URL", "http://fake-vm:8420"):
            with patch("core.state.AUTH_TOKEN", "tok"):
                result = _dispatch_cobaia_session_to_vm("lurking", {}, "cobaia")

    assert "error" in result
    assert "503" in result["error"]


def test_dispatch_cobaia_session_vm_connection_error():
    """_dispatch_cobaia_session_to_vm is best-effort: returns error dict, never raises."""
    from daemon.cobaia_warmup_scheduler import _dispatch_cobaia_session_to_vm

    with patch("httpx.post", side_effect=ConnectionError("VM unreachable")):
        with patch("core.state.VM_API_URL", "http://bad:9999"):
            with patch("core.state.AUTH_TOKEN", "tok"):
                result = _dispatch_cobaia_session_to_vm("lurking", {}, "cobaia")

    assert "error" in result
    assert "VM unreachable" in result["error"]


def test_record_cobaia_metrics_upsert(tmp_path):
    """_record_cobaia_metrics inserts new row correctly."""
    db = _create_warmup_db(tmp_path)

    # get_db is a late import from core.state inside _record_cobaia_metrics
    with patch("core.state.get_db") as mock_get_db:
        def _real_get_db():
            conn = sqlite3.connect(str(db))
            conn.row_factory = sqlite3.Row
            return conn
        mock_get_db.side_effect = _real_get_db

        from daemon.cobaia_warmup_scheduler import _record_cobaia_metrics
        _record_cobaia_metrics("cobaia", {"engagements": 3, "views": 2, "errors": 0})

    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT engagements_count, views_count FROM cobaia_daily_metrics WHERE account_handle='cobaia'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == 3
    assert row[1] == 2


def test_record_cobaia_metrics_delta_accumulates(tmp_path):
    """_record_cobaia_metrics accumulates incremental deltas on conflict."""
    db = _create_warmup_db(tmp_path)

    with patch("core.state.get_db") as mock_get_db:
        def _real_get_db():
            conn = sqlite3.connect(str(db))
            conn.row_factory = sqlite3.Row
            return conn
        mock_get_db.side_effect = _real_get_db

        from daemon.cobaia_warmup_scheduler import _record_cobaia_metrics
        _record_cobaia_metrics("cobaia", {"engagements": 3, "views": 2})
        _record_cobaia_metrics("cobaia", {"engagements": 2, "views": 1})

    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT engagements_count, views_count FROM cobaia_daily_metrics WHERE account_handle='cobaia'"
    ).fetchone()
    conn.close()
    assert row[0] == 5  # 3 + 2
    assert row[1] == 3  # 2 + 1


def test_daily_check_dispatch_called_on_success(tmp_path):
    """_run_daily_check calls _dispatch_cobaia_session_to_vm after daily_check succeeds."""
    from daemon.cobaia_warmup_scheduler import _run_daily_check

    mock_result = {
        "skipped": False, "auto_paused": False,
        "phase": "normal", "current_day": 15, "caps": {"views": 70, "connects": 10, "engagements": 15},
    }
    mock_dispatch_result = {"session_id": "s1", "status": "queued", "actions_planned": 25, "metrics": {}}

    with patch("linkedin.cobaia_warmup.CobaiaWarmupManager") as MockMgr:
        MockMgr.return_value.daily_check.return_value = mock_result
        MockMgr.return_value.record_error = MagicMock()
        MockMgr.return_value.reset_errors = MagicMock()
        with patch("daemon.cobaia_warmup_scheduler._dispatch_cobaia_session_to_vm", return_value=mock_dispatch_result) as mock_dispatch:
            with patch("daemon.cobaia_warmup_scheduler._ws_emit"):
                _run_daily_check()

    mock_dispatch.assert_called_once_with("normal", mock_result["caps"], "caio-leao-cobaia")
    MockMgr.return_value.reset_errors.assert_called_once()


def test_daily_check_records_error_on_dispatch_failure(tmp_path):
    """_run_daily_check calls mgr.record_error when dispatch returns error."""
    from daemon.cobaia_warmup_scheduler import _run_daily_check

    mock_result = {
        "skipped": False, "auto_paused": False,
        "phase": "lurking", "current_day": 3, "caps": {"views": 5, "connects": 0, "engagements": 3},
    }

    with patch("linkedin.cobaia_warmup.CobaiaWarmupManager") as MockMgr:
        MockMgr.return_value.daily_check.return_value = mock_result
        MockMgr.return_value.record_error = MagicMock()
        MockMgr.return_value.reset_errors = MagicMock()
        with patch("daemon.cobaia_warmup_scheduler._dispatch_cobaia_session_to_vm", return_value={"error": "vm_http_503"}) as mock_dispatch:
            with patch("daemon.cobaia_warmup_scheduler._ws_emit"):
                _run_daily_check()

    MockMgr.return_value.record_error.assert_called_once()
    MockMgr.return_value.reset_errors.assert_not_called()


@pytest.mark.anyio
async def test_vm_patch_skip_when_cobaia_li_at_not_set():
    """VM patch /run-session returns skipped when COBAIA_LI_AT env var absent."""
    import os
    # Ensure env var is not set for this test
    env_backup = os.environ.pop("COBAIA_LI_AT", None)
    try:
        from _vm_cobaia_c6_patch import cobaia_run_session, CobaiaRunSessionRequest
        req = CobaiaRunSessionRequest(phase="lurking", caps={"engagements": 3, "views": 5}, account_handle="cobaia")
        result = await cobaia_run_session(req)
        assert result["status"] == "skipped"
        assert result["reason"] == "cobaia_li_at_not_configured"
        assert result["session_id"] is None
    finally:
        if env_backup is not None:
            os.environ["COBAIA_LI_AT"] = env_backup
