"""F.6.5 Brain golden cases regression test suite.

Executes 12 YAML cases (2 per intent × 6 intents) through Brain.decide()
with GoldenMockDispatcher and asserts expected outcomes deterministically.

Run:
  pytest tests/test_brain_golden.py -v
  pytest tests/test_brain_golden.py -n auto      # parallel via pytest-xdist
  pytest tests/ -m golden                        # all golden marker

Cross-ref:
  .claude/PLAN.md § F.6.5 D1-D6
  tests/conftest.py (loader + GoldenMockDispatcher + fixtures)
  .claude/brain-golden-cases/*.yaml
"""
from __future__ import annotations

from typing import Any

import pytest

from tests.conftest import load_all_golden_cases

# Load once at collection time — pytest parametrize materializes the list.
# Schema validation errors raise here, failing collection loud (não silently skipped).
CASES = load_all_golden_cases()


@pytest.mark.golden
@pytest.mark.parametrize(
    "case",
    CASES,
    ids=[c["_file"].replace(".yaml", "") for c in CASES],
)
async def test_brain_golden_case(
    case: dict[str, Any],
    brain_instance,
    mock_dispatcher_factory,
) -> None:
    """Execute one golden case + assert expected outcome.

    Each case YAML defines: intent, context, mock_dispatcher_responses, expected.
    Brain.decide() runs end-to-end against the mock — no network, no real LLM.
    """
    dispatcher = mock_dispatcher_factory(case.get("mock_dispatcher_responses", {}))
    brain_instance.dispatcher = dispatcher

    result = await brain_instance.decide(case["intent"], case.get("context", {}))

    expected = case["expected"]
    file_id = case["_file"]

    # ----- mandatory checks ----------------------------------------------
    assert result["status"] == expected["status"], (
        f"{file_id}: status mismatch — got {result['status']!r}, "
        f"expected {expected['status']!r}"
    )
    assert result["requires_confirm"] == expected["requires_confirm"], (
        f"{file_id}: requires_confirm mismatch — "
        f"got {result['requires_confirm']}, expected {expected['requires_confirm']}"
    )

    # ----- optional checks (None → skip) ---------------------------------
    if expected.get("intent_classified"):
        # Brain echoes intent name in result.intent (handle_intent).
        actual_intent = result["result"].get("intent")
        assert actual_intent == expected["intent_classified"], (
            f"{file_id}: intent_classified mismatch — got {actual_intent!r}"
        )

    if expected.get("min_confidence") is not None:
        conf = float(result["result"].get("confidence", 0.0))
        lo = float(expected["min_confidence"])
        hi = float(expected.get("max_confidence", 1.0))
        assert lo <= conf <= hi, (
            f"{file_id}: confidence {conf} out of range [{lo}, {hi}]"
        )

    if expected.get("max_iterations") is not None:
        iters = int(result["result"].get("iterations", 0))
        assert iters <= int(expected["max_iterations"]), (
            f"{file_id}: iterations {iters} exceeds max {expected['max_iterations']}"
        )

    if expected.get("final_state"):
        # FSM state — always "IDLE" post-decide() (paused or completed both end IDLE).
        assert result["final_state"] == expected["final_state"], (
            f"{file_id}: final_state mismatch — got {result['final_state']!r}, "
            f"expected {expected['final_state']!r}"
        )

    if expected.get("tools_invoked"):
        # Match tool names against accumulated tool_calls (substring tolerant).
        accumulated = result["result"].get("accumulated", []) or []
        actual_tools = [
            f"{s['tool_call'].get('server','')}.{s['tool_call'].get('tool','')}"
            for s in accumulated if isinstance(s, dict) and s.get("tool_call")
        ]
        for expected_tool in expected["tools_invoked"]:
            assert any(expected_tool in t for t in actual_tools), (
                f"{file_id}: expected tool {expected_tool!r} not found in {actual_tools}"
            )


def test_golden_cases_count_exactly_12() -> None:
    """D2 cristalizado: exatamente 12 cases (2 per intent × 6 intents)."""
    assert len(CASES) == 12, (
        f"Expected 12 golden cases (D2 cristalizado: 2 per intent × 6 intents), "
        f"found {len(CASES)}: {[c['_file'] for c in CASES]}"
    )


def test_destructive_intents_always_require_confirm() -> None:
    """G13 — send_outreach cases (destructive intent) → requires_confirm: true 100%."""
    destructive_cases = [c for c in CASES if c["intent"] == "send_outreach"]
    assert len(destructive_cases) >= 2, (
        f"Expected >=2 send_outreach cases, found {len(destructive_cases)}"
    )
    for case in destructive_cases:
        assert case["expected"]["requires_confirm"] is True, (
            f"{case['_file']}: destructive intent send_outreach MUST set "
            f"expected.requires_confirm=true (safety contract)"
        )
