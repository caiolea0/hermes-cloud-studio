"""F.4.1 — Skill proposals CRUD endpoints (Auto-Skill Loop W3 backend).

Cross-ref: .claude/PLAN.md § "F.4 Decisões Cristalizadas" D1 (sub-task split)
           + D7 (skill EXTEND) + D8 (dual source-of-truth).

8 endpoints under /api/skills/proposals (does NOT touch existing /api/hermes/skills
proxy in api/hermes.py — that endpoint remains as VM YAML browser):

  GET    /api/skills/proposals                  — list with optional status filter
  POST   /api/skills/proposals                  — create draft proposal
  GET    /api/skills/proposals/{id}             — single proposal full row
  GET    /api/skills/proposals/{id}/yaml-preview — yaml_blob raw (F.4.3 Monaco editor)
  POST   /api/skills/proposals/{id}/accept       — owner approve (queues F.4.2 lab test)
  POST   /api/skills/proposals/{id}/reject       — owner reject (terminal archived)
  POST   /api/skills/proposals/generate          — F.4.1 STUB; F.4.2 wires workflow invoke
  GET    /api/skills/health                      — aggregate skill_runs counts (F.4.4 enhances)

Pydantic validation per endpoint (D9 pattern F.6.1 / F.8.2 / F.9.1).
"""
from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.skill_proposals import (
    SkillProposalsManager,
    _connect,
    _table_exists,
    manager as proposals_manager,
)

log = logging.getLogger("hermes.api.skills")

