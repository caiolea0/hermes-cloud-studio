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
        """F.4.2_implements_real_github_mcp — F.4.1 stores PR metadata post-create.

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
        finally:
            conn.close()
        return {
            "id": proposal_id,
            "pr_status": pr_status,
            "status": new_status or existing["status"],
            "pr_url": pr_url,
        }

    def owner_decision(
        self,
        proposal_id: str,
        decision: str,
        reason: Optional[str] = None,
    ) -> dict[str, Any]:
        """F.4.3_implements_real_ui_modal — F.4.1 stores decision atomically.

        decision must be 'accept' or 'reject'.
        accept → lab_running (queues lab test via F.4.2 trigger)
        reject → archived (terminal)
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


# Module-level singleton (cheap — no in-memory state beyond DB connection per call).
manager = SkillProposalsManager()
