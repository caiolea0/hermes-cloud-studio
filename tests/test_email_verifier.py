"""F.7 P5 hardening — Hunter.io EmailVerifier unit tests.

R7 refactor: all tests mock GatewayDispatcher.invoke_tool instead of httpx.
No Hunter API calls ever made during tests.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.email_verifier import EmailVerifier, _CACHE_TTL_DAYS


MIGRATION_SQL = (Path(__file__).resolve().parent.parent
                 / "migrations" / "2026_06_hunter_email_cache.sql").read_text(encoding="utf-8")


@pytest.fixture
def tmp_db(tmp_path):
    db = tmp_path / "hunter_test.db"
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION_SQL)
    conn.commit()
    conn.close()
    return str(db)


def _gateway_ok(tool_result: dict) -> dict:
    """Wrap a tool return dict in the gateway success response envelope."""
    return {
        "ok": True,
        "call_id": "test-call-id",
        "server": "hermes-hunter",
        "tool": "verify_email",
        "response": [{"type": "text", "text": json.dumps(tool_result)}],
        "duration_ms": 42,
    }


def _gateway_err(error: str = "connect_error:ConnectionError") -> dict:
    return {"ok": False, "error": error}


def _make_verifier(tmp_db: str, invoke_return: dict) -> tuple[EmailVerifier, AsyncMock]:
    mock_dispatcher = MagicMock()
    mock_dispatcher.invoke_tool = AsyncMock(return_value=invoke_return)
    verifier = EmailVerifier(api_key="test-key", db_path=tmp_db, dispatcher=mock_dispatcher)
    return verifier, mock_dispatcher.invoke_tool


# ── R7 new tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_email_dispatches_via_gateway(tmp_db):
    """GatewayDispatcher.invoke_tool is called with correct server/tool/args."""
    tool_result = {
        "email": "test@example.com", "status": "valid", "score": 95,
        "smtp_check": True, "mx_records": True, "disposable": False, "webmail": False,
    }
    verifier, invoke_mock = _make_verifier(tmp_db, _gateway_ok(tool_result))

    result = await verifier.verify_email("test@example.com")

    invoke_mock.assert_called_once_with(
        server="hermes-hunter",
        tool="verify_email",
        args={"email": "test@example.com"},
    )
    assert result["status"] == "valid"
    assert result["score"] == 95
    assert result["smtp_check"] is True
    assert result["cached"] is False


@pytest.mark.asyncio
async def test_verify_email_cache_hit_skips_dispatch(tmp_db):
    """Second call to same email hits SQLite cache — no gateway dispatch."""
    tool_result = {
        "email": "cached@example.com", "status": "valid", "score": 90,
        "smtp_check": True, "mx_records": True, "disposable": False, "webmail": False,
    }
    verifier, invoke_mock = _make_verifier(tmp_db, _gateway_ok(tool_result))

    r1 = await verifier.verify_email("cached@example.com")
    r2 = await verifier.verify_email("cached@example.com")

    assert r1["cached"] is False
    assert r2["cached"] is True
    assert r2["status"] == "valid"
    assert invoke_mock.call_count == 1  # cache hit on 2nd call


@pytest.mark.asyncio
async def test_dispatcher_failure_graceful_fallback(tmp_db):
    """Gateway ok=False → graceful status='unknown', no exception raised."""
    verifier, _ = _make_verifier(tmp_db, _gateway_err("connect_error:ConnectionRefused"))

    result = await verifier.verify_email("fail@example.com")

    assert result["status"] == "unknown"
    assert result["cached"] is False
    assert "error" in result


# ── Preserved existing tests (updated to use gateway mock) ──────────────────


@pytest.mark.asyncio
async def test_verify_email_returns_structured_dict(tmp_db):
    tool_result = {
        "email": "test@example.com", "status": "valid", "score": 95,
        "smtp_check": True, "mx_records": True, "disposable": False, "webmail": False,
    }
    verifier, _ = _make_verifier(tmp_db, _gateway_ok(tool_result))

    result = await verifier.verify_email("test@example.com")

    assert result["status"] == "valid"
    assert result["score"] == 95
    assert result["smtp_check"] is True
    assert result["mx_records"] is True
    assert result["disposable"] is False
    assert result["cached"] is False


@pytest.mark.asyncio
async def test_verify_email_cache_ttl_30d_expires(tmp_db):
    """Expired cache row is ignored — fresh gateway call is made."""
    conn = sqlite3.connect(tmp_db)
    past = (datetime.now(timezone.utc) - timedelta(days=_CACHE_TTL_DAYS + 1)).isoformat()
    conn.execute(
        """INSERT INTO hunter_email_cache
           (email, status, score, smtp_check, mx_records, disposable, webmail,
            raw_json, verified_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("expired@example.com", "valid", 80, 1, 1, 0, 0, "{}", past, past),
    )
    conn.commit()
    conn.close()

    tool_result = {
        "email": "expired@example.com", "status": "invalid", "score": 10,
        "smtp_check": False, "mx_records": False, "disposable": True, "webmail": False,
    }
    verifier, invoke_mock = _make_verifier(tmp_db, _gateway_ok(tool_result))

    result = await verifier.verify_email("expired@example.com")
    assert result["cached"] is False
    assert result["status"] == "invalid"
    assert invoke_mock.call_count == 1


