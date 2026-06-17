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

import json
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
    get_synthesis_run,
    get_skill_runs_success_rate,
    update_quarantine_status,
    unquarantine as unquarantine_skill,
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
    """F.4.3 D2 — Monaco diff editor needs existing_yaml for compare.

    REUSE _find_closest_skill_yaml helper from AutoSkillRunner (C2 F.4.2).
    Returns {id, name, status, yaml_blob, chars, existing_yaml?, existing_filename?}.
    """
    _ensure_table_or_503()
    try:
        preview = proposals_manager.get_yaml_preview(proposal_id)
    except LookupError:
        raise HTTPException(404, "proposal_not_found")

    # F.4.3 D2 — best-effort lookup of closest existing skill YAML for diff.
    try:
        from core.auto_skill_runner import AutoSkillRunner
        existing = AutoSkillRunner._find_closest_skill_yaml(preview.get("name", ""))
        if existing:
            fname, text = existing
            preview["existing_filename"] = fname
            preview["existing_yaml"] = text
    except Exception as exc:  # noqa: BLE001 — diff is enhancement, never block
        log.debug("yaml-preview existing lookup failed: %s", exc)

    return preview


# ---------------------------------------------------------------------------
# POST /api/skills/proposals/{id}/accept — F.4.3 owner UI consumer
# ---------------------------------------------------------------------------

@router.post("/proposals/{proposal_id}/accept", status_code=202)
async def accept_proposal(proposal_id: str, req: DecisionRequest):
    """F.4.2 owner accept → lab dispatch → (if lab_passed) GitHub MCP PR.

    Pipeline:
      1. owner_decision → status=lab_running
      2. dispatch_sandbox_test (C1) → lab_passed | lab_failed
      3. if lab_passed → dispatch_github_pr (C2) → pr_open | blocked | failed
    """
    _ensure_table_or_503()
    try:
        owner_result = proposals_manager.owner_decision(
            proposal_id, decision="accept", reason=req.reason,
        )
    except LookupError:
        raise HTTPException(404, "proposal_not_found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    from core.auto_skill_runner import AutoSkillRunner
    runner = AutoSkillRunner()
    try:
        lab_outcome = await runner.dispatch_sandbox_test(proposal_id)
    except LookupError:
        raise HTTPException(404, "proposal_not_found")

    response: dict[str, Any] = {
        "status": "ok",
        "owner_decision": owner_result,
        "lab_test_result": lab_outcome["lab_test_result"],
        "new_status": lab_outcome["new_status"],
    }

    if not lab_outcome.get("ok"):
        # Lab failed → D4 BLOCK PR (no GitHub MCP attempt).
        response["pr"] = {"status": "blocked", "reason": "lab_failed"}
        return response

    # C2 — lab passed, chain GitHub MCP PR creation.
    try:
        pr_outcome = await runner.dispatch_github_pr(proposal_id)
    except LookupError:
        raise HTTPException(404, "proposal_not_found")
    except Exception as exc:  # noqa: BLE001 — D5 fail-fast surface (already logged/Sentry'd)
        response["pr"] = {
            "status": "failed",
            "error": str(exc)[:200],
        }
        return response

    response["pr"] = pr_outcome
    if pr_outcome.get("status") == "ok":
        response["new_status"] = "pr_open"
    return response


# ---------------------------------------------------------------------------
# POST /api/skills/proposals/{id}/reject — terminal archived
# ---------------------------------------------------------------------------

@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str, req: DecisionRequest):
    """F.4.3 D5 — owner reject + Sentry breadcrumb + WS emit (audit trail).

    Persists owner_decision_reason (NOT a hard delete — keeps history for
    Brain learning F.future). Emits brain.skill_proposal_rejected so the
    dashboard updates real-time.
    """
    _ensure_table_or_503()
    try:
        result = proposals_manager.owner_decision(
            proposal_id, decision="reject", reason=req.reason,
        )
    except LookupError:
        raise HTTPException(404, "proposal_not_found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    # D5 — Sentry breadcrumb (NOT exception, fire-and-forget).
    from core.sentry_via_gateway import add_breadcrumb
    add_breadcrumb(
        category="skill_proposal_rejected",
        message=f"proposal {proposal_id} rejected by owner",
        level="info",
        data={
            "proposal_id": proposal_id,
            "reason_len": len(req.reason or ""),
        },
    )

    # D5 — WS emit (fire-and-forget).
    try:
        from core.state import ws_manager
        await ws_manager.broadcast({
            "event_type": "brain.skill_proposal_rejected",
            "payload": {
                "proposal_id": proposal_id,
                "status": result.get("status"),
                "reason_provided": bool(req.reason),
            },
        })
    except Exception as exc:  # noqa: BLE001 — broadcast must never block
        log.debug("ws emit brain.skill_proposal_rejected failed: %s", exc)

    return result


# ---------------------------------------------------------------------------
# GET /api/skills/synthesis-runs/{run_id} — F.4.3 PATH 1 modal poll target
# ---------------------------------------------------------------------------

@router.get("/synthesis-runs/{run_id}")
async def get_synthesis_run_status(run_id: str):
    """F.4.3 D3 — PATH 1 modal polls this endpoint every 5s for status."""
    row = get_synthesis_run(run_id)
    if not row:
        raise HTTPException(404, "synthesis_run_not_found")
    return row


# ---------------------------------------------------------------------------
# POST /api/skills/proposals/generate — F.4.2 C3 (PIVOT D6 honest scaffold)
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    trigger_source: Optional[str] = Field(
        "api_manual",
        pattern="^(api_manual|ui_button|cron_auto|subprocess_path2)$",
    )


@router.post("/proposals/generate", status_code=202)
async def trigger_synthesis(req: Optional[GenerateRequest] = None):
    """F.4.2 C3 (PIVOT D6 honest scaffold) — queue a synthesis run.

    Workflow MCP is unavailable (harness feature, not public MCP) AND owner
    constraint subscription-only. Endpoint persists a 'queued' row in
    synthesis_runs + emits brain.skill_synthesis_queued WS event. Owner
    triggers the actual Workflow execution via F.4.3 UI manual button OR
    F.4.6 NOVA subprocess `claude --headless` (PATH 2).
    """
    _ensure_table_or_503()
    from core.auto_skill_runner import AutoSkillRunner
    runner = AutoSkillRunner()
    source = (req.trigger_source if req else None) or "api_manual"
    return await runner.trigger_workflow_synthesis(
        manual=True, trigger_source=source,
    )


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
        "note": "F.4.4 C2 quarantine cron active (success_rate < 0.5 last 10 runs → quarantine)",
    }


