"""F.4.1 — Skill proposals lifecycle state machine.

Cross-ref: .claude/PLAN.md § "F.4 Decisões Cristalizadas" D7 + D8.

D7: hermes-skill-forge-runner skill EXTEND existing.
D8: dual source-of-truth — skill_proposals (workflow staging) + skills/ git (production).

Lifecycle states (skill_proposals.status):
  draft → lab_running → lab_passed | lab_failed
                            ↓
                        pr_open → pr_merged | pr_rejected
                                      ↓
                                  deployed | archived

F.4.1 entrega CRUD + lifecycle helpers; F.4.2 wire-up real lab/GitHub MCP;
F.4.3 UI dashboard; F.4.4 sync VM + Sentry auto-disable cron; F.4.5 closeout.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any, Optional

from core.state import DB_PATH


_ALLOWED_STATUS = {
    "draft", "lab_running", "lab_passed", "lab_failed",
    "pr_open", "pr_merged", "pr_rejected", "deployed", "archived",
}
_ALLOWED_LAB_STATUS = {"pending", "passed", "failed", "skipped"}
_ALLOWED_PR_STATUS = {"not_created", "open", "merged", "closed_rejected"}
_ALLOWED_SOURCE_PATTERN = {
    "owner_manual", "activity_30d_pattern", "brain_observation",
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists() -> bool:
    if not DB_PATH.exists():
        return False
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='skill_proposals'"
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def ensure_synthesis_runs_table(conn: Optional[sqlite3.Connection] = None) -> None:
    """F.4.2 C3 (PIVOT D6) — idempotent CREATE IF NOT EXISTS for synthesis_runs.

    Called by AutoSkillRunner.trigger_workflow_synthesis defensively so the
    scaffold works even when the migration has not been applied at startup.
    """
    own_conn = conn is None
    if own_conn:
        conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS synthesis_runs (
                id              TEXT PRIMARY KEY,
                trigger_type    TEXT NOT NULL,
                status          TEXT NOT NULL,
                queued_at       TEXT NOT NULL,
                requester       TEXT NOT NULL,
                trigger_source  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_synthesis_runs_status ON synthesis_runs(status);
            CREATE INDEX IF NOT EXISTS idx_synthesis_runs_queued_at ON synthesis_runs(queued_at);
            """
        )
        conn.commit()
    finally:
        if own_conn:
            conn.close()


def _ensure_delivery_id_column(conn: sqlite3.Connection) -> None:
    """W3: idempotent ALTER TABLE to add delivery_id + partial UNIQUE index."""
    try:
        conn.execute("ALTER TABLE skill_sync_runs ADD COLUMN delivery_id TEXT NULL")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists
    try:
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_skill_sync_runs_delivery_id
               ON skill_sync_runs(delivery_id) WHERE delivery_id IS NOT NULL"""
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass  # index already exists


def ensure_skill_sync_runs_table(conn: Optional[sqlite3.Connection] = None) -> None:
    """F.4.4 C1 — idempotent CREATE IF NOT EXISTS for skill_sync_runs.

    Called by api/skills_webhook.py before every insert so the table is
    available even when the migration has not been applied at startup.
    W3: also ensures delivery_id column exists (added post-C1).
    """
    own_conn = conn is None
    if own_conn:
        conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS skill_sync_runs (
                id              TEXT PRIMARY KEY,
                trigger_type    TEXT NOT NULL,
                pr_number       INTEGER NULL,
                pr_url          TEXT NULL,
                sync_status     TEXT NOT NULL,
                started_at      TEXT NOT NULL,
                completed_at    TEXT NULL,
                error_message   TEXT NULL,
                affected_skills TEXT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_skill_sync_runs_status
                ON skill_sync_runs(sync_status);
            CREATE INDEX IF NOT EXISTS idx_skill_sync_runs_started_at
                ON skill_sync_runs(started_at);
            """
        )
        conn.commit()
        _ensure_delivery_id_column(conn)
    finally:
        if own_conn:
            conn.close()


