"""F.7 P5 hardening — Hunter.io EmailVerifier unit tests (8 tests, MOCK-DRIVEN).

All tests use a temp SQLite DB + mocked httpx — no Hunter API call real.
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


def _mock_response(status_code: int, json_data: dict | None = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_data or {})
    return resp


@pytest.mark.asyncio
async def test_verify_email_returns_structured_dict(tmp_db):
    verifier = EmailVerifier(api_key="test-key", db_path=tmp_db)
    fake_resp = _mock_response(200, {
        "data": {
            "status": "valid", "score": 95, "smtp_check": True,
            "mx_records": True, "disposable": False, "webmail": False,
        }
    })
    with patch.object(verifier, "_http", new=AsyncMock(return_value=MagicMock(
            get=AsyncMock(return_value=fake_resp)))):
        result = await verifier.verify_email("test@example.com")
    assert result["status"] == "valid"
    assert result["score"] == 95
    assert result["smtp_check"] is True
    assert result["mx_records"] is True
    assert result["disposable"] is False
    assert result["cached"] is False


@pytest.mark.asyncio
async def test_verify_email_cache_hit_skips_api_call(tmp_db):
    verifier = EmailVerifier(api_key="test-key", db_path=tmp_db)
    fake_resp = _mock_response(200, {
        "data": {"status": "valid", "score": 90, "smtp_check": True,
                 "mx_records": True, "disposable": False, "webmail": False}
    })
    get_mock = AsyncMock(return_value=fake_resp)
    with patch.object(verifier, "_http", new=AsyncMock(return_value=MagicMock(get=get_mock))):
        r1 = await verifier.verify_email("cache@example.com")
        r2 = await verifier.verify_email("cache@example.com")
    assert r1["cached"] is False
    assert r2["cached"] is True
    assert r2["status"] == "valid"
    assert get_mock.call_count == 1  # cache hit on 2nd call


@pytest.mark.asyncio
async def test_verify_email_cache_ttl_30d_expires(tmp_db):
    verifier = EmailVerifier(api_key="test-key", db_path=tmp_db)
    # Insert expired row manually
    conn = sqlite3.connect(tmp_db)
    past = (datetime.now(timezone.utc) - timedelta(days=_CACHE_TTL_DAYS + 1)).isoformat()
    conn.execute(
        """INSERT INTO hunter_email_cache
           (email, status, score, smtp_check, mx_records, disposable, webmail,
            raw_json, verified_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("expired@example.com", "valid", 80, 1, 1, 0, 0, "{}",
         past, past),  # expires_at past
    )
    conn.commit()
    conn.close()
    fake_resp = _mock_response(200, {
        "data": {"status": "invalid", "score": 10, "smtp_check": False,
                 "mx_records": False, "disposable": True, "webmail": False}
    })
    get_mock = AsyncMock(return_value=fake_resp)
    with patch.object(verifier, "_http", new=AsyncMock(return_value=MagicMock(get=get_mock))):
        result = await verifier.verify_email("expired@example.com")
    assert result["cached"] is False  # cache expired, fresh call
    assert result["status"] == "invalid"
    assert get_mock.call_count == 1


@pytest.mark.asyncio
async def test_quota_exhausted_graceful_fallback(tmp_db):
    verifier = EmailVerifier(api_key="test-key", db_path=tmp_db)
    fake_resp = _mock_response(429, {})
    with patch.object(verifier, "_http", new=AsyncMock(return_value=MagicMock(
            get=AsyncMock(return_value=fake_resp)))):
        result = await verifier.verify_email("quota@example.com")
    assert result["status"] == "quota_exhausted"
    assert result["score"] == 0
    assert "error" not in result or result.get("cached") is False


@pytest.mark.asyncio
async def test_rate_limit_15_per_min_throttle(tmp_db):
    """Verify sliding window: 15 calls fill window, 16th forces throttle."""
    verifier = EmailVerifier(api_key="test-key", db_path=tmp_db)
    now = time.time()
    verifier._rate_window = [now - 5] * 15  # 15 recent calls
    sleep_calls = []

    async def fake_sleep(s):
        sleep_calls.append(s)

    fake_resp = _mock_response(200, {
        "data": {"status": "valid", "score": 90, "smtp_check": True,
                 "mx_records": True, "disposable": False, "webmail": False}
    })
    with patch("core.email_verifier.asyncio.sleep", new=fake_sleep), \
         patch.object(verifier, "_http", new=AsyncMock(return_value=MagicMock(
                 get=AsyncMock(return_value=fake_resp)))):
        await verifier.verify_email("ratelimit@example.com")
    assert len(sleep_calls) == 1, f"expected throttle sleep, got {sleep_calls}"
    assert sleep_calls[0] > 0


@pytest.mark.asyncio
async def test_disposable_email_detection(tmp_db):
    verifier = EmailVerifier(api_key="test-key", db_path=tmp_db)
    fake_resp = _mock_response(200, {
        "data": {"status": "valid", "score": 50, "smtp_check": True,
                 "mx_records": True, "disposable": True, "webmail": False}
    })
    with patch.object(verifier, "_http", new=AsyncMock(return_value=MagicMock(
            get=AsyncMock(return_value=fake_resp)))):
        result = await verifier.verify_email("user@mailinator.com")
    assert result["disposable"] is True


@pytest.mark.asyncio
async def test_invalid_email_blocked_from_warmup(tmp_db):
    """Invalid email returns status='invalid' — cobaia warmup MUST skip."""
    verifier = EmailVerifier(api_key="test-key", db_path=tmp_db)
    fake_resp = _mock_response(200, {
        "data": {"status": "invalid", "score": 5, "smtp_check": False,
                 "mx_records": False, "disposable": False, "webmail": False}
    })
    with patch.object(verifier, "_http", new=AsyncMock(return_value=MagicMock(
            get=AsyncMock(return_value=fake_resp)))):
        result = await verifier.verify_email("bogus@nonexistent-xyz.com")
    assert result["status"] == "invalid"
    assert result["smtp_check"] is False
    # Format invalid path
    bad = await verifier.verify_email("not-an-email")
    assert bad["status"] == "format_invalid"


@pytest.mark.asyncio
async def test_sentry_breadcrumb_each_verify(tmp_db):
    verifier = EmailVerifier(api_key="test-key", db_path=tmp_db)
    crumbs = []
    verifier._breadcrumb = lambda msg, data: crumbs.append((msg, data))
    fake_resp = _mock_response(200, {
        "data": {"status": "valid", "score": 90, "smtp_check": True,
                 "mx_records": True, "disposable": False, "webmail": False}
    })
    with patch.object(verifier, "_http", new=AsyncMock(return_value=MagicMock(
            get=AsyncMock(return_value=fake_resp)))):
        await verifier.verify_email("crumb@example.com")
        await verifier.verify_email("crumb@example.com")  # cache hit
    assert len(crumbs) >= 2
    kinds = [c[0] for c in crumbs]
    assert any("api_call" in k for k in kinds)
    assert any("cache_hit" in k for k in kinds)
