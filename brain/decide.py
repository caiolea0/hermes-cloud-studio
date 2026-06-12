"""F.6 Brain orchestrator entry point — Brain.decide() main loop.

F.6.1: scaffold + state machine + 6 intents STUBS (deterministic mock).
F.6.2: tool calling integration real via mcp.hermes-llm.route + gateway dispatch.
F.6.3: memory persistence brain_runs + brain_decisions + agentmemory MCP.
F.6.4: safety gates UX dashboard modal + endpoint POST /api/brain/confirm.
F.6.5: golden cases test suite + hermes-brain-test skill battery.
F.6.6: closeout + Task #6 [completed].

Cross-ref:
  .claude/PLAN.md § F.6 Decisões Cristalizadas D1-D10 (2026-06-12, dd57b64)
  .claude/NVIDIA-MODELS-ROUTING-MATRIX.md Task 1 (Brain reasoning)
  mcps/hermes-llm/server.py (Brain consume via gateway route())
  mem_mqae0827 (D1-D10 ground truth)
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from .intents import INTENT_REGISTRY, handle_intent
from .safety import requires_owner_confirm
from .states import BrainStateMachine

__all__ = ["Brain"]


class Brain:
    """Brain orchestrator. Each instance owns one state machine (thread-independent).

    F.6.1 deterministic stub flow:
      1. Validate intent ∈ INTENT_REGISTRY → else error short-circuit.
      2. FSM IDLE → CLASSIFY → REASON → ACT (mock dispatch via handle_intent).
      3. FSM ACT → REVIEW: run safety gate (D8 hybrid).
      4a. If requires_confirm → FSM REVIEW → IDLE (paused), return status='requires_confirm'.
      4b. Else → FSM REVIEW → COMMIT → IDLE, return status='completed'.

    F.6.1 NÃO persiste brain_runs/decisions (F.6.3 entrega).
    F.6.1 NÃO chama LLM real (F.6.2 entrega).
    F.6.1 NÃO chama mcps/* direto (sempre via gateway dispatch in F.6.2).
    """

    def __init__(self) -> None:
        self.fsm = BrainStateMachine()

    async def decide(self, intent: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Main Brain.decide() loop. F.6.1 stub returns deterministic mock per intent.

        Args:
            intent: one of INTENT_REGISTRY keys (else returns error).
            context: arbitrary dict passed to intent handler (mocked F.6.1).

        Returns:
            {
              run_id: str,
              status: 'completed' | 'requires_confirm' | 'error',
              result: dict,                  # intent_result OR {error}
              requires_confirm: bool,
              latency_ms: int,
              total_cost_credits: float,     # F.6.1 always 0.0 (no LLM call)
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

        # F.6.1 mock dispatch (handle_intent returns deterministic stub).
        # F.6.2: real dispatch invokes mcp.hermes-llm.route + tools via gateway.
        intent_result = await handle_intent(intent, ctx)

        # FSM ACT → REVIEW (safety gate)
        self.fsm.to_review()  # type: ignore[attr-defined]

        confidence = float(intent_result.get("confidence", 0.85))
        # action_class: F.6.1 uses intent itself when destructive flag set
        # (F.6.2 will derive from tool sequence chosen by Brain reasoning).
        intent_destructive = bool(INTENT_REGISTRY[intent].get("destructive", False))
        action_class = intent if intent_destructive else ""

        needs_confirm, reason = requires_owner_confirm(intent, confidence, action_class)

        if needs_confirm:
            self.fsm.owner_confirm_required()  # type: ignore[attr-defined]  # REVIEW → IDLE (paused)
            return {
                "run_id": run_id,
                "status": "requires_confirm",
                "result": {**intent_result, "confirm_reason": reason},
                "requires_confirm": True,
                "latency_ms": int((time.monotonic() - start) * 1000),
                "total_cost_credits": 0.0,
                "final_state": self.fsm.current_state,
            }

        # FSM REVIEW → COMMIT → IDLE
        self.fsm.to_commit()  # type: ignore[attr-defined]
        # F.6.3 persistence happens HERE — F.6.1 placeholder no-op.
        self.fsm.complete()  # type: ignore[attr-defined]

        return {
            "run_id": run_id,
            "status": "completed",
            "result": intent_result,
            "requires_confirm": False,
            "latency_ms": int((time.monotonic() - start) * 1000),
            "total_cost_credits": 0.0,
            "final_state": self.fsm.current_state,
        }
