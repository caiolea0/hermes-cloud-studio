"""F.6 Brain orchestrator FastAPI router.

F.6.1: scaffold endpoints + Pydantic schemas.
F.6.2: tool calling real via gateway dispatch.
F.6.3: GET /runs/{id} + POST /replay/{id} return 200 with persisted run + decisions.
F.6.4: POST /confirm/{id} dashboard modal handler.
F.6.5: golden-cases bateria via hermes-brain-test skill.

Endpoints (F.6.3):
  POST /api/brain/decide        — main decision loop (F.6.2 real via gateway dispatch)
  GET  /api/brain/runs          — list recent runs (F.6.3 REAL — optional ?intent filter)
  GET  /api/brain/runs/{run_id} — load past run (F.6.3 REAL — 200 with run + decisions)
  POST /api/brain/replay/{run_id} — show recorded replay (F.6.3 REAL — read-only)
  POST /api/brain/confirm/{run_id} — owner confirm (F.6.4 stub 501)
  GET  /api/brain/intents       — list registered intents (F.6.1)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from brain.decide import Brain
from brain.intents import INTENT_REGISTRY
from brain.replay import list_runs, replay_run

router = APIRouter(prefix="/api/brain", tags=["brain"])


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
    """F.6.4 owner confirm payload (F.6.3 endpoint still stub 501)."""

    approve: bool
    reason: str = ""


@router.post("/decide", response_model=BrainDecideResponse)
async def brain_decide(req: BrainDecideRequest) -> BrainDecideResponse:
    """F.6.2: invokes real LLM via mcp.hermes-llm.route per intent config + ReAct loop.
    F.6.3: persists run + per-transition decisions; opt-in agentmemory MCP save async.
    """
    brain = Brain()
    result = await brain.decide(req.intent, req.context, requester=req.requester)
    return BrainDecideResponse(**result)


@router.get("/runs")
async def list_brain_runs(
    intent: str | None = Query(default=None, description="Filter by intent name (optional)"),
    limit: int = Query(default=50, ge=1, le=500, description="Max rows returned"),
) -> JSONResponse:
    """F.6.3 REAL — list recent brain_runs."""
    result = await list_runs(intent=intent, limit=limit)
    status = 200 if result.get("ok") else 500
    return JSONResponse(status_code=status, content=result)


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> JSONResponse:
    """F.6.3 REAL — load brain_runs row + brain_decisions ordered by sequence ASC.

    Returns 200 + replay payload (show_recorded mode).
    Returns 404 if run_id not found.
    """
    result = await replay_run(run_id, mode="show_recorded")
    if not result.get("ok"):
        if result.get("error") == "run_not_found":
            return JSONResponse(status_code=404, content=result)
        return JSONResponse(status_code=500, content=result)
    return JSONResponse(status_code=200, content=result)


@router.post("/replay/{run_id}")
async def post_replay(run_id: str, mode: str = Query(default="show_recorded")) -> JSONResponse:
    """F.6.3 REAL — POST replay (semantic: explicit action). Identical payload GET /runs/{id}.

    POST chosen for client mental model (replay is an action), parity with GET for cache-friendliness.
    """
    result = await replay_run(run_id, mode=mode)
    if not result.get("ok"):
        if result.get("error") == "run_not_found":
            return JSONResponse(status_code=404, content=result)
        return JSONResponse(status_code=500, content=result)
    return JSONResponse(status_code=200, content=result)


@router.post("/confirm/{run_id}")
async def confirm_run(run_id: str, payload: BrainConfirmRequest) -> JSONResponse:
    """F.6.4 implementa real (UI dashboard modal + state resume). F.6.3 stub preserved."""
    return JSONResponse(
        status_code=501,
        content={
            "error": "not_implemented_f64",
            "run_id": run_id,
            "approve": payload.approve,
            "message": "Owner confirm implementado em F.6.4 (safety UX sub-session).",
        },
    )


@router.get("/intents")
async def list_intents() -> dict[str, Any]:
    """F.6.1 utility — list registered intents + metadata (UI dashboard F.6.4 will consume)."""
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
