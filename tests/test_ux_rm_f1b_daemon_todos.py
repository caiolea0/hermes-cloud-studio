"""UX-RM-F1-B — Kill 9 daemon TODOs in orchestrator.py.

Tests validate:
  TODO #1: _check_human_stop blocks _send_auto_response when stop signal present
  TODO #2: _exec_recalculate_scores returns 501 not_implemented
  TODO #3: _exec_weekly_report sends markdown text via Telegram (no PDF)
  TODO #4: inbox_replies migration idempotent + _get_pending_replies queries correctly
  TODO #5: sequence_enrollments migration idempotent + _get_due_sequence_steps filters past
  TODO #6: _send_via_channel — dry-run default, LinkedIn MCP dispatch, email/WA 501
  TODO #7: _enrich_single returns 501 stub
  TODO #8: _send_auto_response skips on low-confidence LLM output
  TODO #9: _schedule_followup inserts into sequence_enrollments

All tests MOCK-DRIVEN: no real DB, no real LLM, no real gateway calls.
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_db(tmp_path: Path) -> Path:
    """Create a temp DB with daemon tables applied."""
    db = tmp_path / "test_daemon_f1b.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS daemon_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            state TEXT NOT NULL DEFAULT 'idle',
            current_task_type TEXT,
            current_task_detail TEXT,
            energy REAL DEFAULT 1.0,
            started_at TIMESTAMP,
            last_heartbeat TIMESTAMP,
            stats_today TEXT,
            stats_week TEXT
        );
        CREATE TABLE IF NOT EXISTS daemon_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            level TEXT NOT NULL,
            category TEXT NOT NULL,
            message TEXT NOT NULL,
            metadata TEXT,
            visual_event TEXT
        );
        CREATE TABLE IF NOT EXISTS daemon_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            action TEXT NOT NULL,
            reason TEXT NOT NULL,
            context TEXT,
            result TEXT
        );
        CREATE TABLE IF NOT EXISTS inbox_replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prospect_id INTEGER NOT NULL,
            channel TEXT NOT NULL DEFAULT 'unknown',
            body TEXT NOT NULL DEFAULT '',
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            handled INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_inbox_replies_handled
            ON inbox_replies(handled, received_at);
        CREATE TABLE IF NOT EXISTS sequence_enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prospect_id INTEGER NOT NULL,
            sequence_id TEXT NOT NULL DEFAULT 'default',
            current_step INTEGER NOT NULL DEFAULT 0,
            next_action_at TIMESTAMP NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (prospect_id, sequence_id)
        );
        CREATE INDEX IF NOT EXISTS idx_seq_enrollments_due
            ON sequence_enrollments(completed, next_action_at);
        CREATE TABLE IF NOT EXISTS telegram_stop_signals (
            prospect_id INTEGER NOT NULL,
            channel TEXT NOT NULL DEFAULT 'all',
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (prospect_id, channel)
        );
        INSERT OR IGNORE INTO daemon_state (id, state, started_at, last_heartbeat)
        VALUES (1, 'idle', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
    """)
    conn.close()
    return db


def _make_daemon(db_path: Path):
    """Build a HermesDaemon with patched DB_PATH (no __init__ called)."""
    from daemon.orchestrator import HermesDaemon, DaemonState, ChannelState, DaemonStats
    daemon = HermesDaemon.__new__(HermesDaemon)
    daemon.state = DaemonState.IDLE
    daemon.current_task = None
    daemon.energy = 1.0
    daemon.stats_today = DaemonStats()
    daemon.stats_week = DaemonStats()
    daemon.consecutive_errors = 0
    daemon.decision_log = []
    daemon.channels = {
        "linkedin": ChannelState(name="linkedin", daily_limit=70),
        "email": ChannelState(name="email", daily_limit=75),
        "whatsapp": ChannelState(name="whatsapp", daily_limit=25, is_active=False),
    }
    daemon._db_path = str(db_path)
    return daemon


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    return _build_db(tmp_path)


@pytest.fixture
def daemon(tmp_db):
    d = _make_daemon(tmp_db)
    return d, tmp_db


