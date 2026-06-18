"""Phase 5 — owner_verified gate for cobaia activation safety.

8 tests covering:
  - migration idempotency
  - default owner_verified=False
  - auto_skill_runner gate blocks PR when not verified
  - auto_skill_runner proceeds when verified
  - verify endpoint sets allowed_mcps
  - verify endpoint rejects invalid MCPs
  - unverify endpoint reverts state
  - WS emit brain.skill_awaiting_verify on gate hit
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import core.skill_proposals as skill_proposals_module
import core.state as state_module
from core.auto_skill_runner import AutoSkillRunner
from core.skill_proposals import SkillProposalsManager


# ---------------------------------------------------------------------------
# Fixture — tmp DB with BOTH skill_proposals + owner_verified migrations applied
# ---------------------------------------------------------------------------

def _apply_migration(conn: sqlite3.Connection, path: Path) -> None:
    """Apply a SQL migration, handling ALTER TABLE ADD COLUMN idempotency.

    Uses executescript for the base schema (handles comments + multi-statement),
    then does statement-by-statement for ALTER TABLE migrations with error catching.
    """
    sql = path.read_text(encoding="utf-8")
    # Strip comment-only lines to avoid `;` inside comments breaking split.
    cleaned_lines = [
        line for line in sql.splitlines()
        if not line.strip().startswith("--")
    ]
    sql_clean = "\n".join(cleaned_lines)

    for stmt in sql_clean.split(";"):
        stmt = stmt.strip()
        if not stmt:
            continue
        try:
            conn.execute(stmt)
            conn.commit()
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if "duplicate column" in msg or "already exists" in msg:
                pass  # idempotent
            else:
                raise


@pytest.fixture
def verified_db(monkeypatch, tmp_path):
    db_path = tmp_path / "phase5.db"
    root = Path(__file__).parent.parent
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    _apply_migration(conn, root / "migrations" / "2026_06_skill_proposals.sql")
    _apply_migration(conn, root / "migrations" / "2026_06_skill_owner_verified.sql")

    conn.close()

    monkeypatch.setattr(state_module, "DB_PATH", db_path)
    monkeypatch.setattr(skill_proposals_module, "DB_PATH", db_path)

    manager = SkillProposalsManager()
    return manager, db_path


def _make_runner(manager, ws_emitted: list[dict] | None = None):
    """Return AutoSkillRunner with mocked dispatcher + captured WS emits."""
    runner = AutoSkillRunner(dispatcher=None, manager=manager)
    if ws_emitted is not None:
        async def _fake_ws(event_type, payload):
            ws_emitted.append({"event_type": event_type, "payload": payload})
        runner._ws_emit = _fake_ws  # type: ignore[method-assign]
    return runner


# ---------------------------------------------------------------------------
# T1 — migration idempotent: applying twice raises no error
# ---------------------------------------------------------------------------

def test_migration_idempotent_owner_verified_columns(tmp_path):
    db_path = tmp_path / "idempotent.db"
    root = Path(__file__).parent.parent
    conn = sqlite3.connect(str(db_path))
    _apply_migration(conn, root / "migrations" / "2026_06_skill_proposals.sql")
    # First apply
    _apply_migration(conn, root / "migrations" / "2026_06_skill_owner_verified.sql")
    # Second apply — must not raise
    _apply_migration(conn, root / "migrations" / "2026_06_skill_owner_verified.sql")
    cols = [r[1] for r in conn.execute("PRAGMA table_info(skill_proposals)").fetchall()]
    conn.close()
    for col in ("owner_verified", "allowed_mcps", "verified_at", "verified_by",
                "verification_notes", "awaiting_verify_since"):
        assert col in cols, f"missing column: {col}"


# ---------------------------------------------------------------------------
# T2 — new proposal defaults to owner_verified=0
# ---------------------------------------------------------------------------

def test_proposal_default_owner_verified_false(verified_db):
    manager, _ = verified_db
    proposal = manager.create(
        name="new-proposal-test",
        description="Phase 5 default check",
        yaml_blob="name: new-proposal-test\nversion: 0.1\nprovider: openrouter\n",
    )
    detail = manager.get(proposal["id"])
    assert detail.get("owner_verified") in (0, None, False), (
        "owner_verified must default to 0/False"
    )


# ---------------------------------------------------------------------------
# T3 — auto_skill_runner skips PR creation if owner_verified=0
# ---------------------------------------------------------------------------

def test_auto_skill_runner_skips_pr_if_not_verified(verified_db):
    manager, _ = verified_db
    ws_emitted: list[dict] = []
    runner = _make_runner(manager, ws_emitted)

    # Create + lab-pass a proposal (owner_verified stays 0)
    proposal = manager.create(
        name="skip-test",
        description="should be blocked",
        yaml_blob="name: skip-test\nversion: 0.1\nprovider: openrouter\n",
    )
    pid = proposal["id"]
    manager.update_lab_result(pid, {"status": "passed", "ok": True}, "passed")

    result = asyncio.run(runner.dispatch_github_pr(pid))

    assert result["status"] == "skipped_owner_verify_required"
    assert result["reason"] == "owner_verified_required — visit /skills page to verify this skill"
    assert result["proposal_id"] == pid

    # Status stays lab_passed (CHECK constraint); awaiting_verify_since is stamped
    detail = manager.get(pid)
    assert detail["status"] == "lab_passed"
    assert detail.get("awaiting_verify_since") is not None

    # WS emit must have fired
    assert any(e["event_type"] == "brain.skill_awaiting_verify" for e in ws_emitted)


# ---------------------------------------------------------------------------
# T4 — auto_skill_runner proceeds past gate when owner_verified=1
# ---------------------------------------------------------------------------

def test_auto_skill_runner_creates_pr_if_verified(verified_db):
    manager, _ = verified_db

    proposal = manager.create(
        name="verified-pr-test",
        description="should reach GitHub gate",
        yaml_blob="name: verified-pr-test\nversion: 0.1\nprovider: openrouter\n",
    )
    pid = proposal["id"]
    manager.update_lab_result(pid, {"status": "passed", "ok": True}, "passed")

    # Set owner_verified=1
    manager.update_owner_verified(pid, verified=True, allowed_mcps='["sentry"]', notes="approved")

    detail = manager.get(pid)
    assert detail["owner_verified"] == 1

    # The runner should proceed past Phase 5 gate and attempt GitHub MCP call.
    # GitHub call will fail (no dispatcher) — but phase 5 gate must NOT be hit.
    runner = _make_runner(manager)

    # Patch dispatcher.invoke_tool to raise RuntimeError (simulate GitHub MCP fail)
    runner.dispatcher = MagicMock()
    runner.dispatcher.invoke_tool = AsyncMock(side_effect=RuntimeError("github_mcp_mock"))

    with pytest.raises(RuntimeError, match="github_mcp_mock"):
        asyncio.run(runner.dispatch_github_pr(pid))

    # Key assertion: the runner must NOT have returned "skipped_owner_verify_required"
    # (It raised — meaning it got past the phase 5 gate and hit the GitHub call)


# ---------------------------------------------------------------------------
# T5 — verify endpoint sets allowed_mcps + owner_verified=1
# ---------------------------------------------------------------------------

def test_verify_endpoint_sets_allowed_mcps(verified_db):
    manager, _ = verified_db
    proposal = manager.create(
        name="verify-endpoint-test",
        description="api verify",
        yaml_blob="name: verify-endpoint-test\nversion: 0.1\nprovider: openrouter\n",
    )
    pid = proposal["id"]

    allowed = ["sentry", "hermes-linkedin"]
    result = manager.update_owner_verified(
        proposal_id=pid,
        verified=True,
        allowed_mcps=json.dumps(sorted(allowed)),
        notes="test approval",
    )

    assert result["owner_verified"] is True
    assert result["allowed_mcps"] == json.dumps(sorted(allowed))

    detail = manager.get(pid)
    assert detail["owner_verified"] == 1
    assert "sentry" in (detail.get("allowed_mcps") or "")
    assert detail["verified_by"] == "caio"
    assert detail["verified_at"] is not None


# ---------------------------------------------------------------------------
# T6 — verify endpoint rejects invalid MCPs (API layer validation)
# ---------------------------------------------------------------------------

def test_verify_endpoint_rejects_invalid_mcps():
    from api.skills import _VALID_MCPS
    allowed_set = {"sentry", "evil-mcp", "not-a-real-mcp"}
    invalid = allowed_set - _VALID_MCPS
    assert "evil-mcp" in invalid
    assert "not-a-real-mcp" in invalid
    assert "sentry" not in invalid


# ---------------------------------------------------------------------------
# T7 — unverify endpoint reverts state
# ---------------------------------------------------------------------------

def test_unverify_endpoint_reverts_state(verified_db):
    manager, _ = verified_db
    proposal = manager.create(
        name="unverify-test",
        description="revoke test",
        yaml_blob="name: unverify-test\nversion: 0.1\nprovider: openrouter\n",
    )
    pid = proposal["id"]

    # Verify first
    manager.update_owner_verified(pid, verified=True, allowed_mcps='["sentry"]', notes="ok")
    detail = manager.get(pid)
    assert detail["owner_verified"] == 1

    # Unverify
    result = manager.update_owner_verified(
        pid, verified=False, allowed_mcps=None, notes="owner_unverify"
    )
    assert result["owner_verified"] is False

    detail2 = manager.get(pid)
    assert detail2["owner_verified"] == 0
    assert detail2["allowed_mcps"] is None
    assert detail2["verified_at"] is None
    assert detail2["verified_by"] is None


# ---------------------------------------------------------------------------
# T8 — WS emit brain.skill_awaiting_verify fires on gate hit
# ---------------------------------------------------------------------------

def test_ws_emit_brain_skill_awaiting_verify(verified_db):
    manager, _ = verified_db
    ws_emitted: list[dict] = []
    runner = _make_runner(manager, ws_emitted)

    proposal = manager.create(
        name="ws-emit-test",
        description="ws gate check",
        yaml_blob="name: ws-emit-test\nversion: 0.1\nprovider: openrouter\n",
    )
    pid = proposal["id"]
    manager.update_lab_result(pid, {"status": "passed", "ok": True}, "passed")
    # owner_verified stays 0 — gate fires

    asyncio.run(runner.dispatch_github_pr(pid))

    ws_events = [e for e in ws_emitted if e["event_type"] == "brain.skill_awaiting_verify"]
    assert len(ws_events) >= 1, "brain.skill_awaiting_verify WS event must fire"
    payload = ws_events[0]["payload"]
    assert payload["proposal_id"] == pid
    assert payload.get("reason") == "owner_verified_required"
