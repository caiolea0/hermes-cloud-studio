"""F.6 Brain orchestrator package.

F.6.1: scaffold (this commit) — state machine + 6 intents stubs deterministic.
F.6.2: tool calling real via gateway dispatch.
F.6.3: memory persistence brain_runs + brain_decisions.
F.6.4: safety gates + owner confirm UX.
F.6.5: golden cases test suite + hermes-brain-test skill.
F.6.6: closeout.

Public API:
  from brain.decide import Brain
  brain = Brain()
  result = await brain.decide(intent="answer_owner", context={...})
"""
from .decide import Brain
from .intents import INTENT_REGISTRY
from .states import BrainState

__all__ = ["Brain", "INTENT_REGISTRY", "BrainState"]
