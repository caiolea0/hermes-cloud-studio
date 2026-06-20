"""F.6 Brain orchestrator FastAPI router.

F.6.1: scaffold endpoints + Pydantic schemas.
F.6.2: tool calling real via gateway dispatch.
F.6.3: GET /runs/{id} + POST /replay/{id} return 200 with persisted run + decisions.
F.6.4: POST /confirm/{id} REAL (501→200) — owner approve/deny + optional 500-char comment
       + resume_from_run_id deterministic + WS broadcast brain.run_confirm_resolved.
       GET /runs aceita ?status filter (rehydrate drawer page-reload).
F.6.5: golden-cases bateria via hermes-brain-test skill.

Endpoints (F.6.4):
  POST /api/brain/decide        — main decision loop (F.6.2 real via gateway dispatch)
  GET  /api/brain/runs          — list recent runs (?intent + ?status filters)
  GET  /api/brain/runs/{run_id} — load past run (run + decisions)
  POST /api/brain/replay/{run_id} — show recorded replay (read-only)
  POST /api/brain/confirm/{run_id} — owner approve/deny REAL + resume + WS broadcast
  GET  /api/brain/intents       — list registered intents
"""
from __future__ import annotations

import json
import os
import time
from collections import deque
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

# UX-RM-F5-A — per-process sliding window rate limit for SSE stream endpoint.
_BRAIN_STREAM_RPM: int = int(os.environ.get("BRAIN_STREAM_MAX_RPM", "10"))
_BRAIN_STREAM_TIMESTAMPS: deque[float] = deque()


def _check_stream_rate_limit() -> bool:
    """Sliding window 60s — returns True if request is within limit, False if exceeded."""
    now = time.monotonic()
    while _BRAIN_STREAM_TIMESTAMPS and now - _BRAIN_STREAM_TIMESTAMPS[0] > 60.0:
        _BRAIN_STREAM_TIMESTAMPS.popleft()
    if len(_BRAIN_STREAM_TIMESTAMPS) >= _BRAIN_STREAM_RPM:
        return False
    _BRAIN_STREAM_TIMESTAMPS.append(now)
    return True

from brain.decide import Brain
from brain.dispatch import sanitize
from brain.intents import INTENT_REGISTRY
from brain.replay import list_runs, replay_run

router = APIRouter(prefix="/api/brain", tags=["brain"])


class BrainStreamRequest(BaseModel):
    """Input schema for POST /api/brain/stream-decide (UX-RM-F5-A/B)."""

    prompt: str = Field(..., min_length=1, max_length=2000, description="Natural language query for Brain AI mode")
    context: dict[str, Any] = Field(default_factory=dict, description="Ambient context (current page, etc.)")
    intent_hint: str | None = Field(default=None, description="Optional INTENT_REGISTRY key; defaults to answer_owner")
    # F5-B multimodal: base64-encoded image, client-side 5MB guard, server-side 10MB cap.
    image_b64: str | None = Field(
        default=None,
        max_length=13_981_016,  # ceil(10MB * 4/3) base64 overhead
        description="F5-B multimodal: base64-encoded image (max ~10MB decoded). 501 stub until vision configured.",
    )


class BrainDecideRequest(BaseModel):
    """Input schema for POST /api/brain/decide (D9)."""

    intent: str = Field(..., description="Intent key from INTENT_REGISTRY (6 entries F.6.1)")
    context: dict[str, Any] = Field(default_factory=dict, description="Arbitrary input for intent handler")
    max_latency_ms: int = Field(default=30000, ge=100, le=300000, description="Soft latency budget")
    force_provider: str = Field(default="", description="F.6.2 routing matrix override (T1/T2/T3/T4 LLM tier)")
    requester: str = Field(default="api", description="F.6.3 owner/daemon/api/cron tag persisted brain_runs")


class BrainDecideResponse(BaseModel):
    """Output schema (D9)."""

    run_id: str
    status: str  # 'completed' | 'requires_confirm' | 'error'
    result: dict[str, Any]
    requires_confirm: bool = False
    latency_ms: int = 0
    total_cost_credits: float = 0.0
    final_state: str = "IDLE"


class BrainConfirmRequest(BaseModel):
    """F.6.4 owner confirm payload — D2: action + optional 500-char comment.

    action: 'approve' | 'deny' | 'cancel' (cancel is server-side coded deny w/ owner_canceled).
    comment: optional rationale 500 chars max; sanitized server-side (SENSITIVE_KEYS).
    """

    action: str = Field(..., pattern="^(approve|deny|cancel)$")
    comment: str = Field(default="", max_length=500)


async def _emit_ws_event(event_type: str, payload: dict[str, Any]) -> None:
    """Fire-and-forget WS broadcast — never raises (BackgroundTasks bg).

    F.6.4 D4: dot-notation canonical brain.* namespace (F.2.3 pattern).
    """
    try:
        # Lazy import — evita circular core.state ↔ api.brain
        from core.state import ws_manager
        await ws_manager.broadcast({"event_type": event_type, **payload})
    except Exception:  # noqa: BLE001 — WS non-critical
        from core.sentry_via_gateway import capture_exception as _sentry_capture
        _sentry_capture(requester="brain-core")


