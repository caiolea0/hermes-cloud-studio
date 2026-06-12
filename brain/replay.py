"""F.6 Brain decision replay (D7 cristalizado).

F.6.1 STUB — endpoints return 501 not_implemented.
F.6.3 IMPLEMENTS REAL — load brain_runs + brain_decisions, reconstruct
       sequence of state transitions + tool calls + final result.

D7: replay is CLI/API only — NO UI tab (F.future when F.8 cost observability
dashboard lands, cross-ref F.8).
"""
from __future__ import annotations

from typing import Any


async def replay_run(run_id: str) -> dict[str, Any]:
    """F.6.1 stub. F.6.3 implements real replay via DB read.

    Expected F.6.3 return shape:
      {
        "run_id": str,
        "intent": str,
        "context": dict,
        "transitions": [{"state_from","state_to","tool_invoked","tool_args","tool_result","rationale","latency_ms"}],
        "final_state": str,
        "final_result": dict,
        "total_latency_ms": int,
        "total_cost_credits": float,
        "confidence_score": float,
      }
    """
    return {
        "error": "not_implemented_f63",
        "run_id": run_id,
        "message": "Decision replay implementado em F.6.3 (memory persistence).",
    }


async def list_runs(intent: str | None = None, limit: int = 50) -> dict[str, Any]:
    """F.6.1 stub. F.6.3 implements real listing via DB query."""
    return {
        "error": "not_implemented_f63",
        "filter_intent": intent,
        "limit": limit,
        "message": "Run listing implementado em F.6.3 (memory persistence).",
    }
