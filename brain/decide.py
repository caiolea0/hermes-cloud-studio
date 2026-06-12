"""F.6 Brain orchestrator entry point — Brain.decide() main loop.

F.6.1: scaffold + state machine + 6 intents STUBS (deterministic mock).
F.6.2: tool calling REAL via mcp.hermes-llm.route + gateway dispatch + ReAct loop.
F.6.3: memory persistence brain_runs + brain_decisions + agentmemory MCP.
F.6.4: safety gates UX dashboard modal + endpoint POST /api/brain/confirm.
F.6.5: golden cases test suite + hermes-brain-test skill battery.
F.6.6: closeout + Task #6 [completed].

Cross-ref:
  .claude/PLAN.md § F.6 Decisões D1-D10 + F.6.2 D1-D8 (2026-06-12, dd57b64+68f0623)
  .claude/NVIDIA-MODELS-ROUTING-MATRIX.md Task 1 (Brain reasoning)
  mcps/hermes-llm/server.py (Brain consume via gateway route())
  brain/_react.py F.6.2 (ReAct loop multi-step)
  brain/dispatch.py F.6.2 (Gateway HTTP client)
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from .dispatch import GatewayDispatcher
from .intents import INTENT_REGISTRY, handle_intent
from .safety import requires_owner_confirm
from .states import BrainStateMachine

__all__ = ["Brain"]


class Brain:
    """Brain orchestrator. Each instance owns one state machine (thread-independent).

    F.6.2 real dispatch flow:
      1. Validate intent ∈ INTENT_REGISTRY → else error short-circuit.
      2. FSM IDLE → CLASSIFY → REASON → ACT.
      3. ACT: handle_intent → react_loop (gateway dispatch via mcp.hermes-llm.route + tools).
      4. FSM ACT → REVIEW: run safety gate (D8 hybrid).
      5a. If requires_confirm → FSM REVIEW → IDLE (paused), return status='requires_confirm'.
      5b. Else → FSM REVIEW → COMMIT → IDLE, return status='completed'.

    F.6.2 NÃO persiste brain_runs/decisions (F.6.3 entrega).
    F.6.2 NÃO renderiza UI confirm modal (F.6.4 entrega).
    F.6.2 NÃO implementa replay (F.6.3 entrega).
    F.6.2 NÃO chama linkedin/* direto — sempre via mcp.hermes-linkedin.* gateway dispatch (BLACKLIST R2).
    """

    def __init__(self, dispatcher: GatewayDispatcher | None = None) -> None:
        self.fsm = BrainStateMachine()
        self.dispatcher = dispatcher or GatewayDispatcher()

    async def decide(self, intent: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Main Brain.decide() loop. F.6.2 real LLM dispatch + ReAct multi-step.

        Args:
            intent: one of INTENT_REGISTRY keys (else returns error).
            context: arbitrary dict passed to ReAct prompt builder.

        Returns:
            {
              run_id: str,
              status: 'completed' | 'requires_confirm' | 'error',
              result: dict,                  # intent_result enriched (final_answer, iterations, accumulated, ...)
              requires_confirm: bool,
              latency_ms: int,
              total_cost_credits: float,     # F.6.2 derived from sum(accumulated[*].tool_result.cost_credits)
              final_state: str,              # last FSM state (IDLE after completion)
            }
        """
        ctx = context or {}
        run_id = str(uuid.uuid4())
        start = time.monotonic()

        # Defensive: unknown intent short-circuit (no FSM transitions to avoid invalid state).
        if intent not in INTENT_REGISTRY:
            return {
                "run_id": run_id,
                "status": "error",
                "result": {"error": f"unknown_intent:{intent}"},
                "requires_confirm": False,
                "latency_ms": int((time.monotonic() - start) * 1000),
                "total_cost_credits": 0.0,
                "final_state": self.fsm.current_state,
            }

        # FSM forward: IDLE → CLASSIFY → REASON → ACT
        self.fsm.start_classify()  # type: ignore[attr-defined]
        self.fsm.to_reason()  # type: ignore[attr-defined]
        self.fsm.to_act()  # type: ignore[attr-defined]

        # F.6.2 real dispatch: handle_intent → react_loop → gateway dispatch.
        intent_result = await handle_intent(intent, ctx, dispatcher=self.dispatcher)

        # FSM ACT → REVIEW (safety gate)
        self.fsm.to_review()  # type: ignore[attr-defined]

        confidence = float(intent_result.get("confidence", 0.5))
        intent_destructive = bool(INTENT_REGISTRY[intent].get("destructive", False))
        # F.6.2 action_class: usa intent quando destructive (F.future: derivar de tool sequence).
        action_class = intent if intent_destructive else ""

        needs_confirm, reason = requires_owner_confirm(intent, confidence, action_class)

        # F.6.2 cost real (W6 reviewer F.6.1) — vem do react_result.cost_credits aggregated.
        total_cost = float(intent_result.get("cost_credits", 0.0) or 0.0)

        latency_ms = int((time.monotonic() - start) * 1000)

        if needs_confirm:
            self.fsm.owner_confirm_required()  # type: ignore[attr-defined]  # REVIEW → IDLE (paused)
            return {
                "run_id": run_id,
                "status": "requires_confirm",
                "result": {**intent_result, "confirm_reason": reason},
                "requires_confirm": True,
                "latency_ms": latency_ms,
                "total_cost_credits": total_cost,
                "final_state": self.fsm.current_state,
            }

        # FSM REVIEW → COMMIT → IDLE
        self.fsm.to_commit()  # type: ignore[attr-defined]
        # F.6.3 persistence happens HERE — F.6.2 placeholder no-op.
        self.fsm.complete()  # type: ignore[attr-defined]

        # Status: completed se ok=True OR react_result indicou utility_no_llm (route_skill_run).
        # llm_dispatch_failed OR max_iterations_reached → status='error' (Brain.decide() perspective).
        result_status = intent_result.get("status", "completed")
        if intent_result.get("ok") or result_status == "utility_no_llm":
            decide_status = "completed"
        else:
            decide_status = "error"

        return {
            "run_id": run_id,
            "status": decide_status,
            "result": intent_result,
            "requires_confirm": False,
            "latency_ms": latency_ms,
            "total_cost_credits": total_cost,
            "final_state": self.fsm.current_state,
        }