def _build_awaiting_payload(decide_result: dict[str, Any]) -> dict[str, Any]:
    """F.6.4 D4 — assemble brain.run_awaiting_confirm WS payload (summary card source)."""
    res = decide_result.get("result") or {}
    final_answer = res.get("final_answer")
    summary_what = str(final_answer)[:200] if final_answer else f"intent={res.get('intent', '')}"
    return {
        "run_id": decide_result.get("run_id"),
        "intent": res.get("intent", ""),
        "action_class": res.get("action_class", "") or (res.get("intent", "") if res.get("destructive") else ""),
        "confidence": float(res.get("confidence", 0.0) or 0.0),
        "confirm_reason": res.get("confirm_reason", ""),
        "started_at": datetime.utcnow().isoformat() + "Z",
        "summary_card": {
            "what": summary_what,
            "why": res.get("confirm_reason", ""),
            "cost": float(decide_result.get("total_cost_credits", 0.0) or 0.0),
            "iterations": int(res.get("iterations", 0) or 0),
        },
    }


@router.post("/stream-decide")
async def stream_decide(body: BrainStreamRequest, bg: BackgroundTasks) -> StreamingResponse:
    """UX-RM-F5-A — SSE stream of Brain.decide() ReAct trace for Cmd+K AI mode.

    Rate limited: BRAIN_STREAM_MAX_RPM requests/min (default 10).
    Event types: thought | tool_call | tool_result | final | error.
    SSE format: data: <json>\n\n (spec-compliant, AbortController friendly).
    Auth: X-Hermes-Token via existing auth_middleware (all /api/* routes).
    """
    if not _check_stream_rate_limit():
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit excedido: máx {_BRAIN_STREAM_RPM} queries/min. Tente em 60s.",
            headers={"Retry-After": "60"},
        )

    brain = Brain()

    async def event_stream():
        last_event: dict[str, Any] = {}
        try:
            async for event in brain.stream_decide(
                prompt=body.prompt,
                context=body.context,
                intent_hint=body.intent_hint,
                image_b64=body.image_b64,
            ):
                last_event = event
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)[:200]})}\n\n"

        # WS telemetry after stream ends (audit trail brain.ai_query_used)
        try:
            from core.state import ws_manager
            intent_resolved = last_event.get("intent", body.intent_hint or "answer_owner")
            await ws_manager.broadcast({
                "event_type": "brain.ai_query_used",
                "prompt_length": len(body.prompt),
                "intent": intent_resolved,
                "status": last_event.get("status", "unknown") if last_event.get("type") == "final" else "incomplete",
            })
        except Exception:  # noqa: BLE001 — telemetry non-critical
            pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/decide", response_model=BrainDecideResponse)
async def brain_decide(req: BrainDecideRequest, bg: BackgroundTasks) -> BrainDecideResponse:
    """F.6.2: invokes real LLM via mcp.hermes-llm.route per intent config + ReAct loop.
    F.6.3: persists run + per-transition decisions; opt-in agentmemory MCP save async.
    F.6.4: WS broadcast brain.run_awaiting_confirm fire-and-forget se requires_confirm.

    Caller: daemon/orchestrator.py _cobaia_run_warmup_action (via brain_decide_via_gateway),
    pipeline_engine.py route_skill_run fast-path, and internal HTTP calls from server.py.
    No dashboard SPA caller — this is a backend-to-backend endpoint.
    """
    brain = Brain()
    result = await brain.decide(req.intent, req.context, requester=req.requester)
    if result.get("requires_confirm"):
        bg.add_task(_emit_ws_event, "brain.run_awaiting_confirm", _build_awaiting_payload(result))
    return BrainDecideResponse(**result)


@router.get("/runs")
async def list_brain_runs(
    intent: str | None = Query(default=None, description="Filter by intent name (optional)"),
    status: str | None = Query(default=None, description="Filter by final_state (F.6.4: 'requires_confirm', etc)"),
    limit: int = Query(default=50, ge=1, le=500, description="Max rows returned"),
) -> JSONResponse:
    """F.6.3 REAL — list recent brain_runs. F.6.4 added ?status filter."""
    result = await list_runs(intent=intent, limit=limit, status=status)
    code = 200 if result.get("ok") else 500
    return JSONResponse(status_code=code, content=result)


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> JSONResponse:
    """F.6.3 REAL — load brain_runs row + brain_decisions ordered by sequence ASC."""
    result = await replay_run(run_id, mode="show_recorded")
    if not result.get("ok"):
        if result.get("error") == "run_not_found":
            return JSONResponse(status_code=404, content=result)
        return JSONResponse(status_code=500, content=result)
    return JSONResponse(status_code=200, content=result)