@pytest.mark.asyncio
async def test_quota_exhausted_graceful_fallback(tmp_db):
    """MCP returns quota_exhausted → EmailVerifier passes it through, no exception."""
    tool_result = {"email": "quota@example.com", "status": "quota_exhausted", "score": 0}
    verifier, _ = _make_verifier(tmp_db, _gateway_ok(tool_result))

    result = await verifier.verify_email("quota@example.com")
    assert result["status"] == "quota_exhausted"
    assert result["score"] == 0


@pytest.mark.asyncio
async def test_rate_limit_15_per_min_throttle(tmp_db):
    """Sliding window: 15 calls fill window, 16th forces asyncio.sleep."""
    tool_result = {
        "email": "rl@example.com", "status": "valid", "score": 90,
        "smtp_check": True, "mx_records": True, "disposable": False, "webmail": False,
    }
    verifier, _ = _make_verifier(tmp_db, _gateway_ok(tool_result))

    now = time.time()
    verifier._rate_window = [now - 5] * 15
    sleep_calls: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleep_calls.append(s)

    with patch("core.email_verifier.asyncio.sleep", new=fake_sleep):
        await verifier.verify_email("rl@example.com")

    assert len(sleep_calls) == 1, f"expected throttle sleep, got {sleep_calls}"
    assert sleep_calls[0] > 0


@pytest.mark.asyncio
async def test_disposable_email_detection(tmp_db):
    tool_result = {
        "email": "user@mailinator.com", "status": "valid", "score": 50,
        "smtp_check": True, "mx_records": True, "disposable": True, "webmail": False,
    }
    verifier, _ = _make_verifier(tmp_db, _gateway_ok(tool_result))

    result = await verifier.verify_email("user@mailinator.com")
    assert result["disposable"] is True


@pytest.mark.asyncio
async def test_invalid_email_blocked_from_warmup(tmp_db):
    """format_invalid is returned without gateway call; invalid status propagated."""
    tool_result = {
        "email": "bogus@nonexistent-xyz.com", "status": "invalid", "score": 5,
        "smtp_check": False, "mx_records": False, "disposable": False, "webmail": False,
    }
    verifier, invoke_mock = _make_verifier(tmp_db, _gateway_ok(tool_result))

    result = await verifier.verify_email("bogus@nonexistent-xyz.com")
    assert result["status"] == "invalid"
    assert result["smtp_check"] is False

    bad = await verifier.verify_email("not-an-email")
    assert bad["status"] == "format_invalid"
    # format_invalid short-circuits before gateway
    assert invoke_mock.call_count == 1


@pytest.mark.asyncio
async def test_sentry_breadcrumb_each_verify(tmp_db):
    """Breadcrumbs emitted on gateway_dispatch and cache_hit calls."""
    tool_result = {
        "email": "crumb@example.com", "status": "valid", "score": 90,
        "smtp_check": True, "mx_records": True, "disposable": False, "webmail": False,
    }
    verifier, _ = _make_verifier(tmp_db, _gateway_ok(tool_result))
    crumbs: list[tuple] = []
    verifier._breadcrumb = lambda msg, data: crumbs.append((msg, data))

    await verifier.verify_email("crumb@example.com")
    await verifier.verify_email("crumb@example.com")  # cache hit

    assert len(crumbs) >= 2
    kinds = [c[0] for c in crumbs]
    assert any("gateway_dispatch" in k for k in kinds)
    assert any("cache_hit" in k for k in kinds)