# ---------------------------------------------------------------------------
# POST /api/skills/{name}/unquarantine — D5 (F.4.4 C2)
# ---------------------------------------------------------------------------

class UnquarantineRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


@router.post("/{skill_name}/unquarantine")
async def unquarantine_endpoint(skill_name: str, req: Optional[UnquarantineRequest] = None):
    """F.4.4 C2 D5 — mark a skill proposal as unquarantined (PC-side state).

    Clears quarantine_at + quarantine_reason from skill_proposals row.
    Returns 404 if proposal not found or not currently quarantined.
    NOTE: to restore the YAML file on VM, use the VM unquarantine endpoint
    (POST /api/skills/{name}/unquarantine on hermes-api.caioleao.com via tunnel).
    """
    _ensure_table_or_503()
    reason = (req.reason if req else None) or "manual_unquarantine"

    # First check if the proposal exists
    proposal = proposals_manager.get_by_name(skill_name)
    if proposal is None:
        raise HTTPException(404, f"No skill proposal found for '{skill_name}'")

    # unquarantine() returns False if not quarantined
    updated = unquarantine_skill(skill_name)
    if not updated:
        raise HTTPException(
            409,
            f"Skill '{skill_name}' is not quarantined (quarantine_at is NULL)",
        )

    # Log audit trail in skill_sync_runs
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    run_id = str(uuid.uuid4())
    conn = _connect()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO skill_sync_runs
               (id, trigger_type, pr_number, pr_url, sync_status, started_at,
                completed_at, error_message, affected_skills)
               VALUES (?, 'manual_unquarantine', NULL, NULL, 'unquarantined', ?, ?, ?, ?)""",
            (run_id, now, now, reason, json.dumps([skill_name])),
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

    # WS emit (best-effort)
    try:
        from core.state import ws_manager
        import asyncio
        asyncio.create_task(ws_manager.broadcast({
            "event_type": "brain.skill_unquarantined",
            "payload": {
                "skill_name": skill_name,
                "reason": reason,
                "run_id": run_id,
            },
        }))
    except Exception:
        pass

    return {
        "status": "ok",
        "skill_name": skill_name,
        "message": f"Skill '{skill_name}' unquarantined. Restore YAML on VM via VM endpoint.",
        "run_id": run_id,
    }
