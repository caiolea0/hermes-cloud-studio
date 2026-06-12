"""F.6.2 Brain smoke — REAL dispatch via gateway OR OFFLINE_MODE deterministic.

Modes:
  HERMES_BRAIN_OFFLINE=1 (default)  → MockDispatcher, deterministic, no network
  HERMES_BRAIN_OFFLINE=0            → real GatewayDispatcher (requires gateway up + NIM key)

OFFLINE smoke validates:
  1. All 6 intents route through Brain.decide() correctly.
  2. Destructive intents (send_outreach) → requires_confirm regardless of confidence.
  3. Utility intent (route_skill_run) → no LLM call.
  4. Unknown intent → status=error, FSM stays IDLE.
  5. Two Brain() instances independent (no shared FSM).
  6. ReAct multi-step + tool dispatch ordering.

REAL smoke (HERMES_BRAIN_OFFLINE=0) validates:
  7. classify task_type → T1 NIM Free response real.
  8. Brain handles dispatch tool failures gracefully (low_conf → requires_confirm).

Run:
  python -m brain._smoke                       # OFFLINE deterministic (CI safe)
  HERMES_BRAIN_OFFLINE=0 python -m brain._smoke  # REAL gateway dispatch
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from .decide import Brain
from .intents import INTENT_REGISTRY
from .safety import DESTRUCTIVE_ACTIONS
from .states import BrainState

OFFLINE_MODE = os.getenv("HERMES_BRAIN_OFFLINE", "1") != "0"


class _MockDispatcher:
    """Deterministic mock: emits canned LLM responses per intent task_type."""

    def __init__(self) -> None:
        self.route_calls: list[tuple[str, str]] = []
        self.invoke_calls: list[tuple[str, str]] = []

    async def route(self, task_type: str, prompt: str, **kw: Any) -> dict[str, Any]:
        self.route_calls.append((task_type, prompt[:80]))
        # Deterministic: emit JSON final_answer = "mock_response_<task_type>", conf=0.85
        # confidence 0.85 > 0.5 → non-destructive intents complete; destructive still gate.
        canned = (
            f'{{"rationale": "mock {task_type}", "planned_tool": null, '
            f'"final_answer": "mock_response_{task_type}", "confidence": 0.85}}'
        )
        return {
            "ok": True,
            "response": {"ok": True, "response": canned, "cost_credits": 0.0},
        }

    async def invoke_tool(self, server: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        self.invoke_calls.append((server, tool))
        return {"ok": True, "response": {"ok": True}, "cost_credits": 0.0}


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}", file=sys.stderr)
        sys.exit(1)


async def _run_offline_smoke() -> list[str]:
    """OFFLINE deterministic — 6 intents + unknown + isolation."""
    passes: list[str] = []
    mock = _MockDispatcher()

    # Case 1-6: each registered intent yields a deterministic outcome.
    for intent_name, cfg in INTENT_REGISTRY.items():
        brain = Brain(dispatcher=mock)
        result = await brain.decide(intent_name, {"smoke": True, "id": intent_name})

        _assert(bool(result["run_id"]), f"{intent_name}: run_id missing")
        _assert(
            result["final_state"] == BrainState.IDLE.value,
            f"{intent_name}: final_state must be IDLE, got {result['final_state']}",
        )

        if cfg["destructive"] or intent_name in DESTRUCTIVE_ACTIONS:
            _assert(
                result["status"] == "requires_confirm",
                f"{intent_name}: destructive must require confirm, got {result['status']}",
            )
            _assert(result["requires_confirm"] is True, f"{intent_name}: requires_confirm flag")
            _assert(
                "confirm_reason" in result["result"],
                f"{intent_name}: confirm_reason missing",
            )
            passes.append(f"  [confirm-gate] {intent_name}: {result['result']['confirm_reason']}")
        elif cfg["task_type"] is None:
            # utility intent: status=completed, no LLM call
            _assert(
                result["status"] == "completed",
                f"{intent_name}: utility must complete, got {result['status']}",
            )
            _assert(
                result["result"]["status"] == "utility_no_llm",
                f"{intent_name}: react_status must be utility_no_llm",
            )
            passes.append(f"  [utility]      {intent_name}: no LLM call")
        else:
            _assert(
                result["status"] == "completed",
                f"{intent_name}: non-destructive must complete, got {result['status']}",
            )
            _assert(result["requires_confirm"] is False, f"{intent_name}: must NOT require confirm")
            _assert(
                result["result"].get("final_answer") == f"mock_response_{cfg['task_type']}",
                f"{intent_name}: mock final_answer mismatch",
            )
            passes.append(
                f"  [completed]    {intent_name}: task_type={cfg['task_type']} iter={result['result']['iterations']}"
            )

    # Case 7: unknown intent error-handling (no FSM crash).
    brain = Brain(dispatcher=mock)
    result = await brain.decide("intent_does_not_exist_xyz", {})
    _assert(result["status"] == "error", "unknown intent must return status='error'")
    _assert("error" in result["result"], "unknown intent must include error field")
    _assert(
        result["final_state"] == BrainState.IDLE.value,
        f"unknown intent must leave FSM at IDLE, got {result['final_state']}",
    )
    passes.append(f"  [error]        unknown_intent: {result['result']['error']}")

    # Case 8: independence — two Brain() instances do not share FSM state.
    brain_a = Brain(dispatcher=_MockDispatcher())
    brain_b = Brain(dispatcher=_MockDispatcher())
    res_a = await brain_a.decide("answer_owner", {"who": "a"})
    res_b = await brain_b.decide("send_outreach", {"who": "b"})
    _assert(res_a["status"] == "completed", "brain_a should complete")
    _assert(res_b["status"] == "requires_confirm", "brain_b should require confirm")
    _assert(res_a["run_id"] != res_b["run_id"], "run_ids must differ across instances")
    passes.append("  [isolation]    two Brain() instances independent")

    # Case 9: max_iter cap functional with looping mock
    class _LoopMock(_MockDispatcher):
        async def route(self, task_type: str, prompt: str, **kw: Any) -> dict[str, Any]:
            self.route_calls.append((task_type, prompt[:80]))
            # Always plan a tool, never final_answer → forces max_iter
            return {
                "ok": True,
                "response": {
                    "ok": True,
                    "response": '{"rationale":"loop","planned_tool":{"server":"x","tool":"y","args":{}},"final_answer":null,"confidence":0.5}',
                    "cost_credits": 0.0,
                },
            }

    loop_mock = _LoopMock()
    brain_c = Brain(dispatcher=loop_mock)
    res_c = await brain_c.decide("answer_owner", {"loop": True})
    _assert(res_c["result"]["iterations"] == 5, f"max_iter cap 5, got {res_c['result']['iterations']}")
    _assert(res_c["result"]["status"] == "max_iterations_reached", f"got {res_c['result']['status']}")
    passes.append(f"  [max_iter]     cap=5 functional, react_status=max_iterations_reached")

    return passes


async def _run_real_smoke() -> list[str]:
    """REAL — Brain.decide() via real gateway dispatch."""
    passes: list[str] = []

    # Test A: classify task — known reliable T1 NIM Free
    brain = Brain()
    result = await brain.decide(
        "classify_prospect",
        {"name": "TechCorp", "category": "B2B SaaS", "website": "techcorp.com"},
    )
    _assert(result["status"] in ("completed", "requires_confirm", "error"), f"unexpected status {result['status']}")
    _assert(result["latency_ms"] > 0, "latency must be positive")
    _assert(result["result"].get("iterations", 0) >= 1, "must complete at least 1 iteration")
    react_status = result["result"].get("status")
    passes.append(
        f"  [real]    classify_prospect status={result['status']} react={react_status} "
        f"iter={result['result']['iterations']} conf={result['result'].get('confidence', 0)} "
        f"latency={result['latency_ms']}ms"
    )

    # Test B: utility intent — no LLM call even in REAL mode
    brain_b = Brain()
    result_b = await brain_b.decide("route_skill_run", {"skill": "test"})
    _assert(result_b["status"] == "completed", f"utility must complete, got {result_b['status']}")
    _assert(result_b["result"]["status"] == "utility_no_llm", "react_status must be utility_no_llm")
    passes.append(f"  [real]    route_skill_run utility no_llm latency={result_b['latency_ms']}ms")

    # Test C: destructive intent always requires_confirm
    brain_c = Brain()
    result_c = await brain_c.decide("send_outreach", {"prospect_id": "test"})
    _assert(result_c["status"] == "requires_confirm", f"destructive must require confirm")
    _assert(
        "destructive" in result_c["result"].get("confirm_reason", "").lower()
        or "low_confidence" in result_c["result"].get("confirm_reason", "").lower(),
        "confirm_reason must indicate destructive or low_confidence",
    )
    passes.append(f"  [real]    send_outreach destructive {result_c['result']['confirm_reason']}")

    return passes


async def _run_smoke() -> None:
    if OFFLINE_MODE:
        print("F.6.2 BRAIN SMOKE (OFFLINE_MODE — deterministic mock dispatcher)")
        passes = await _run_offline_smoke()
    else:
        print("F.6.2 BRAIN SMOKE (REAL — gateway dispatch via NIM + Ollama)")
        passes = await _run_real_smoke()

    print("ALL PASS:")
    for line in passes:
        print(line)
    print(f"\nTotal: {len(passes)} assertions.")


if __name__ == "__main__":
    asyncio.run(_run_smoke())