router = APIRouter(prefix="/api/skills", tags=["skills"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ProposalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    yaml_blob: str = Field(..., min_length=1)
    source_pattern: str = Field("owner_manual", pattern="^(owner_manual|activity_30d_pattern|brain_observation)$")


class DecisionRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_table_or_503() -> None:
    if not _table_exists():
        raise HTTPException(
            503,
            "skill_proposals table missing — apply migrations/2026_06_skill_proposals.sql",
        )


def _runs_table_exists() -> bool:
    from core.state import DB_PATH
    if not DB_PATH.exists():
        return False
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='skill_runs'"
        ).fetchone()
        return row is not None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /api/skills/proposals — list with filter + pagination
# ---------------------------------------------------------------------------

@router.get("/proposals")
async def list_proposals(
    status: Optional[str] = Query(None, description="draft | lab_running | lab_passed | lab_failed | pr_open | pr_merged | pr_rejected | deployed | archived"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    _ensure_table_or_503()
    try:
        result = proposals_manager.list_by_status(status=status, limit=limit, offset=offset)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return JSONResponse(
        content=result,
        headers={"X-Total-Count": str(result["total"])},
    )


# ---------------------------------------------------------------------------
# POST /api/skills/proposals — create draft
# ---------------------------------------------------------------------------

@router.post("/proposals", status_code=201)
async def create_proposal(req: ProposalCreate):
    _ensure_table_or_503()
    try:
        result = proposals_manager.create(
            name=req.name,
            description=req.description,
            yaml_blob=req.yaml_blob,
            source_pattern=req.source_pattern,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return result


# ---------------------------------------------------------------------------
# GET /api/skills/proposals/{id}
# ---------------------------------------------------------------------------

@router.get("/proposals/{proposal_id}")
async def get_proposal(proposal_id: str):
    _ensure_table_or_503()
    try:
        return proposals_manager.get(proposal_id)
    except LookupError:
        raise HTTPException(404, "proposal_not_found")


# ---------------------------------------------------------------------------
# GET /api/skills/proposals/{id}/yaml-preview — F.4.3 Monaco editor consumer
# ---------------------------------------------------------------------------

@router.get("/proposals/{proposal_id}/yaml-preview")
async def get_yaml_preview(proposal_id: str):
    _ensure_table_or_503()
    try:
        return proposals_manager.get_yaml_preview(proposal_id)
    except LookupError:
        raise HTTPException(404, "proposal_not_found")


# ---------------------------------------------------------------------------
# POST /api/skills/proposals/{id}/accept — F.4.3 owner UI consumer
# ---------------------------------------------------------------------------

@router.post("/proposals/{proposal_id}/accept", status_code=202)
async def accept_proposal(proposal_id: str, req: DecisionRequest):
    """F.4.1 transition draft → lab_running. F.4.2 background task triggers lab dispatch."""
    _ensure_table_or_503()
    try:
        result = proposals_manager.owner_decision(
            proposal_id, decision="accept", reason=req.reason,
        )
    except LookupError:
        raise HTTPException(404, "proposal_not_found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {
        **result,
        "note": "F.4.2_implements_real_lab_dispatch + F.4.2_implements_real_github_mcp",
    }


# ---------------------------------------------------------------------------
# POST /api/skills/proposals/{id}/reject — terminal archived
# ---------------------------------------------------------------------------

@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str, req: DecisionRequest):
    _ensure_table_or_503()
    try:
        result = proposals_manager.owner_decision(
            proposal_id, decision="reject", reason=req.reason,
        )
    except LookupError:
        raise HTTPException(404, "proposal_not_found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return result


# ---------------------------------------------------------------------------
# POST /api/skills/proposals/generate — STUB (F.4.2 implements workflow invoke)
# ---------------------------------------------------------------------------

@router.post("/proposals/generate", status_code=202)
async def trigger_synthesis():
    """F.4.1 STUB — F.4.2_implements_real_workflow_invoke.

    Returns 202 + job_id placeholder. F.4.2 will spawn
    .claude/workflows/hermes-skill-forge.js via Workflow tool dispatch.
    """
    _ensure_table_or_503()
    job_id = str(uuid.uuid4())
    return {
        "job_id": job_id,
        "status": "queued",
        "note": "F.4.2_implements_real_workflow_invoke — F.4.1 STUB returns job_id only",
    }


# ---------------------------------------------------------------------------
# GET /api/skills/health — aggregate skill_runs counts (F.4.4 enhances)
# ---------------------------------------------------------------------------

@router.get("/health")
async def skills_health(window_days: int = Query(7, ge=1, le=90)):
    """F.4.1 basic counts. F.4.4_implements_sentry_integration + quarantine signal D6."""
    if not _runs_table_exists():
        return {
            "window_days": window_days,
            "table_exists": False,
            "total_runs": 0,
            "by_status": {},
            "by_skill": {},
            "note": "skill_runs missing — apply migrations/2026_06_skill_proposals.sql",
        }

    cutoff = time.time() - window_days * 86400
    conn = _connect()
    try:
        by_status_rows = conn.execute(
            """SELECT status, COUNT(*) AS n
               FROM skill_runs
               WHERE strftime('%s', started_at) >= ?
               GROUP BY status""",
            (str(int(cutoff)),),
        ).fetchall()
        by_skill_rows = conn.execute(
            """SELECT skill_name,
                      COUNT(*) AS total,
                      SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                      SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS errors,
                      AVG(latency_ms) AS avg_latency_ms
               FROM skill_runs
               WHERE strftime('%s', started_at) >= ?
               GROUP BY skill_name
               ORDER BY total DESC
               LIMIT 50""",
            (str(int(cutoff)),),
        ).fetchall()
    finally:
        conn.close()

    by_status = {r["status"]: int(r["n"]) for r in by_status_rows}
    by_skill: dict[str, dict[str, Any]] = {}
    for r in by_skill_rows:
        total = int(r["total"] or 0)
        completed = int(r["completed"] or 0)
        success_rate = round(completed / total, 3) if total else 0.0
        by_skill[r["skill_name"]] = {
            "total": total,
            "completed": completed,
            "errors": int(r["errors"] or 0),
            "avg_latency_ms": round(float(r["avg_latency_ms"] or 0), 1),
            "success_rate": success_rate,
        }

    return {
        "window_days": window_days,
        "table_exists": True,
        "total_runs": sum(by_status.values()),
        "by_status": by_status,
        "by_skill": by_skill,
        "note": "F.4.4_implements_sentry_integration + D6 quarantine signal (success_rate < 0.5 last 10)",
    }
