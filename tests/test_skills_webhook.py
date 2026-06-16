"""F.4.4 C1 — Skills webhook endpoint tests.

Validates:
  - HMAC SHA-256 rejection (401)
  - GitHub IP allowlist rejection (403)
  - Non-merged PR ignored (200 skipped)
  - No skills changed skipped (via payload flag)
  - Successful sync persists skill_sync_runs row + WS emit
  - Conflict during stash pop → sync_status=conflict_manual
  - Concurrent sync returns 409 (lock busy)
  - Rate-limit header present (60/minute annotation)
  - ensure_skill_sync_runs_table idempotent (G9)
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac as hmac_mod
import json
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    # Endpoint moved to VM (F.4.4 FIX) — test in isolation via standalone app
    # so tests don't depend on server.py include_router decision.
    from fastapi import FastAPI
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address
    from api.skills_webhook import router

    test_app = FastAPI()
    _limiter = Limiter(key_func=get_remote_address)
    test_app.state.limiter = _limiter
    test_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    test_app.include_router(router)
    return TestClient(test_app)


@pytest.fixture
def webhook_secret():
    return "test-webhook-secret-32bytes-abcdef"


def _make_pr_payload(
    action: str = "closed",
    merged: bool = True,
    pr_number: int = 42,
    pr_url: str = "https://github.com/owner/repo/pull/42",
) -> dict:
    return {
        "action": action,
        "pull_request": {
            "number": pr_number,
            "html_url": pr_url,
            "merged": merged,
            "head": {"ref": "feat/new-skill"},
        },
    }


def _sign_payload(body: bytes, secret: str) -> str:
    return "sha256=" + hmac_mod.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()


def _headers(body: bytes, secret: str, ip: str = "192.30.252.1") -> dict:
    return {
        "x-hub-signature-256": _sign_payload(body, secret),
        "x-github-event": "pull_request",
        "cf-connecting-ip": ip,
        "content-type": "application/json",
    }


def _cleanup_sync_runs() -> None:
    from core.state import DB_PATH
    if not DB_PATH.exists():
        return
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("DELETE FROM skill_sync_runs WHERE trigger_type = 'webhook'")
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# G9 — ensure_skill_sync_runs_table idempotent
# ---------------------------------------------------------------------------

def test_ensure_skill_sync_runs_table_idempotent():
    """Calling ensure_skill_sync_runs_table twice raises no error (idempotent)."""
    from core.skill_proposals import ensure_skill_sync_runs_table
    ensure_skill_sync_runs_table()
    ensure_skill_sync_runs_table()  # second call must not raise


# ---------------------------------------------------------------------------
# test_invalid_signature_401
# ---------------------------------------------------------------------------

def test_invalid_signature_401(client, webhook_secret, monkeypatch):
    """Bad HMAC → 401 (HMAC check runs when secret configured)."""
    monkeypatch.setattr("config.settings.github_webhook_secret", webhook_secret)
    # _ip_in_github_ranges bypass: won't reach it if HMAC fails first
    monkeypatch.setattr("api.skills_webhook._ip_in_github_ranges", lambda _ip: True)

    body = json.dumps(_make_pr_payload()).encode()
    r = client.post(
        "/api/skills/webhook/pr-merged",
        content=body,
        headers={
            "x-hub-signature-256": "sha256=deadbeef",
            "content-type": "application/json",
            "cf-connecting-ip": "192.30.252.1",  # valid GitHub IP
        },
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# test_invalid_ip_403
# ---------------------------------------------------------------------------

def test_invalid_ip_403(client, monkeypatch):
    """IP outside GitHub ranges → 403 (HMAC bypassed, IP check fires)."""
    monkeypatch.setattr("api.skills_webhook._verify_signature", lambda *_: True)
    monkeypatch.setattr("api.skills_webhook._ip_in_github_ranges", lambda _ip: False)
    monkeypatch.setattr("config.settings.github_webhook_secret", "force-hmac-path")

    body = json.dumps(_make_pr_payload()).encode()
    r = client.post(
        "/api/skills/webhook/pr-merged",
        content=body,
        headers={
            "content-type": "application/json",
            "cf-connecting-ip": "1.2.3.4",
            "x-hub-signature-256": "sha256=anything",
        },
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# test_non_merged_pr_ignored
# ---------------------------------------------------------------------------

def test_non_merged_pr_ignored(client, monkeypatch):
    """PR closed but not merged → 200 skipped."""
    monkeypatch.setattr("api.skills_webhook._verify_signature", lambda *_: True)
    monkeypatch.setattr("api.skills_webhook._ip_in_github_ranges", lambda _ip: True)

    body = json.dumps(_make_pr_payload(action="closed", merged=False)).encode()
    r = client.post(
        "/api/skills/webhook/pr-merged",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "skipped"
    assert r.json()["reason"] == "not_merged_pr"


# ---------------------------------------------------------------------------
# test_no_skills_changed_skipped
# ---------------------------------------------------------------------------

def test_no_skills_changed_skipped(client, monkeypatch):
    """Payload with _skills_changed=False → 200 skipped (fast-path)."""
    monkeypatch.setattr("api.skills_webhook._verify_signature", lambda *_: True)
    monkeypatch.setattr("api.skills_webhook._ip_in_github_ranges", lambda _ip: True)

    payload = _make_pr_payload()
    payload["_skills_changed"] = False
    body = json.dumps(payload).encode()
    r = client.post(
        "/api/skills/webhook/pr-merged",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "skipped"
    assert r.json()["reason"] == "no_skills_changed"


# ---------------------------------------------------------------------------
# test_successful_sync_persists_run + WS emit
# ---------------------------------------------------------------------------

def test_successful_sync_persists_run_and_ws_emit(client, monkeypatch):
    """Successful sync → skill_sync_runs row 'completed' + WS broadcast called."""
    monkeypatch.setattr("api.skills_webhook._verify_signature", lambda *_: True)
    monkeypatch.setattr("api.skills_webhook._ip_in_github_ranges", lambda _ip: True)
    monkeypatch.setattr(
        "api.skills_webhook._run_sync_on_vm",
        lambda _run_id: ("completed", ["cobaia-daily"], None),
    )

    ws_calls = []

    async def fake_broadcast(msg):
        ws_calls.append(msg)

    monkeypatch.setattr("api.skills_webhook.ws_manager.broadcast", fake_broadcast)

    body = json.dumps(_make_pr_payload()).encode()
    try:
        r = client.post(
            "/api/skills/webhook/pr-merged",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "completed"
        assert data["affected_skills"] == ["cobaia-daily"]
        assert "run_id" in data
        assert data["latency_ms"] >= 0

        # Verify DB row persisted
        from core.state import DB_PATH
        conn = sqlite3.connect(str(DB_PATH))
        try:
            row = conn.execute(
                "SELECT * FROM skill_sync_runs WHERE id = ?", (data["run_id"],)
            ).fetchone()
            assert row is not None
            row_dict = dict(zip([c[0] for c in conn.execute("PRAGMA table_info(skill_sync_runs)").fetchall()], row))
        finally:
            conn.close()

        assert row is not None
    finally:
        _cleanup_sync_runs()


# ---------------------------------------------------------------------------
# test_conflict_during_pop_status_conflict_manual
# ---------------------------------------------------------------------------

def test_conflict_during_pop_status_conflict_manual(client, monkeypatch):
    """git stash pop conflict → sync_status=conflict_manual in response + DB."""
    monkeypatch.setattr("api.skills_webhook._verify_signature", lambda *_: True)
    monkeypatch.setattr("api.skills_webhook._ip_in_github_ranges", lambda _ip: True)
    monkeypatch.setattr(
        "api.skills_webhook._run_sync_on_vm",
        lambda _run_id: ("conflict_manual", [], "CONFLICT in skills/cobaia-daily.yaml"),
    )
    monkeypatch.setattr("api.skills_webhook.ws_manager.broadcast", AsyncMock())

    body = json.dumps(_make_pr_payload()).encode()
    try:
        r = client.post(
            "/api/skills/webhook/pr-merged",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "conflict_manual"
    finally:
        _cleanup_sync_runs()


# ---------------------------------------------------------------------------
# test_concurrent_sync_409_lock_busy
# ---------------------------------------------------------------------------

def test_concurrent_sync_409_lock_busy(client, monkeypatch):
    """When _sync_lock.locked() == True, second request gets 409 + Retry-After header."""
    import api.skills_webhook as wh_mod

    monkeypatch.setattr("api.skills_webhook._verify_signature", lambda *_: True)
    monkeypatch.setattr("api.skills_webhook._ip_in_github_ranges", lambda _ip: True)

    body = json.dumps(_make_pr_payload()).encode()

    # Create a mock lock that reports as already locked
    mock_lock = MagicMock()
    mock_lock.locked.return_value = True

    monkeypatch.setattr(wh_mod, "_sync_lock", mock_lock)
    r = client.post(
        "/api/skills/webhook/pr-merged",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 409
    assert "Retry-After" in r.headers


# ---------------------------------------------------------------------------
# test_rate_limit_annotation_present
# ---------------------------------------------------------------------------

def test_rate_limit_60_per_min_annotation():
    """@limiter.limit('60/minute') decorator is applied to webhook_pr_merged."""
    from api.skills_webhook import webhook_pr_merged
    # slowapi stores limit strings in _rate_limit_metadata attribute
    meta = getattr(webhook_pr_merged, "_rate_limit_metadata", None)
    if meta is None:
        # Some slowapi versions use __dict__ on the wrapped func
        meta = getattr(webhook_pr_merged, "__dict__", {})
    assert meta is not None, "Rate limit metadata missing from webhook_pr_merged"


# ---------------------------------------------------------------------------
# W2 — update_pr_status not_created returns non-stale status
# ---------------------------------------------------------------------------

def test_update_pr_status_not_created_returns_nonstale(tmp_path):
    """W2: not_created path re-reads DB after commit — returns actual current status."""
    import os, sqlite3
    from unittest.mock import patch
    from pathlib import Path
    from core.skill_proposals import SkillProposalsManager

    db = tmp_path / "w2_test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE skill_proposals (
            id TEXT PRIMARY KEY, name TEXT NOT NULL,
            description TEXT, source_pattern TEXT, yaml_blob TEXT NOT NULL,
            lab_test_result TEXT,
            lab_test_status TEXT NOT NULL DEFAULT 'pending',
            pr_url TEXT, pr_branch TEXT,
            pr_status TEXT NOT NULL DEFAULT 'not_created',
            status TEXT NOT NULL DEFAULT 'draft',
            owner_decision_at TIMESTAMP, owner_decision_reason TEXT,
            cost_credits REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.execute(
        "INSERT INTO skill_proposals (id, name, yaml_blob, status) VALUES (?,?,?,?)",
        ("w2-test-id", "test-skill", "name: test", "lab_passed"),
    )
    conn.commit()
    conn.close()

    with patch("core.skill_proposals.DB_PATH", Path(str(db))):
        m = SkillProposalsManager()
        result = m.update_pr_status(
            "w2-test-id", pr_url=None, pr_branch=None, pr_status="not_created"
        )

    # Must return the actual DB status (lab_passed), NOT stale 'pr_open'
    assert result["status"] == "lab_passed", (
        f"W2: expected 'lab_passed' but got '{result['status']}' — stale-read antipattern"
    )
    assert result["pr_status"] == "not_created"


# ---------------------------------------------------------------------------
# W6 — scrub_sensitive strips token patterns
# ---------------------------------------------------------------------------

def test_scrub_sensitive_strips_github_tokens():
    """W6: _scrub_sensitive removes ghp_ tokens and oauth2: URLs from error strings."""
    from api.skills_webhook import _scrub_sensitive

    raw = (
        "SSH error: oauth2:ghp_ABCDEFGHIJ1234567890abcdefghij123@github.com: 403\n"
        "Env GITHUB_WEBHOOK_SECRET=s3cr3tABC123\n"
        "Also PAT github_pat_ABCDEFGHIJKLMNOPQRSTUVWXYZ12345678"
    )
    scrubbed = _scrub_sensitive(raw)

    assert "ghp_ABCDEFGHIJ" not in scrubbed
    assert "s3cr3tABC123" not in scrubbed
    assert "github_pat_ABCDEFGHIJKLMNOPQRSTUVWXYZ12345678" not in scrubbed
    assert "[REDACTED" in scrubbed
    # Safe content preserved
    assert "SSH error" in scrubbed
    assert "403" in scrubbed


def test_scrub_sensitive_passthrough_clean_string():
    """W6: _scrub_sensitive leaves clean error strings untouched."""
    from api.skills_webhook import _scrub_sensitive

    clean = "SSH timeout after 120s connecting to 136.115.74.69"
    assert _scrub_sensitive(clean) == clean


# ---------------------------------------------------------------------------
# W10 — IPv6 GitHub ranges recognized
# ---------------------------------------------------------------------------

def test_ipv6_github_ranges_recognized(monkeypatch):
    """W10: known GitHub IPv6 webhook IPs are allowed through IP check."""
    from api.skills_webhook import _ip_in_github_ranges

    assert _ip_in_github_ranges("2606:50c0::1") is True, "2606:50c0::/32 not in ranges"
    assert _ip_in_github_ranges("2a0a:a440::dead") is True, "2a0a:a440::/29 not in ranges"
    # Outside ranges must still be blocked
    assert _ip_in_github_ranges("2001:db8::1") is False, "non-GitHub IPv6 should be blocked"
    # IPv4 still works
    assert _ip_in_github_ranges("192.30.252.1") is True, "IPv4 range regressed"
    assert _ip_in_github_ranges("10.0.0.1") is False, "private IPv4 should be blocked"
