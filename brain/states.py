"""F.6 Brain state machine (D2 cristalizado).

6 states canonical Anthropic Think→Act→Observe:
  IDLE → CLASSIFY → REASON → ACT → REVIEW → COMMIT → IDLE

Uses `transitions` lib (lightweight FSM, ~3KB import) — picked over LangGraph
(heavy deps, owner solo no-code preference per D1).
"""
from __future__ import annotations

from enum import Enum

from transitions import Machine


class BrainState(str, Enum):
    """6 canonical Brain states (D2)."""

    IDLE = "IDLE"
    CLASSIFY = "CLASSIFY"
    REASON = "REASON"
    ACT = "ACT"
    REVIEW = "REVIEW"
    COMMIT = "COMMIT"


# Transitions FSM definition — state names MUST match BrainState enum exactly (case-sensitive).
_STATE_NAMES = tuple(s.value for s in BrainState)

_TRANSITIONS = (
    {"trigger": "start_classify", "source": BrainState.IDLE.value, "dest": BrainState.CLASSIFY.value},
    {"trigger": "to_reason", "source": BrainState.CLASSIFY.value, "dest": BrainState.REASON.value},
    {"trigger": "to_act", "source": BrainState.REASON.value, "dest": BrainState.ACT.value},
    {"trigger": "to_review", "source": BrainState.ACT.value, "dest": BrainState.REVIEW.value},
    # Owner confirm required (D5/D8) — pause back to IDLE waiting confirm endpoint
    {"trigger": "owner_confirm_required", "source": BrainState.REVIEW.value, "dest": BrainState.IDLE.value},
    {"trigger": "to_commit", "source": BrainState.REVIEW.value, "dest": BrainState.COMMIT.value},
    {"trigger": "complete", "source": BrainState.COMMIT.value, "dest": BrainState.IDLE.value},
    # Abort from any state on error/timeout
    {"trigger": "abort", "source": "*", "dest": BrainState.IDLE.value},
)


class BrainStateMachine:
    """Brain FSM wrapper. Each Brain() instance owns one machine (thread-independent)."""

    def __init__(self) -> None:
        self.machine = Machine(
            model=self,
            states=list(_STATE_NAMES),
            transitions=list(_TRANSITIONS),
            initial=BrainState.IDLE.value,
            auto_transitions=False,  # only explicit triggers allowed (deterministic)
            ignore_invalid_triggers=False,  # raise on invalid path (catches bugs F.6.1 smoke)
        )

    @property
    def current_state(self) -> str:
        return self.state  # type: ignore[attr-defined]