def get_skill_sync_run_by_delivery_id(delivery_id: str) -> Optional[dict[str, Any]]:
    """W3: look up existing run by X-GitHub-Delivery ID for dedup check."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, sync_status FROM skill_sync_runs WHERE delivery_id = ? LIMIT 1",
            (delivery_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def insert_skill_sync_run(
    *,
    run_id: str,
    trigger_type: str,
    pr_number: Optional[int],
    pr_url: Optional[str],
    started_at: str,
    delivery_id: Optional[str] = None,
) -> str:
    """F.4.4 C1 — insert initial 'started' row. Returns run_id.

    W3: delivery_id (X-GitHub-Delivery header) stored for dedup; NULL for non-webhook.
    """
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO skill_sync_runs
                (id, trigger_type, pr_number, pr_url, sync_status, started_at, delivery_id)
            VALUES (?, ?, ?, ?, 'started', ?, ?)
            """,
            (run_id, trigger_type, pr_number, pr_url, started_at, delivery_id),
        )
        conn.commit()
    finally:
        conn.close()
    return run_id


def update_skill_sync_run(run_id: str, **kwargs: Any) -> None:
    """F.4.4 C1 — atomic UPDATE of skill_sync_runs fields by run_id.

    Accepted kwargs: sync_status, completed_at, error_message, affected_skills.
    Unknown keys are silently ignored (forward-compat).
    """
    _allowed = {"sync_status", "completed_at", "error_message", "affected_skills"}
    fields = {k: v for k, v in kwargs.items() if k in _allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [run_id]
    conn = _connect()
    try:
        conn.execute(
            f"UPDATE skill_sync_runs SET {set_clause} WHERE id = ?",  # noqa: S608
            values,
        )
        conn.commit()
    finally:
        conn.close()


def get_synthesis_run(run_id: str) -> Optional[dict[str, Any]]:
    """F.4.2 C3 helper — read single synthesis_runs row by id."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM synthesis_runs WHERE id = ?", (run_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


class SkillProposalsManager:
    """Lifecycle state machine for skill_proposals.

    All public methods raise ValueError for invalid input or LookupError for
    missing rows. API layer translates to HTTPException.
    """

    def create(
        self,
        name: str,
        description: Optional[str],
        yaml_blob: str,
        source_pattern: str = "owner_manual",
    ) -> dict[str, Any]:
        if not name or not isinstance(name, str):
            raise ValueError("name must be non-empty string")
        if not yaml_blob or not isinstance(yaml_blob, str):
            raise ValueError("yaml_blob must be non-empty string")
        if source_pattern not in _ALLOWED_SOURCE_PATTERN:
            raise ValueError(
                f"source_pattern must be one of {sorted(_ALLOWED_SOURCE_PATTERN)}"
            )

        proposal_id = str(uuid.uuid4())
        conn = _connect()
        try:
            conn.execute(
                """INSERT INTO skill_proposals
                   (id, name, description, yaml_blob, source_pattern)
                   VALUES (?, ?, ?, ?, ?)""",
                (proposal_id, name, description, yaml_blob, source_pattern),
            )
            conn.commit()
        finally:
            conn.close()
        return {"id": proposal_id, "name": name, "status": "draft"}

    def list_by_status(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        if status is not None and status not in _ALLOWED_STATUS:
            raise ValueError(f"status must be one of {sorted(_ALLOWED_STATUS)}")

        where = "WHERE status = ?" if status else ""
        params: list[Any] = [status] if status else []

        conn = _connect()
        try:
            total_row = conn.execute(
                f"SELECT COUNT(*) AS c FROM skill_proposals {where}", params
            ).fetchone()
            total = int(total_row["c"]) if total_row else 0
            rows = conn.execute(
                f"""SELECT id, name, description, source_pattern, status,
                           lab_test_status, pr_status, pr_url, pr_branch,
                           owner_decision_at, owner_decision_reason,
                           cost_credits, created_at, updated_at
                    FROM skill_proposals
                    {where}
                    ORDER BY updated_at DESC
                    LIMIT ? OFFSET ?""",
                params + [limit, offset],
            ).fetchall()
            items = [dict(r) for r in rows]
        finally:
            conn.close()

        return {"items": items, "total": total, "offset": offset, "limit": limit}

    def get(self, proposal_id: str) -> dict[str, Any]:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM skill_proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
            if not row:
                raise LookupError("proposal_not_found")
            return dict(row)
        finally:
            conn.close()

    def get_yaml_preview(self, proposal_id: str) -> dict[str, Any]:
        """Return yaml_blob raw + metadata (F.4.3 Monaco editor consumer)."""
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT id, name, yaml_blob, status FROM skill_proposals WHERE id = ?",
                (proposal_id,),
            ).fetchone()
            if not row:
                raise LookupError("proposal_not_found")
            return {
                "id": row["id"],
                "name": row["name"],
                "status": row["status"],
                "yaml_blob": row["yaml_blob"],
                "chars": len(row["yaml_blob"] or ""),
            }
        finally:
            conn.close()

    def update_lab_result(
        self,
        proposal_id: str,
        lab_test_result: dict[str, Any],
        lab_test_status: str,
    ) -> dict[str, Any]:
        """Persist lab_test_result + transition status (F.4.2 C1 wires AutoSkillRunner).

        Transitions status: lab_running → lab_passed | lab_failed.
        """
        if lab_test_status not in _ALLOWED_LAB_STATUS:
            raise ValueError(
                f"lab_test_status must be one of {sorted(_ALLOWED_LAB_STATUS)}"
            )
        new_status = {
            "passed": "lab_passed",
            "failed": "lab_failed",
            "pending": "lab_running",
            "skipped": "lab_passed",
        }[lab_test_status]

        conn = _connect()
        try:
            existing = conn.execute(
                "SELECT status FROM skill_proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
            if not existing:
                raise LookupError("proposal_not_found")
            conn.execute(
                """UPDATE skill_proposals
                   SET lab_test_result = ?, lab_test_status = ?, status = ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (json.dumps(lab_test_result), lab_test_status, new_status, proposal_id),
            )
            conn.commit()
        finally:
            conn.close()
        return {"id": proposal_id, "lab_test_status": lab_test_status, "status": new_status}

    def update_pr_status(
        self,
        proposal_id: str,
        pr_url: Optional[str],
        pr_branch: Optional[str],
        pr_status: str,
    ) -> dict[str, Any]:
        """Persist PR metadata + transition status (F.4.2 C2 wires AutoSkillRunner).

        Transitions status: lab_passed → pr_open → pr_merged | pr_rejected.
        """
        if pr_status not in _ALLOWED_PR_STATUS:
            raise ValueError(
                f"pr_status must be one of {sorted(_ALLOWED_PR_STATUS)}"
            )
        status_map = {
            "open": "pr_open",
            "merged": "pr_merged",
            "closed_rejected": "pr_rejected",
            "not_created": None,
        }
        new_status = status_map[pr_status]

        conn = _connect()
        try:
            existing = conn.execute(
                "SELECT status FROM skill_proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
            if not existing:
                raise LookupError("proposal_not_found")
            set_clauses = ["pr_status = ?", "updated_at = CURRENT_TIMESTAMP"]
            params: list[Any] = [pr_status]
            if pr_url is not None:
                set_clauses.append("pr_url = ?")
                params.append(pr_url)
            if pr_branch is not None:
                set_clauses.append("pr_branch = ?")
                params.append(pr_branch)
            if new_status is not None:
                set_clauses.append("status = ?")
                params.append(new_status)
            params.append(proposal_id)
            conn.execute(
                f"UPDATE skill_proposals SET {', '.join(set_clauses)} WHERE id = ?",
                params,
            )
            conn.commit()
            # W2: re-read after commit — eliminates stale-read antipattern when new_status is None
            post_row = conn.execute(
                "SELECT status FROM skill_proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
            effective_status = post_row["status"] if post_row else (new_status or existing["status"])
        finally:
            conn.close()
        return {
            "id": proposal_id,
            "pr_status": pr_status,
            "status": effective_status,
            "pr_url": pr_url,
        }

    def owner_decision(
        self,
        proposal_id: str,
        decision: str,
        reason: Optional[str] = None,
    ) -> dict[str, Any]:
        """Atomic owner decision persistence (F.4.1 base; F.4.3 UI modal consumer).

        decision must be 'accept' or 'reject'.
        accept → lab_running (queues lab test via F.4.2 trigger)
        reject → archived (terminal, reason persisted to owner_decision_reason)
        """
        if decision not in ("accept", "reject"):
            raise ValueError("decision must be 'accept' or 'reject'")
        new_status = "lab_running" if decision == "accept" else "archived"

        conn = _connect()
        try:
            existing = conn.execute(
                "SELECT status FROM skill_proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
            if not existing:
                raise LookupError("proposal_not_found")
            conn.execute(
                """UPDATE skill_proposals
                   SET status = ?, owner_decision_at = CURRENT_TIMESTAMP,
                       owner_decision_reason = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (new_status, reason, proposal_id),
            )
            conn.commit()
        finally:
            conn.close()
        return {
            "id": proposal_id,
            "decision": decision,
            "status": new_status,
            "reason": reason,
        }


    def update_owner_verified(
        self,
        proposal_id: str,
        verified: bool,
        allowed_mcps: Optional[str],
        notes: Optional[str] = None,
    ) -> dict[str, Any]:
        """Phase 5 — set owner_verified flag + allowed_mcps allowlist.

        verified=True  → sets verified_at + verified_by='caio', clears awaiting_verify_since.
        verified=False → clears verification fields (unverify/revoke).
        """
        conn = _connect()
        try:
            existing = conn.execute(
                "SELECT status FROM skill_proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
            if not existing:
                raise LookupError("proposal_not_found")
            if verified:
                conn.execute(
                    """UPDATE skill_proposals
                       SET owner_verified = 1,
                           allowed_mcps = ?,
                           verified_at = CURRENT_TIMESTAMP,
                           verified_by = 'caio',
                           verification_notes = ?,
                           awaiting_verify_since = NULL,
                           updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (allowed_mcps, notes, proposal_id),
                )
            else:
                conn.execute(
                    """UPDATE skill_proposals
                       SET owner_verified = 0,
                           allowed_mcps = NULL,
                           verified_at = NULL,
                           verified_by = NULL,
                           verification_notes = ?,
                           updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (notes, proposal_id),
                )
            conn.commit()
        finally:
            conn.close()
        return {
            "id": proposal_id,
            "owner_verified": verified,
            "allowed_mcps": allowed_mcps,
        }

    def mark_awaiting_verify(self, proposal_id: str) -> dict[str, Any]:
        """Phase 5 — auto_skill_runner stamps awaiting_verify_since when lab_passed but not owner_verified.

        Does NOT change status (stays lab_passed, within CHECK constraint).
        Dashboard detects pending-verify via lab_passed + owner_verified=0 + awaiting_verify_since IS NOT NULL.
        """
        conn = _connect()
        try:
            existing = conn.execute(
                "SELECT status FROM skill_proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
            if not existing:
                raise LookupError("proposal_not_found")
            conn.execute(
                """UPDATE skill_proposals
                   SET awaiting_verify_since = CURRENT_TIMESTAMP,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (proposal_id,),
            )
            conn.commit()
        finally:
            conn.close()
        return {"id": proposal_id, "status": existing["status"], "awaiting_verify_since_set": True}

    def get_pending_verification(self, limit: int = 50) -> list[dict[str, Any]]:
        """Phase 5 — lab_passed proposals not yet owner_verified. Used by dashboard filter + API."""
        conn = _connect()
        try:
            rows = conn.execute(
                """SELECT id, name, description, status, lab_test_status,
                          owner_verified, allowed_mcps, verified_at, awaiting_verify_since,
                          cost_credits, created_at, updated_at
                   FROM skill_proposals
                   WHERE owner_verified = 0
                     AND status = 'lab_passed'
                   ORDER BY updated_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_by_name(self, name: str) -> Optional[dict[str, Any]]:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM skill_proposals WHERE name = ? LIMIT 1", (name,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


# Module-level singleton (cheap — no in-memory state beyond DB connection per call).
manager = SkillProposalsManager()


# ---------------------------------------------------------------------------
# F.4.4 C2 — Quarantine helpers (PC-side, reads from hermes_local.db)
# ---------------------------------------------------------------------------

def _ensure_quarantine_columns(conn: sqlite3.Connection) -> None:
    """Idempotent ALTER TABLE to add quarantine_reason + quarantine_at columns."""
    for col, typ in [("quarantine_reason", "TEXT"), ("quarantine_at", "TEXT")]:
        try:
            conn.execute(f"ALTER TABLE skill_proposals ADD COLUMN {col} {typ}")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists


def get_skill_runs_success_rate(
    name: str,
    limit: int = 10,
    db_path: Optional[str] = None,
) -> dict[str, Any]:
    """Query skill_runs by skill_name and compute success_rate.

    Returns dict with keys: success_rate, total, passed, failed, sample_size.
    Uses PC's hermes_local.db unless db_path overridden.
    """
    _path = str(db_path) if db_path else str(DB_PATH)
    conn = sqlite3.connect(_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT status FROM skill_runs
               WHERE skill_name = ?
               ORDER BY started_at DESC LIMIT ?""",
            (name, limit),
        ).fetchall()
    finally:
        conn.close()

    total = len(rows)
    passed = sum(1 for r in rows if r["status"] == "completed")
    failed = total - passed
    return {
        "success_rate": round(passed / total, 3) if total else 0.0,
        "total": total,
        "passed": passed,
        "failed": failed,
        "sample_size": total,
    }


def update_quarantine_status(
    name: str,
    reason: str,
    db_path: Optional[str] = None,
) -> bool:
    """Mark a skill proposal as quarantined (sets quarantine_at + quarantine_reason).

    Uses 'archived' status (valid in CHECK constraint) as quarantine proxy.
    Returns True if a row was updated, False if not found or already quarantined.
    """
    _path = str(db_path) if db_path else str(DB_PATH)
    conn = sqlite3.connect(_path, timeout=10.0)
    try:
        _ensure_quarantine_columns(conn)
        cur = conn.execute(
            """UPDATE skill_proposals
               SET quarantine_reason = ?,
                   quarantine_at = CURRENT_TIMESTAMP,
                   status = 'archived',
                   updated_at = CURRENT_TIMESTAMP
               WHERE name = ? AND quarantine_at IS NULL""",
            (reason, name),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def unquarantine(
    name: str,
    db_path: Optional[str] = None,
) -> bool:
    """Clear quarantine state for a skill proposal.

    Returns True if a row was updated, False if not found or not quarantined.
    """
    _path = str(db_path) if db_path else str(DB_PATH)
    conn = sqlite3.connect(_path, timeout=10.0)
    try:
        _ensure_quarantine_columns(conn)
        cur = conn.execute(
            """UPDATE skill_proposals
               SET quarantine_reason = NULL,
                   quarantine_at = NULL,
                   status = 'deployed',
                   updated_at = CURRENT_TIMESTAMP
               WHERE name = ? AND quarantine_at IS NOT NULL""",
            (name,),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
