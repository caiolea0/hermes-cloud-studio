"""F.6.1 Brain smoke test — deterministic, isolated, no network/LLM.

Validates:
  1. All 6 intents in INTENT_REGISTRY dispatch successfully (status='completed')
     EXCEPT destructive intents which return status='requires_confirm'.
  2. Unknown intent returns status='error' (no FSM crash).
  3. State machine ends at IDLE after every run.
  4. Multiple Brain() instances are independent (no shared state).
  5. Safety gates (D8) trigger correctly for destructive intents.

Run: python -m brain._smoke
"""
from __future__ import annotations

import asyncio
import sys

from .decide import Brain
from .intents import INTENT_REGISTRY
from .safety import DESTRUCTIVE_ACTIONS
from .states import BrainState


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}", file=sys.stderr)
        sys.exit(1)


async def _run_smoke() -> None:
    passes: list[str] = []

    # Case 1-6: each registered intent yields a deterministic outcome.
    for intent_name, cfg in INTENT_REGISTRY.items():
        brain = Brain()
        result = await brain.decide(intent_name, {"smoke": True, "id": intent_name})

        _assert(result["run_id"], f"{intent_name}: run_id missing")
        _assert(
            result["final_state"] == BrainState.IDLE.value,
            f"{intent_name}: final_state must be IDLE, got {result['final_state']}",
        )
        _assert(result["total_cost_credits"] == 0.0, f"{intent_name}: F.6.1 cost must be 0.0")
        _assert(isinstance(result["latency_ms"], int), f"{intent_name}: latency_ms must be int")

        if cfg["destructive"] or intent_name in DESTRUCTIVE_ACTIONS:
            _assert(
                result["status"] == "requires_confirm",
                f"{intent_name}: destructive intent must require confirm, got {result['status']}",
            )
            _assert(result["requires_confirm"] is True, f"{intent_name}: requires_confirm flag")
            _assert(
                "confirm_reason" in result["result"],
                f"{intent_name}: confirm_reason missing",
            )
            passes.append(f"  [confirm-gate] {intent_name}: {result['result']['confirm_reason']}")
        else:
            _assert(
                result["status"] == "completed",
                f"{intent_name}: non-destructive must complete, got {result['status']}",
            )
            _assert(result["requires_confirm"] is False, f"{intent_name}: requires_confirm must be False")
            _assert(result["result"].get("ok") is True, f"{intent_name}: result.ok must be True")
            passes.append(f"  [completed]    {intent_name}: task_type={result['result'].get('task_type')}")

    # Case 7: unknown intent error-handling (no FSM crash).
    brain = Brain()
    result = await brain.decide("intent_does_not_exist_xyz", {})
    _assert(result["status"] == "error", "unknown intent must return status='error'")
    _assert("error" in result["result"], "unknown intent must include error field")
    _assert(
        result["final_state"] == BrainState.IDLE.value,
        f"unknown intent must leave FSM at IDLE, got {result['final_state']}",
    )
    passes.append(f"  [error]        unknown_intent: {result['result']['error']}")

    # Case 8: independence — two Brain() instances do not share FSM state.
    brain_a = Brain()
    brain_b = Brain()
    res_a = await brain_a.decide("answer_owner", {"who": "a"})
    res_b = await brain_b.decide("send_outreach", {"who": "b"})
    _assert(res_a["status"] == "completed", "brain_a should complete")
    _assert(res_b["status"] == "requires_confirm", "brain_b should require confirm")
    _assert(res_a["run_id"] != res_b["run_id"], "run_ids must differ across instances")
    passes.append("  [isolation]    two Brain() instances independent (no shared FSM)")

    print("F.6.1 BRAIN SMOKE — ALL PASS")
    for line in passes:
        print(line)
    print(f"Total: {len(passes)} assertions, {len(INTENT_REGISTRY)} intents + 1 unknown + 1 isolation case.")


if __name__ == "__main__":
    asyncio.run(_run_smoke())