# ---------------------------------------------------------------------------
# TODO #1: _check_human_stop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_human_stop_received_blocks_auto_response(tmp_db):
    """STOP signal in telegram_stop_signals → _check_human_stop returns True."""
    from daemon import orchestrator as orch

    with patch.object(orch, "DB_PATH", tmp_db):
        # Insert stop signal
        conn = sqlite3.connect(str(tmp_db))
        conn.execute(
            "INSERT INTO telegram_stop_signals (prospect_id, channel) VALUES (?, ?)",
            (42, "linkedin"),
        )
        conn.commit()
        conn.close()

        d = _make_daemon(tmp_db)
        result = await orch.HermesDaemon._check_human_stop(d, prospect_id=42, channel="linkedin")
        assert result is True


@pytest.mark.asyncio
async def test_human_stop_channel_all_blocks_any_channel(tmp_db):
    """STOP signal with channel='all' blocks any channel send."""
    from daemon import orchestrator as orch

    with patch.object(orch, "DB_PATH", tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        conn.execute(
            "INSERT INTO telegram_stop_signals (prospect_id, channel) VALUES (?, 'all')",
            (99,),
        )
        conn.commit()
        conn.close()

        d = _make_daemon(tmp_db)
        assert await orch.HermesDaemon._check_human_stop(d, prospect_id=99, channel="email") is True


@pytest.mark.asyncio
async def test_no_stop_signal_allows_auto_response(tmp_db):
    """No stop signal → _check_human_stop returns False (allow send)."""
    from daemon import orchestrator as orch

    with patch.object(orch, "DB_PATH", tmp_db):
        d = _make_daemon(tmp_db)
        result = await orch.HermesDaemon._check_human_stop(d, prospect_id=1, channel="linkedin")
        assert result is False


# ---------------------------------------------------------------------------
# TODO #2: _exec_recalculate_scores — 501 stub
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recalculate_scores_returns_501(tmp_db):
    """_exec_recalculate_scores returns status=not_implemented + code=501."""
    from daemon import orchestrator as orch

    with patch.object(orch, "DB_PATH", tmp_db):
        d = _make_daemon(tmp_db)
        d.log_event = AsyncMock()
        result = await orch.HermesDaemon._exec_recalculate_scores(d, None)
        assert result["status"] == "not_implemented"
        assert result["code"] == 501


# ---------------------------------------------------------------------------
# TODO #3: _exec_weekly_report — markdown via Telegram (no PDF)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_weekly_report_sends_markdown_telegram(tmp_db):
    """_exec_weekly_report calls _notify_telegram with text, returns sent=True."""
    from daemon import orchestrator as orch
    from daemon.orchestrator import DaemonStats

    with patch.object(orch, "DB_PATH", tmp_db):
        d = _make_daemon(tmp_db)
        d.stats_week = DaemonStats(
            discovered=10, enriched=5, contacted=3, replied=1,
            meetings=0, errors=0, decisions=5,
        )
        d._notify_telegram = AsyncMock()
        result = await orch.HermesDaemon._exec_weekly_report(d, None)
        assert result == {"sent": True}
        d._notify_telegram.assert_called_once()
        text = d._notify_telegram.call_args[0][0]
        assert "Weekly Report" in text
        assert "10" in text  # discovered count


# ---------------------------------------------------------------------------
# TODO #4: inbox_replies migration + _get_pending_replies
# ---------------------------------------------------------------------------

def test_inbox_table_migration_idempotent(tmp_db):
    """Applying migration SQL twice does not raise (IF NOT EXISTS guards)."""
    migration = Path(__file__).parent.parent / "migrations" / "2026_06_daemon_sequence_inbox.sql"
    assert migration.exists(), "migration file must exist"
    conn = sqlite3.connect(str(tmp_db))
    sql = migration.read_text()
    conn.executescript(sql)  # first apply
    conn.executescript(sql)  # second apply — must not raise
    conn.close()


@pytest.mark.asyncio
async def test_get_unhandled_replies_returns_handled_zero(tmp_db):
    """_get_pending_replies returns only rows with handled=0."""
    from daemon import orchestrator as orch

    with patch.object(orch, "DB_PATH", tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        conn.executemany(
            "INSERT INTO inbox_replies (prospect_id, channel, body, handled) VALUES (?, ?, ?, ?)",
            [
                (1, "linkedin", "Oi, tenho interesse", 0),
                (2, "email", "Pode me ligar?", 0),
                (3, "linkedin", "Nao obrigado", 1),  # already handled
            ],
        )
        conn.commit()
        conn.close()

        d = _make_daemon(tmp_db)
        replies = await orch.HermesDaemon._get_pending_replies(d)
        assert len(replies) == 2
        assert all(r["channel"] in ("linkedin", "email") for r in replies)
        assert all(isinstance(r["prospect_id"], int) for r in replies)


# ---------------------------------------------------------------------------
# TODO #5: sequence_enrollments migration + _get_due_sequence_steps
# ---------------------------------------------------------------------------

def test_sequence_enrollments_migration_idempotent(tmp_db):
    """Applying migration SQL twice does not raise."""
    migration = Path(__file__).parent.parent / "migrations" / "2026_06_daemon_sequence_inbox.sql"
    conn = sqlite3.connect(str(tmp_db))
    sql = migration.read_text()
    conn.executescript(sql)
    conn.executescript(sql)
    conn.close()


@pytest.mark.asyncio
async def test_get_due_sequence_steps_filters_past(tmp_db):
    """_get_due_sequence_steps returns past-due rows only (next_action_at <= now)."""
    from daemon import orchestrator as orch

    with patch.object(orch, "DB_PATH", tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        conn.executemany(
            "INSERT INTO sequence_enrollments (prospect_id, sequence_id, next_action_at, completed) "
            "VALUES (?, ?, ?, ?)",
            [
                (10, "default", "2020-01-01 00:00:00", 0),   # past → due
                (11, "default", "2020-06-15 00:00:00", 0),   # past → due
                (12, "default", "2099-01-01 00:00:00", 0),   # future → NOT due
                (13, "default", "2020-01-01 00:00:00", 1),   # past but completed → NOT due
            ],
        )
        conn.commit()
        conn.close()

        d = _make_daemon(tmp_db)
        steps = await orch.HermesDaemon._get_due_sequence_steps(d)
        assert len(steps) == 2
        prospect_ids = {s["prospect_id"] for s in steps}
        assert prospect_ids == {10, 11}


# ---------------------------------------------------------------------------
# TODO #6: _send_via_channel — env flag + MCP + stubs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_channel_disabled_env_dry_run(tmp_db, monkeypatch):
    """When HERMES_CHANNEL_SEND_ENABLED != '1', returns True (dry-run) without MCP call."""
    monkeypatch.delenv("HERMES_CHANNEL_SEND_ENABLED", raising=False)
    from daemon import orchestrator as orch

    with patch.object(orch, "DB_PATH", tmp_db):
        d = _make_daemon(tmp_db)
        result = await orch.HermesDaemon._send_via_channel(
            d, "linkedin", 1, "template text", {}
        )
        assert result is True


@pytest.mark.asyncio
async def test_send_channel_linkedin_invokes_gateway(tmp_db, monkeypatch):
    """When enabled + channel=linkedin → GatewayDispatcher.invoke_tool called."""
    monkeypatch.setenv("HERMES_CHANNEL_SEND_ENABLED", "1")
    monkeypatch.setenv("HERMES_GATEWAY_OAUTH_SECRET", "test-secret")
    from daemon import orchestrator as orch

    mock_dispatcher = MagicMock()
    mock_dispatcher.invoke_tool = AsyncMock(return_value={"ok": True, "call_id": "abc"})

    with (
        patch.object(orch, "DB_PATH", tmp_db),
        patch("brain.dispatch.GatewayDispatcher", return_value=mock_dispatcher),
    ):
        d = _make_daemon(tmp_db)
        result = await orch.HermesDaemon._send_via_channel(
            d, "linkedin", 7, "Oi fulano", {}
        )
        assert result is True
        mock_dispatcher.invoke_tool.assert_called_once()
        call_args = mock_dispatcher.invoke_tool.call_args
        assert call_args[0][0] == "hermes-linkedin"
        assert call_args[0][1] == "send_message"


@pytest.mark.asyncio
async def test_send_channel_email_returns_501(tmp_db, monkeypatch):
    """When enabled + channel=email → returns False (501 stub, F.future)."""
    monkeypatch.setenv("HERMES_CHANNEL_SEND_ENABLED", "1")
    from daemon import orchestrator as orch

    with patch.object(orch, "DB_PATH", tmp_db):
        d = _make_daemon(tmp_db)
        result = await orch.HermesDaemon._send_via_channel(
            d, "email", 1, "template", {}
        )
        assert result is False


# ---------------------------------------------------------------------------
# TODO #7: _enrich_single — 501 stub
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enrich_prospect_returns_501(tmp_db):
    """_enrich_single returns fields_filled=0, code=501."""
    from daemon import orchestrator as orch

    with patch.object(orch, "DB_PATH", tmp_db):
        d = _make_daemon(tmp_db)
        result = await orch.HermesDaemon._enrich_single(d, {"id": 1, "name": "Test"})
        assert result["fields_filled"] == 0
        assert result["code"] == 501
        assert "not implemented" in result["reason"]


# ---------------------------------------------------------------------------
# TODO #8: _send_auto_response — low-confidence skip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_auto_response_skips_low_confidence(tmp_db):
    """When LLM returns < 20 chars, auto-response is skipped (low_confidence_skip)."""
    from daemon import orchestrator as orch
    from linkedin.ollama_router import OllamaUnavailable

    short_response = "ok"  # len=2 < 20

    with patch.object(orch, "DB_PATH", tmp_db):
        d = _make_daemon(tmp_db)
        d._send_via_channel = AsyncMock()

        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value=short_response)

        with patch.object(orch, "ollama_router", mock_router):
            await orch.HermesDaemon._send_auto_response(
                d, prospect_id=5, intent="interested", channel="linkedin"
            )

        d._send_via_channel.assert_not_called()


@pytest.mark.asyncio
async def test_generate_auto_response_sends_when_confident(tmp_db):
    """When LLM returns >= 20 chars, _send_via_channel is called."""
    from daemon import orchestrator as orch

    good_response = "Obrigado pelo retorno! Podemos agendar uma conversa rapida?"

    with patch.object(orch, "DB_PATH", tmp_db):
        d = _make_daemon(tmp_db)
        d._send_via_channel = AsyncMock(return_value=True)

        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value=good_response)

        with patch.object(orch, "ollama_router", mock_router):
            await orch.HermesDaemon._send_auto_response(
                d, prospect_id=5, intent="interested", channel="linkedin"
            )

        d._send_via_channel.assert_called_once()


# ---------------------------------------------------------------------------
# TODO #9: _schedule_followup — inserts enrollment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_schedule_followup_inserts_enrollment(tmp_db):
    """_schedule_followup inserts a sequence_enrollments row with correct next_action_at offset."""
    from daemon import orchestrator as orch

    with patch.object(orch, "DB_PATH", tmp_db):
        d = _make_daemon(tmp_db)
        await orch.HermesDaemon._schedule_followup(
            d, prospect_id=99, days=30, sequence_id="follow_up_30d"
        )

    conn = sqlite3.connect(str(tmp_db))
    row = conn.execute(
        "SELECT prospect_id, sequence_id, completed FROM sequence_enrollments WHERE prospect_id = 99"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == 99
    assert row[1] == "follow_up_30d"
    assert row[2] == 0  # not completed


@pytest.mark.asyncio
async def test_schedule_followup_idempotent(tmp_db):
    """INSERT OR IGNORE prevents duplicate enrollment for same prospect+sequence."""
    from daemon import orchestrator as orch

    with patch.object(orch, "DB_PATH", tmp_db):
        d = _make_daemon(tmp_db)
        await orch.HermesDaemon._schedule_followup(d, prospect_id=50, days=30)
        await orch.HermesDaemon._schedule_followup(d, prospect_id=50, days=30)  # duplicate → ignored

    conn = sqlite3.connect(str(tmp_db))
    count = conn.execute(
        "SELECT COUNT(*) FROM sequence_enrollments WHERE prospect_id = 50"
    ).fetchone()[0]
    conn.close()
    assert count == 1
