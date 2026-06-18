"""F.6.2 ReAct loop multi-step canonical Anthropic Think→Act→Observe.

D3 ReAct loop: each iteration LLM reasons + chooses next tool, dispatches via gateway,
observes result, repeats until final_answer OR max_iterations OR no planned_tool.

D4 sequential tool execution (NÃO asyncio.gather F.6.2 — paralelo F.future se F.8
observability mostra benefit). D6 max iter 5 hardcoded.

D5 confidence híbrido: final_conf = 0.6 * llm_self + 0.4 * brain_validation
brain_validation = successful_tool_calls / total_tool_calls

D7 timeout 30s per dispatch (delegado routing matrix max_latency_ms).

Cross-ref:
  .claude/PLAN.md § F.6.2 Decisões D3-D7 (commit 68f0623)
  brain/dispatch.py F.6.2 (Gateway HTTP client)
  brain/intents.py F.6.2 INTENT_REGISTRY (task_type + default_tools)
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from .dispatch import GatewayDispatcher

__all__ = ["react_loop", "MAX_REACT_ITERATIONS", "CONFIDENCE_MAX_ITER_PENALTY"]

log = logging.getLogger("brain.react")

MAX_REACT_ITERATIONS = 5  # D6 cristalizado
CONFIDENCE_MAX_ITER_PENALTY = 0.2  # D6 cristalizado

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_json_fences(text: str) -> str:
    """LLMs often wrap JSON in ```json ... ``` fences — strip pra parse."""
    return _FENCE_RE.sub("", text).strip()


def _extract_llm_text(dispatch_result: dict[str, Any]) -> str:
    """Gateway response shape: {ok, response: {ok, response: "<text>"}}.

    Returns innermost text OR empty string if route failed.
    """
    if not dispatch_result.get("ok"):
        return ""
    inner = dispatch_result.get("response", {})
    if isinstance(inner, dict):
        if not inner.get("ok"):
            return ""
        return str(inner.get("response", "") or "")
    return str(inner or "")


def _parse_llm_json(text: str) -> dict[str, Any]:
    """Parse LLM response as JSON. Defensive: strip fences, return fallback shape on error."""
    if not text:
        return {"rationale": "empty_llm_response", "planned_tool": None, "final_answer": None, "confidence": 0.3}
    cleaned = _strip_json_fences(text)
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    # Fallback: LLM didn't emit JSON → treat full text as final_answer
    return {
        "rationale": "llm_response_not_json",
        "planned_tool": None,
        "final_answer": text[:2000],
        "confidence": 0.4,
    }


def _build_react_prompt(intent: str, intent_config: dict[str, Any], context: dict[str, Any], accumulated: list[dict[str, Any]]) -> str:
    """Build ReAct prompt: intent + context + tools available + accumulated history."""
    tools = intent_config.get("default_tools", []) or []
    description = intent_config.get("description", "")

    lines = [
        f"You are Hermes Brain orchestrator. Execute intent: {intent}",
        f"Description: {description}",
        f"Available tools: {tools if tools else '[none — return final_answer directly]'}",
        f"Context: {json.dumps(context, default=str)[:1500]}",
        "",
    ]

    if accumulated:
        lines.append("Previous iterations:")
        for step in accumulated:
            lines.append(f"  Iter {step['iteration']}:")
            lines.append(f"    Thought: {step['thought'][:300]}")
            tc = step["tool_call"]
            lines.append(f"    Tool: {tc.get('server')}.{tc.get('tool')} args={json.dumps(tc.get('args',{}), default=str)[:200]}")
            tr = step["tool_result"]
            result_summary = json.dumps(tr, default=str)[:500] if isinstance(tr, dict) else str(tr)[:500]
            lines.append(f"    Result: {result_summary}")
        lines.append("")

    lines.append("Output STRICT JSON (no markdown fences):")
    lines.append('{"rationale": "...", "planned_tool": {"server": "...", "tool": "...", "args": {}} OR null, "final_answer": "..." OR null, "confidence": 0.0-1.0}')
    lines.append("")
    lines.append("Rules:")
    lines.append("- If you have a final answer, set planned_tool=null and provide final_answer text.")
    lines.append("- If you need to call a tool, set planned_tool with server+tool+args from Available tools list.")
    lines.append("- confidence reflects YOUR self-assessment (0.0 unsure → 1.0 certain).")

    return "\n".join(lines)


def _compute_confidence(accumulated: list[dict[str, Any]], llm_self: float) -> float:
    """D5 híbrido 0.6 LLM + 0.4 Brain validation (tool success rate)."""
    llm_self = max(0.0, min(1.0, float(llm_self)))
    if not accumulated:
        return round(llm_self, 3)
    successful = sum(1 for r in accumulated if isinstance(r.get("tool_result"), dict) and r["tool_result"].get("ok"))
    brain_validation = successful / len(accumulated)
    return round(0.6 * llm_self + 0.4 * brain_validation, 3)


def _aggregate_tool_costs(accumulated: list[dict[str, Any]]) -> float:
    """Sum cost_credits across tool_result inner.cost_credits (gateway response shape)."""
    total = 0.0
    for r in accumulated:
        tr = r.get("tool_result", {})
        if not isinstance(tr, dict):
            continue
        inner = tr.get("response", {})
        if isinstance(inner, dict):
            cost = inner.get("cost_credits")
            if isinstance(cost, (int, float)):
                total += float(cost)
    return total


def _extract_llm_call_cost(dispatch_result: dict[str, Any]) -> float:
    """Extract cost_credits from a single hermes-llm.route dispatch result."""
    if not isinstance(dispatch_result, dict):
        return 0.0
    inner = dispatch_result.get("response", {})
    if not isinstance(inner, dict):
        return 0.0
    cost = inner.get("cost_credits")
    return float(cost) if isinstance(cost, (int, float)) else 0.0


async def react_loop(
    intent: str,
    context: dict[str, Any],
    intent_config: dict[str, Any],
    dispatcher: GatewayDispatcher | None = None,
) -> dict[str, Any]:
    """Main ReAct loop. Returns final result dict.

    Args:
        intent: intent name (informational only — caller must pre-validate via INTENT_REGISTRY).
        context: arbitrary context passed to LLM prompt.
        intent_config: INTENT_REGISTRY[intent] dict (task_type, default_tools, destructive).
        dispatcher: optional GatewayDispatcher (default new instance).

    Returns:
        {
          ok: bool,                    # final_answer reached OR max_iter graceful
          iterations: int,
          final_answer: str | None,
          confidence: float,
          intent: str,
          task_type: str | None,
          tools_used: list[dict],
          accumulated: list[dict],     # full ReAct trace
          cost_credits: float,
          status: 'completed' | 'max_iterations_reached' | 'llm_dispatch_failed' | 'utility_no_llm'
        }
    """
    dispatcher = dispatcher or GatewayDispatcher()
    task_type = intent_config.get("task_type")

    # Utility intents (task_type=None like route_skill_run) — no LLM call.
    if task_type is None:
        return {
            "ok": True,
            "iterations": 0,
            "final_answer": None,
            "confidence": 1.0,
            "intent": intent,
            "task_type": None,
            "tools_used": [],
            "accumulated": [],
            "cost_credits": 0.0,
            "status": "utility_no_llm",
        }

    accumulated: list[dict[str, Any]] = []
    llm_calls_cost = 0.0  # F.6.2 LLM call cost tracking (separate from tool_result inner cost)
    iteration = 0

    while iteration < MAX_REACT_ITERATIONS:
        iteration += 1

        # THINK: LLM reasoning call
        prompt = _build_react_prompt(intent, intent_config, context, accumulated)
        llm_dispatch = await dispatcher.route(task_type=str(task_type), prompt=prompt)
        llm_calls_cost += _extract_llm_call_cost(llm_dispatch)

        if not llm_dispatch.get("ok"):
            log.warning("ReAct iter %d intent=%s LLM dispatch HTTP fail: %s", iteration, intent, llm_dispatch.get("error"))
            return {
                "ok": False,
                "iterations": iteration,
                "final_answer": None,
                "confidence": 0.0,
                "intent": intent,
                "task_type": task_type,
                "tools_used": [r["tool_call"] for r in accumulated],
                "accumulated": accumulated,
                "cost_credits": round(llm_calls_cost + _aggregate_tool_costs(accumulated), 4),
                "status": "llm_dispatch_failed",
                "error": str(llm_dispatch.get("error", "unknown"))[:300],
            }

        # Inner route ok=false (all tiers exhausted) — also treat as dispatch failed
        inner_route = llm_dispatch.get("response", {})
        if isinstance(inner_route, dict) and not inner_route.get("ok"):
            log.warning("ReAct iter %d intent=%s route all_tiers_failed: %s", iteration, intent, inner_route.get("error"))
            return {
                "ok": False,
                "iterations": iteration,
                "final_answer": None,
                "confidence": 0.0,
                "intent": intent,
                "task_type": task_type,
                "tools_used": [r["tool_call"] for r in accumulated],
                "accumulated": accumulated,
                "cost_credits": round(llm_calls_cost + _aggregate_tool_costs(accumulated), 4),
                "status": "llm_dispatch_failed",
                "error": str(inner_route.get("error", "all_tiers_failed"))[:300],
            }

        llm_text = _extract_llm_text(llm_dispatch)
        parsed = _parse_llm_json(llm_text)

        rationale = str(parsed.get("rationale", ""))[:1000]
        planned_tool = parsed.get("planned_tool")
        final_answer = parsed.get("final_answer")
        llm_self_conf = float(parsed.get("confidence", 0.5) or 0.5)

        # Terminal: final answer reached OR no more tools planned
        if final_answer is not None or not planned_tool:
            return {
                "ok": True,
                "iterations": iteration,
                "final_answer": str(final_answer)[:4000] if final_answer is not None else rationale,
                "confidence": _compute_confidence(accumulated, llm_self_conf),
                "intent": intent,
                "task_type": task_type,
                "tools_used": [r["tool_call"] for r in accumulated],
                "accumulated": accumulated,
                "cost_credits": round(llm_calls_cost + _aggregate_tool_costs(accumulated), 4),
                "status": "completed",
            }

        # ACT: dispatch planned tool (D4 sequential — NÃO asyncio.gather)
        if not isinstance(planned_tool, dict):
            log.warning("ReAct iter %d intent=%s planned_tool invalid type=%s", iteration, intent, type(planned_tool).__name__)
            return {
                "ok": False,
                "iterations": iteration,
                "final_answer": rationale,
                "confidence": _compute_confidence(accumulated, llm_self_conf) - 0.1,
                "intent": intent,
                "task_type": task_type,
                "tools_used": [r["tool_call"] for r in accumulated],
                "accumulated": accumulated,
                "cost_credits": round(llm_calls_cost + _aggregate_tool_costs(accumulated), 4),
                "status": "completed",
                "note": "invalid_planned_tool_type",
            }

        server = str(planned_tool.get("server", ""))
        tool = str(planned_tool.get("tool", ""))
        args = planned_tool.get("args", {}) or {}
        if not server or not tool:
            log.warning("ReAct iter %d intent=%s planned_tool missing server/tool", iteration, intent)
            return {
                "ok": True,
                "iterations": iteration,
                "final_answer": rationale or "missing server/tool in planned_tool",
                "confidence": _compute_confidence(accumulated, llm_self_conf) - 0.1,
                "intent": intent,
                "task_type": task_type,
                "tools_used": [r["tool_call"] for r in accumulated],
                "accumulated": accumulated,
                "cost_credits": round(llm_calls_cost + _aggregate_tool_costs(accumulated), 4),
                "status": "completed",
                "note": "invalid_planned_tool_schema",
            }

        tool_result = await dispatcher.invoke_tool(server=server, tool=tool, args=args if isinstance(args, dict) else {})

        # OBSERVE: accumulate (NÃO asyncio.gather — sequential per D4)
        accumulated.append({
            "iteration": iteration,
            "thought": rationale,
            "tool_call": {"server": server, "tool": tool, "args": args},
            "tool_result": tool_result,
        })

    # Max iterations reached (D6 penalty 0.2)
    base_conf = _compute_confidence(accumulated, 0.5)
    return {
        "ok": False,
        "iterations": iteration,
        "final_answer": None,
        "confidence": max(0.0, round(base_conf - CONFIDENCE_MAX_ITER_PENALTY, 3)),
        "intent": intent,
        "task_type": task_type,
        "tools_used": [r["tool_call"] for r in accumulated],
        "accumulated": accumulated,
        "cost_credits": round(llm_calls_cost + _aggregate_tool_costs(accumulated), 4),
        "status": "max_iterations_reached",
    }


async def react_loop_streaming(
    intent: str,
    context: dict[str, Any],
    intent_config: dict[str, Any],
    dispatcher: GatewayDispatcher | None = None,
):
    """Async generator — yields SSE event dicts during ReAct execution.

    UX-RM-F5-A: powers /api/brain/stream-decide SSE endpoint.
    Mirrors react_loop() logic, emitting events at each observable step.

    Yields dicts with type: thought | tool_call | tool_result | final | error.
    """
    dispatcher = dispatcher or GatewayDispatcher()
    task_type = intent_config.get("task_type")

    if task_type is None:
        yield {"type": "final", "answer": None, "confidence": 1.0, "iterations": 0, "status": "utility_no_llm"}
        return

    accumulated: list[dict[str, Any]] = []
    llm_calls_cost = 0.0
    iteration = 0

    while iteration < MAX_REACT_ITERATIONS:
        iteration += 1

        prompt = _build_react_prompt(intent, intent_config, context, accumulated)
        llm_dispatch = await dispatcher.route(task_type=str(task_type), prompt=prompt)
        llm_calls_cost += _extract_llm_call_cost(llm_dispatch)

        if not llm_dispatch.get("ok"):
            err = str(llm_dispatch.get("error", "unknown"))[:200]
            log.warning("react_stream iter %d intent=%s LLM fail: %s", iteration, intent, err)
            yield {"type": "error", "message": f"LLM dispatch falhou: {err}"}
            return

        inner_route = llm_dispatch.get("response", {})
        if isinstance(inner_route, dict) and not inner_route.get("ok"):
            err = str(inner_route.get("error", "all_tiers_failed"))[:200]
            log.warning("react_stream iter %d intent=%s all tiers failed: %s", iteration, intent, err)
            yield {"type": "error", "message": f"Todos os modelos falharam: {err}"}
            return

        llm_text = _extract_llm_text(llm_dispatch)
        parsed = _parse_llm_json(llm_text)

        rationale = str(parsed.get("rationale", ""))[:1000]
        planned_tool = parsed.get("planned_tool")
        final_answer = parsed.get("final_answer")
        llm_self_conf = float(parsed.get("confidence", 0.5) or 0.5)

        if rationale:
            yield {"type": "thought", "chunk": rationale, "iteration": iteration}

        if final_answer is not None or not planned_tool:
            conf = _compute_confidence(accumulated, llm_self_conf)
            cost = round(llm_calls_cost + _aggregate_tool_costs(accumulated), 4)
            yield {
                "type": "final",
                "answer": str(final_answer)[:4000] if final_answer is not None else rationale,
                "confidence": conf,
                "iterations": iteration,
                "cost_credits": cost,
                "status": "completed",
            }
            return

        if not isinstance(planned_tool, dict):
            log.warning("react_stream iter %d intent=%s invalid planned_tool type", iteration, intent)
            yield {"type": "error", "message": "Tipo de ferramenta inválido na resposta do modelo"}
            return

        server = str(planned_tool.get("server", ""))
        tool = str(planned_tool.get("tool", ""))
        args = planned_tool.get("args", {}) or {}

        if not server or not tool:
            conf = _compute_confidence(accumulated, llm_self_conf)
            cost = round(llm_calls_cost + _aggregate_tool_costs(accumulated), 4)
            yield {
                "type": "final",
                "answer": rationale or "ferramenta planejada sem server/tool",
                "confidence": conf,
                "iterations": iteration,
                "cost_credits": cost,
                "status": "completed",
            }
            return

        yield {"type": "tool_call", "tool": f"{server}.{tool}", "args": args if isinstance(args, dict) else {}, "iteration": iteration}

        tool_result = await dispatcher.invoke_tool(
            server=server, tool=tool, args=args if isinstance(args, dict) else {}
        )
        tool_ok = bool(isinstance(tool_result, dict) and tool_result.get("ok"))
        yield {
            "type": "tool_result",
            "result": tool_result if isinstance(tool_result, dict) else {"raw": str(tool_result)[:500]},
            "ok": tool_ok,
        }

        accumulated.append({
            "iteration": iteration,
            "thought": rationale,
            "tool_call": {"server": server, "tool": tool, "args": args},
            "tool_result": tool_result,
        })

    base_conf = _compute_confidence(accumulated, 0.5)
    cost = round(llm_calls_cost + _aggregate_tool_costs(accumulated), 4)
    yield {
        "type": "final",
        "answer": None,
        "confidence": max(0.0, round(base_conf - CONFIDENCE_MAX_ITER_PENALTY, 3)),
        "iterations": iteration,
        "cost_credits": cost,
        "status": "max_iterations_reached",
    }
