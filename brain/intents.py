"""F.6 Brain intent registry (D3 cristalizado).

6 intents core (5 essenciais + 1 utility):
  1. answer_owner          — chat dashboard owner-facing
  2. send_outreach         — F.7 cobaia LinkedIn outreach (DESTRUCTIVE)
  3. synth_skill           — F.4 auto-skill generation
  4. classify_prospect     — F.7 ICP scoring
  5. summarize_conversation — chat memory long-context summarization
  6. route_skill_run       — utility: low-latency executor (no LLM call)

Expand F.future: analyze_competitor, generate_report, triage_inbox.

F.6.1: handle_intent() returned mock data deterministic — NO real LLM call.
F.6.2: handle_intent() delegates to brain._react.react_loop (real dispatch via gateway).
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .dispatch import GatewayDispatcher

# Intent registry — 6 entries exact (D3 — NOT 5, NOT 7+).
# `task_type` matches NVIDIA-MODELS-ROUTING-MATRIX.md §4 ground truth.
# `destructive` mirrors safety.DESTRUCTIVE_ACTIONS (D8).
# `default_tools` lists MCP tool names that F.6.2 will dispatch via gateway.
# `agentmemory_save` F.6.3 D4 opt-in cross-session long-term learning (default false).
INTENT_REGISTRY: dict[str, dict[str, Any]] = {
    "answer_owner": {
        "description": "Chat dashboard owner-facing — responde pergunta direta",
        "task_type": "reasoning",
        "destructive": False,
        "default_tools": [],  # F.6.2 may add mcp.postgres.query for data lookups
        "agentmemory_save": True,  # F.6.3 D4: cross-session owner context
    },
    "send_outreach": {
        "description": "F.7 cobaia LinkedIn outreach gen + dispatch",
        "task_type": "creative_ptbr",
        "destructive": True,  # ALWAYS owner confirm (D8)
        "default_tools": [
            "mcp.hermes-llm.route",
            "mcp.hermes-prospects.search_prospects",
            "mcp.hermes-linkedin.send_invite",
        ],
        "agentmemory_save": False,  # F.6.3 D4: high volume, mcp_calls already logs
    },
    "synth_skill": {
        "description": "F.4 auto-skill generation",
        "task_type": "code_gen",
        "destructive": False,  # synth NOT destructive; promote_skill is.
        "default_tools": [
            "mcp.hermes-llm.route",
            "mcp.hermes-skills.propose_skill_yaml_stub",
        ],
        "agentmemory_save": True,  # F.6.3 D4: skill evolution history
    },
    "classify_prospect": {
        "description": "F.7 ICP scoring",
        "task_type": "classify",
        "destructive": False,
        "default_tools": [
            "mcp.hermes-llm.route",
            "mcp.hermes-prospects.score_lead",
        ],
        "agentmemory_save": True,  # F.6.3 D4: ICP scoring rationale refinement
    },
    "summarize_conversation": {
        "description": "F.6 chat memory long-context summarization",
        "task_type": "summarize",
        "destructive": False,
        "default_tools": ["mcp.hermes-llm.route"],
        "agentmemory_save": False,  # F.6.3 D4: transient summaries
    },
    "route_skill_run": {
        "description": "Utility: pure-Python executor sem LLM, gateway dispatch direto (low-latency)",
        "task_type": None,  # NÃO chama LLM
        "destructive": False,
        "default_tools": [],
        "agentmemory_save": False,  # F.6.3 D4: utility no LLM, no observation worth
    },
}


async def handle_intent(
    intent: str,
    context: dict[str, Any],
    dispatcher: "GatewayDispatcher | None" = None,
) -> dict[str, Any]:
    """F.6.2 REAL — delegates to brain._react.react_loop (gateway dispatch + ReAct).

    For intents with task_type=None (utility like route_skill_run), react_loop
    short-circuits sem LLM call (returns status='utility_no_llm').

    Returns enriched intent_result shape compatible with Brain.decide() consumer:
      {ok, intent, task_type, destructive, tools_available, confidence,
       tools_used, final_answer, iterations, accumulated, cost_credits, status, ...}
    """
    if intent not in INTENT_REGISTRY:
        return {"ok": False, "error": f"unknown_intent:{intent}"}

    config = INTENT_REGISTRY[intent]

    # Lazy import (avoid circular brain.intents <-> brain._react if either grows).
    from ._react import react_loop

    react_result = await react_loop(
        intent=intent,
        context=context,
        intent_config=config,
        dispatcher=dispatcher,
    )

    # Merge static intent metadata + dynamic ReAct result.
    return {
        "ok": bool(react_result.get("ok")),
        "intent": intent,
        "task_type": config["task_type"],
        "destructive": config["destructive"],
        "tools_available": list(config["default_tools"]),
        "tools_used": react_result.get("tools_used", []),
        "final_answer": react_result.get("final_answer"),
        "confidence": react_result.get("confidence", 0.5),
        "iterations": react_result.get("iterations", 0),
        "accumulated": react_result.get("accumulated", []),
        "cost_credits": react_result.get("cost_credits", 0.0),
        "status": react_result.get("status", "completed"),
        "error": react_result.get("error"),
        "note": react_result.get("note"),
    }
