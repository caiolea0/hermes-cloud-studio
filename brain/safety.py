"""F.6 Brain safety gates (D8 cristalizado).

HYBRID approach — owner confirm OBRIGATÓRIO se:
  (a) action_class IN DESTRUCTIVE_ACTIONS, OR
  (b) intent IN DESTRUCTIVE_ACTIONS (some intents always destructive), OR
  (c) confidence < CONFIDENCE_THRESHOLD (default 0.5).

DESTRUCTIVE_ACTIONS is frozenset (immutable — security: prevent runtime mutation).

F.future: CONFIDENCE_THRESHOLD configurable via PrefPanel + DB pref_keys.
F.6.1 hardcoded 0.5 (D8).
"""
from __future__ import annotations

# Frozenset (NOT list) — security: caller cannot mutate at runtime.
DESTRUCTIVE_ACTIONS: frozenset[str] = frozenset({
    "send_outreach",
    "send_message",
    "send_inmail",
    "synth_skill_promote",
    "deploy_skill_pr",
})

CONFIDENCE_THRESHOLD: float = 0.5


def requires_owner_confirm(
    intent: str,
    confidence: float,
    action_class: str = "",
) -> tuple[bool, str]:
    """Decide if Brain.decide() must pause for owner confirmation.

    Returns (requires_confirm, reason).
    reason is empty string when no confirm needed.
    """
    if action_class in DESTRUCTIVE_ACTIONS:
        return True, f"destructive_action:{action_class}"
    if intent in DESTRUCTIVE_ACTIONS:
        return True, f"destructive_intent:{intent}"
    if confidence < CONFIDENCE_THRESHOLD:
        return True, f"low_confidence:{confidence:.2f}<{CONFIDENCE_THRESHOLD}"
    return False, ""
