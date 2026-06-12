"""F.6 Brain orchestrator FastAPI router.

F.6.1: scaffold endpoints + Pydantic schemas (this commit).
F.6.2: tool calling real via gateway dispatch.
F.6.3: GET /api/brain/runs/{id} reads brain_runs + brain_decisions.
F.6.4: POST /api/brain/confirm/{id} dashboard modal handler.
F.6.5: golden-cases bateria via hermes-brain-test skill.

Endpoints (F.6.1):
  POST /api/brain/decide        — main decision loop (real F.6.1 stub deterministic)
  GET  /api/brain/runs/{run_id} — load past run (F.6.3 implementa; F.6.1 stub 501)
  POST /api/brain/confirm/{run_id} — owner confirm (F.6.4 implementa; F.6.1 stub 501)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from brain.decide import Brain
from brain.intents import INTENT_REGISTRY

router = APIRouter(prefix="/api/brain", tags=["brain"])


class BrainDecideRequest(BaseModel):
    """Input schema for POST /api/brain/decide (D9)."""

    intent: str = Field(..., description="Intent key from INTENT_REGISTRY (6 entries F.6.1)")
    context: dict[str, Any] = Field(default_factory=dict, description="Arbitrary input for intent handler")
    max_latency_ms: int = Field(default=30000, ge=100, le=300000, description="Soft latency budget")
    force_provider: str = Field(default="", description="F.6.2 routing matrix override (T1/T2/T3/T4 LLM tier)")


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
    """F.6.4 owner confirm payload (F.6.1 endpoint stub 501)."""

    approve: bool
    reason: str = ""


@router.post("/decide", response_model=BrainDecideResponse)
async def brain_decide(req: BrainDecideRequest) -> BrainDecideResponse:
    """F.6.1: deterministic stub via Brain.decide() — mock data per intent.

    F.6.2: invokes real LLM via mcp.hermes-llm.route(prompt, task_type) per intent config,
           then dispatches default_tools through ContextForge gateway.
    """
    brain = Brain()
    result = await brain.decide(req.intent, req.context)
    return BrainDecideResponse(**result)


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> JSONResponse:
    """F.6.3 implementa real (DB read brain_runs + brain_decisions). F.6.1 stub."""
    return JSONResponse(
        status_code=501,
        content={
            "error": "not_implemented_f63",
            "run_id": run_id,
            "message": "Run lookup implementado em F.6.3 (memory persistence sub-session).",
        },
    )


@router.post("/confirm/{run_id}")
async def confirm_run(run_id: str, payload: BrainConfirmRequest) -> JSONResponse:
    """F.6.4 implementa real (UI dashboard modal + state resume). F.6.1 stub."""
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
            }
            for name, cfg in INTENT_REGISTRY.items()
        ],
    }