@router.post("/replay/{run_id}")
async def post_replay(run_id: str, mode: str = Query(default="show_recorded")) -> JSONResponse:
    """F.6.3 REAL — POST replay (semantic: explicit action).
    Admin/debug endpoint — no dashboard SPA caller. Used by CLI and brain test skill.
    """
    result = await replay_run(run_id, mode=mode)
    if not result.get("ok"):
        if result.get("error") == "run_not_found":
            return JSONResponse(status_code=404, content=result)
        return JSONResponse(status_code=500, content=result)
    return JSONResponse(status_code=200, content=result)


@router.post("/confirm/{run_id}")
async def confirm_run(
    run_id: str,
    payload: BrainConfirmRequest,
    bg: BackgroundTasks,
) -> JSONResponse:
    """F.6.4 REAL — owner approve/deny resume_from_run_id + persist owner_comment + WS broadcast.

    D2 (action + optional 500-char comment) + D4 (WS resolved) + D6 (deterministic state restore).
    D5 (forever pending) — endpoint só age sob comando explícito owner.

    Returns:
      200 OK  on success
      404     if run_id not found
      409     if run not in 'requires_confirm' state (idempotent re-check)
    """
    # Sanitize comment via SENSITIVE_KEYS (defense-in-depth — Pydantic max_length already capped 500).
    raw_comment = (payload.comment or "").strip()
    sanitized = sanitize({"comment": raw_comment})
    safe_comment = str(sanitized.get("comment") or "")[:500]

    if payload.action == "cancel":
        approved = False
        # D2 explicit UX — auto-prepend owner_canceled marker if no comment.
        if not safe_comment:
            safe_comment = "owner_canceled"
        else:
            safe_comment = f"owner_canceled: {safe_comment}"[:500]
    else:
        approved = payload.action == "approve"

    brain = Brain()
    result = await brain.resume_from_run_id(run_id, approved=approved, comment=safe_comment)

    if not result.get("ok"):
        err = result.get("error", "unknown")
        if err == "run_not_found":
            return JSONResponse(status_code=404, content={"ok": False, "error": err, "run_id": run_id})
        if err == "not_awaiting_confirm":
            return JSONResponse(
                status_code=409,
                content={
                    "ok": False,
                    "error": err,
                    "run_id": run_id,
                    "current_state": result.get("current_state"),
                    "detail": "Run already resolved by another owner tab (optimistic lock).",
                },
            )
        return JSONResponse(status_code=500, content=result)

    # D4 — WS broadcast resolved (other tabs sync; drawer removes pending card)
    bg.add_task(
        _emit_ws_event,
        "brain.run_confirm_resolved",
        {
            "run_id": run_id,
            "action": payload.action,
            "approved": approved,
            "final_state": result.get("final_state"),
            "resolved_at": datetime.utcnow().isoformat() + "Z",
        },
    )

    return JSONResponse(status_code=200, content=result)


@router.get("/queue-stats")
async def brain_queue_stats() -> dict[str, Any]:
    """F8-B — brain queue stats for cobaia operator badge.

    Returns counts of brain_runs in each state:
      pending      — requires_confirm (awaiting owner approval)
      processing   — NULL final_state started in last 10 min (still running)
      decided_today — completed today
    Graceful: returns zeros if table missing or error.
    """
    import datetime
    import sqlite3 as _sqlite3

    from brain.persistence import _DEFAULT_DB

    db_path = _DEFAULT_DB
    try:
        conn = _sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = _sqlite3.Row
        tbl = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='brain_runs'"
        ).fetchone()
        if not tbl:
            conn.close()
            return {"pending": 0, "processing": 0, "decided_today": 0}
        pending = conn.execute(
            "SELECT COUNT(*) AS c FROM brain_runs WHERE final_state='requires_confirm'"
        ).fetchone()["c"]
        processing = conn.execute(
            "SELECT COUNT(*) AS c FROM brain_runs"
            " WHERE final_state IS NULL AND started_at > datetime('now', '-10 minutes')"
        ).fetchone()["c"]
        today_str = datetime.date.today().isoformat()
        decided_today = conn.execute(
            "SELECT COUNT(*) AS c FROM brain_runs"
            " WHERE final_state='completed' AND date(finished_at) = ?",
            (today_str,),
        ).fetchone()["c"]
        conn.close()
        return {"pending": int(pending), "processing": int(processing), "decided_today": int(decided_today)}
    except Exception as exc:  # noqa: BLE001 — graceful non-critical
        return {"pending": 0, "processing": 0, "decided_today": 0, "error": str(exc)[:100]}


@router.get("/intents")
async def list_intents() -> dict[str, Any]:
    """F.6.1 utility — list registered intents + metadata.
    Admin/debug endpoint — no dashboard SPA caller today. Future F.6.4 UI may consume.
    """
    return {
        "count": len(INTENT_REGISTRY),
        "intents": [
            {
                "name": name,
                "description": cfg["description"],
                "task_type": cfg["task_type"],
                "destructive": cfg["destructive"],
                "tools_available": cfg["default_tools"],
                "agentmemory_save": cfg.get("agentmemory_save", False),
            }
            for name, cfg in INTENT_REGISTRY.items()
        ],
    }
