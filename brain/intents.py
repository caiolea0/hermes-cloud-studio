"""F.6 Brain intent registry (D3 cristalizado).

6 intents core (5 essenciais + 1 utility):
  1. answer_owner          — chat dashboard owner-facing
  2. send_outreach         — F.7 cobaia LinkedIn outreach (DESTRUCTIVE)
  3. synth_skill           — F.4 auto-skill generation
  4. classify_prospect     — F.7 ICP scoring
  5. summarize_conversation — chat memory long-context summarization
  6. route_skill_run       — utility: low-latency executor (no LLM call)

Expand F.future: analyze_competitor, generate_report, triage_inbox.

F.6.1: handle_intent() returns mock data deterministic — NO real LLM call.
F.6.2: implements real dispatch via mcp.hermes-llm.route() + tool calling.
"""
from __future__ import annotations

from typing import Any

# Intent registry — 6 entries exact (D3 — NOT 5, NOT 7+).
# `task_type` matches NVIDIA-MODELS-ROUTING-MATRIX.md §4 ground truth.
# `destructive` mirrors safety.DESTRUCTIVE_ACTIONS (D8).
# `default_tools` lists MCP tool names that F.6.2 will dispatch via gateway.
INTENT_REGISTRY: dict[str, dict[str, Any]] = {
    "answer_owner": {
        "description": "Chat dashboard owner-facing — responde pergunta direta",
        "task_type": "reasoning",
        "destructive": False,
        "default_tools": [],  # F.6.2 may add mcp.postgres.query for data lookups
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
    },
    "synth_skill": {
        "description": "F.4 auto-skill generation",
        "task_type": "code_gen",
        "destructive": False,  # synth NOT destructive; promote_skill is.
        "default_tools": [
            "mcp.hermes-llm.route",
            "mcp.hermes-skills.propose_skill_yaml_stub",
        ],
    },
    "classify_prospect": {
        "description": "F.7 ICP scoring",
        "task_type": "classify",
        "destructive": False,
        "default_tools": [
            "mcp.hermes-llm.route",
            "mcp.hermes-prospects.score_lead",
        ],
    },
    "summarize_conversation": {
        "description": "F.6 chat memory long-context summarization",
        "task_type": "summarize",
        "destructive": False,
        "default_tools": ["mcp.hermes-llm.route"],
    },
    "route_skill_run": {
        "description": "Utility: pure-Python executor sem LLM, gateway dispatch direto (low-latency)",
        "task_type": None,  # NÃO chama LLM
        "destructive": False,
        "default_tools": [],
    },
}


async def handle_intent(intent: str, context: dict[str, Any]) -> dict[str, Any]:
    """F.6.1 STUB — returns mock data deterministic per intent.

    F.6.2 implements:
      - real LLM call via mcp.hermes-llm.route(prompt, task_type=cfg['task_type'])
      - tool dispatch via gateway for each tool in cfg['default_tools']
      - confidence derived from model log-probs / heuristic
    """
    if intent not in INTENT_REGISTRY:
        return {"ok": False, "error": f"unknown_intent:{intent}"}

    config = INTENT_REGISTRY[intent]
    return {
        "ok": True,
        "intent": intent,
        "mock_response": f"[F.6.1 STUB] {config['description']} — context_keys={sorted(context.keys())}",
        "confidence": 0.85,
        "task_type": config["task_type"],
        "destructive": config["destructive"],
        "tools_used": [],  # F.6.2 populates as dispatch happens
        "tools_available": list(config["default_tools"]),
    }
