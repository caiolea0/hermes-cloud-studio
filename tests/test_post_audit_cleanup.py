"""R11+R12+R13 post-audit cleanup verification tests."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent


# ── R11 ─────────────────────────────────────────────────────────────────────

def test_events_jsonl_path_deprecated_documented():
    """R11: events_jsonl_path migration block must carry deprecation comment."""
    state_py = (ROOT / "core" / "state.py").read_text(encoding="utf-8")
    assert "R11: DEPRECATED" in state_py, (
        "core/state.py missing R11 deprecation comment for events_jsonl_path"
    )
    assert "ARTIFACTS_BASE" in state_py or "events.jsonl" in state_py, (
        "Deprecation comment must reference runtime computation of events.jsonl path"
    )


# ── R12 ─────────────────────────────────────────────────────────────────────

def test_cobaia_autotune_synthesis_wired_in_decide():
    """R12: brain/decide.py must wire cobaia_autotune_synthesis (no cobaia_intent_not_wired)."""
    decide_py = (ROOT / "brain" / "decide.py").read_text(encoding="utf-8")
    assert "cobaia_autotune_synthesis" in decide_py, (
        "brain/decide.py missing elif branch for cobaia_autotune_synthesis"
    )
    # Ensure not using the fallback error path for this intent
    assert "_handle_cobaia_autotune_synthesis_intent" in decide_py, (
        "brain/decide.py must delegate to _handle_cobaia_autotune_synthesis_intent"
    )


def test_cobaia_autotune_synthesis_handler_in_intents():
    """R12: brain/intents.py must define _handle_cobaia_autotune_synthesis_intent."""
    intents_py = (ROOT / "brain" / "intents.py").read_text(encoding="utf-8")
    assert "def _handle_cobaia_autotune_synthesis_intent" in intents_py, (
        "brain/intents.py missing _handle_cobaia_autotune_synthesis_intent function"
    )
    assert "detect_and_trigger" in intents_py, (
        "_handle_cobaia_autotune_synthesis_intent must delegate to detect_and_trigger"
    )


def test_cobaia_autotune_synthesis_handler_returns_ok():
    """R12: _handle_cobaia_autotune_synthesis_intent returns ok=True for no-breach case."""
    from brain.intents import _handle_cobaia_autotune_synthesis_intent

    # no-breach path: detect_and_trigger returns triggered=0, no DB needed if mocked
    # Use a non-existent account to get no-breach result (empty DB → no metrics)
    result = _handle_cobaia_autotune_synthesis_intent(
        {"account_handle": "__r12_test_nonexistent__", "sustained_hours": 24}
    )
    assert result["ok"] is True, f"Expected ok=True, got: {result}"
    assert result["intent"] == "cobaia_autotune_synthesis"
    assert result["status"] == "completed"
    assert "final_answer" in result
    assert result["final_answer"].get("triggered", 0) == 0  # no breach in test DB


# ── R13 ─────────────────────────────────────────────────────────────────────

def test_plan_md_closeout_evidence_updated():
    """R13: PLAN.md F.4.4 C2 closeout must reference verified 2026-06-18 evidence."""
    plan_md = (ROOT / ".claude" / "PLAN.md").read_text(encoding="utf-8")
    assert "Verified 2026-06-18" in plan_md, (
        ".claude/PLAN.md must contain 'Verified 2026-06-18' systemctl evidence"
    )
    assert "hermes-skill-quarantine.timer" in plan_md, (
        "Timer name must appear in PLAN.md evidence"
    )
    # Ensure old false claim phrase is gone
    assert "VM timer active next 04:00 UTC" not in plan_md, (
        "Old false claim 'VM timer active next 04:00 UTC' must be replaced"
    )
