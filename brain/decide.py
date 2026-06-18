"""F.6 Brain orchestrator entry point — Brain.decide() main loop.

F.6.1: scaffold + state machine + 6 intents STUBS (deterministic mock).
F.6.2: tool calling REAL via mcp.hermes-llm.route + gateway dispatch + ReAct loop.
F.6.3: memory persistence brain_runs + brain_decisions + agentmemory MCP opt-in.
F.6.4: safety gates UX dashboard modal + endpoint POST /api/brain/confirm.
F.6.5: golden cases test suite + hermes-brain-test skill battery.
F.6.6: closeout + Task #6 [completed].

Cross-ref:
  .claude/PLAN.md § F.6 Decisões D1-D10 + F.6.2 D1-D8 + F.6.3 D1-D6
  brain/persistence.py F.6.3 (async DB layer + writer queue)
  brain/_react.py F.6.2 (ReAct loop multi-step)
  brain/dispatch.py F.6.2 (Gateway HTTP client)
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from .dispatch import GatewayDispatcher
from .intents import INTENT_REGISTRY, handle_intent
from .persistence import BrainPersistence, get_persistence
from .safety import requires_owner_confirm
from .states import BrainStateMachine

__all__ = ["Brain"]

log = logging.getLogger("brain.decide")


class Brain:
    """Brain orchestrator. Each instance owns one state machine (thread-independent).

    F.6.3 persistence flow:
      1. Validate intent ∈ INTENT_REGISTRY → else error short-circuit (sem persist).
      2. SYNC INSERT brain_runs (run_id reservado imediato).
      3. FSM IDLE → CLASSIFY → REASON → ACT (3 decisions scheduled async).
      4. ACT: handle_intent → react_loop (gateway dispatch).
      5. Per ReAct iter: 1 decision scheduled (state ACT→ACT, tool_invoked + result).
      6. FSM ACT → REVIEW (safety gate decision).
      7a. If requires_confirm → FSM REVIEW → IDLE (paused). UPDATE brain_runs final.
      7b. Else → FSM REVIEW → COMMIT → IDLE. UPDATE brain_runs final.
      8. Opt-in: agentmemory MCP save async fire-and-forget se INTENT_REGISTRY[intent].agentmemory_save.

    F.6.3 NÃO chama linkedin/* direto — sempre via gateway dispatch (BLACKLIST R2).
    F.6.3 NÃO renderiza UI confirm modal (F.6.4 entrega).
    F.6.3 NÃO implementa golden cases (F.6.5 entrega).
    """

    def __init__(
        self,
        dispatcher: GatewayDispatcher | None = None,
        persistence: BrainPersistence | None = None,
    ) -> None:
        self.fsm = BrainStateMachine()
        self.dispatcher = dispatcher or GatewayDispatcher()
        self.persistence = persistence or get_persistence()

    async def decide(
        self,
        intent: str,
        context: dict[str, Any] | None = None,
        requester: str = "api",
    ) -> dict[str, Any]:
        """Main Brain.decide() loop. F.6.3 persistence integrated.

        Args:
            intent: one of INTENT_REGISTRY keys (else returns error).
            context: arbitrary dict passed to ReAct prompt builder.
            requester: 'owner_dashboard' | 'daemon' | 'api' | 'cron' (default 'api').

        Returns:
            {
              run_id: str,
              status: 'completed' | 'requires_confirm' | 'error',
              result: dict,
              requires_confirm: bool,
              latency_ms: int,
              total_cost_credits: float,
              final_state: str,
            }
        """
        ctx = context or {}
        run_id = str(uuid.uuid4())
        start = time.monotonic()

        # F.7 cobaia domain: fast-path, bypass F.6 FSM + INTENT_REGISTRY.
        if intent.startswith("cobaia_"):
            return await self._decide_cobaia(intent, ctx, run_id, start)

        # Defensive: unknown intent short-circuit (no FSM, no persistence).
        if intent not in INTENT_REGISTRY:
            return {
                "run_id": run_id,
                "status": "error",
                "result": {"error": f"unknown_intent:{intent}"},
                "requires_confirm": False,
                "latency_ms": int((time.monotonic() - start) * 1000),
                "total_cost_credits": 0.0,
                "final_state": self.fsm.current_state,
            }

        # SYNC INSERT brain_runs (run_id reservado). Persistence error NÃO aborta decide()
        # (best-effort — Sentry capture; flow continua) — owner ainda recebe resposta útil.
        persistence_ok = await self._persist_run_start(run_id, intent, ctx, requester)

        # FSM forward: IDLE → CLASSIFY → REASON → ACT (3 async decisions scheduled)
        seq = 0
        self.fsm.start_classify()  # type: ignore[attr-defined]
        seq += 1
        self._schedule_decision(
            persistence_ok, run_id, seq, "IDLE", "CLASSIFY",
            rationale=f"Brain.decide() invoked intent={intent} requester={requester}",
        )

        self.fsm.to_reason()  # type: ignore[attr-defined]
        seq += 1
        self._schedule_decision(
            persistence_ok, run_id, seq, "CLASSIFY", "REASON",
            rationale=f"intent classified, planning task_type={INTENT_REGISTRY[intent]['task_type']}",
        )

        self.fsm.to_act()  # type: ignore[attr-defined]
        seq += 1
        self._schedule_decision(
            persistence_ok, run_id, seq, "REASON", "ACT",
            rationale="dispatching ReAct loop via handle_intent",
        )

        # F.6.2 real dispatch: handle_intent → react_loop → gateway dispatch.
        intent_result = await handle_intent(intent, ctx, dispatcher=self.dispatcher)

        # F.6.3 D2: 1 decision row per ReAct iteration (tool_invoked + result).
        accumulated = intent_result.get("accumulated") or []
        for step in accumulated:
            seq += 1
            tc = step.get("tool_call") or {}
            tr = step.get("tool_result") or {}
            server = tc.get("server", "")
            tool = tc.get("tool", "")
            tool_invoked = f"mcp.{server}.{tool}" if server and tool else None
            # Latency from tool_result.duration_ms (gateway response shape)
            tr_latency = 0
            if isinstance(tr, dict):
                tr_latency = int(tr.get("duration_ms") or 0)
            self._schedule_decision(
                persistence_ok, run_id, seq, "ACT", "ACT",
                tool_invoked=tool_invoked,
                tool_args=tc.get("args") or {},
                tool_result=tr if isinstance(tr, dict) else {"raw": str(tr)[:500]},
                rationale=str(step.get("thought") or "")[:1000],
                latency_ms=tr_latency,
            )

        # FSM ACT → REVIEW (safety gate)
        self.fsm.to_review()  # type: ignore[attr-defined]
        seq += 1

        confidence = float(intent_result.get("confidence", 0.5))
        intent_destructive = bool(INTENT_REGISTRY[intent].get("destructive", False))
        action_class = intent if intent_destructive else ""
        needs_confirm, reason = requires_owner_confirm(intent, confidence, action_class)

        total_cost = float(intent_result.get("cost_credits", 0.0) or 0.0)
        latency_ms = int((time.monotonic() - start) * 1000)

        self._schedule_decision(
            persistence_ok, run_id, seq, "ACT", "REVIEW",
            rationale=f"safety gate: confidence={confidence:.2f} destructive={intent_destructive} "
                      f"needs_confirm={needs_confirm} reason={reason or 'none'}",
        )

        if needs_confirm:
            self.fsm.owner_confirm_required()  # type: ignore[attr-defined]
            seq += 1
            self._schedule_decision(
                persistence_ok, run_id, seq, "REVIEW", "IDLE",
                rationale=f"owner confirm REQUIRED — paused. reason={reason}",
            )
            final_result_payload = {
                **intent_result,
                "confirm_reason": reason,
                "action_class": action_class,
            }
            await self._persist_run_final(
                persistence_ok, run_id, "requires_confirm",
                final_result_payload, latency_ms, total_cost, confidence,
            )
            # agentmemory opt-in (paused runs also valuable for owner context retrieval)
            self._maybe_save_agentmemory(run_id, intent, ctx, final_result_payload, status="requires_confirm")
            return {
                "run_id": run_id,
                "status": "requires_confirm",
                "result": final_result_payload,
                "requires_confirm": True,
                "latency_ms": latency_ms,
                "total_cost_credits": total_cost,
                "final_state": self.fsm.current_state,
            }

        # FSM REVIEW → COMMIT → IDLE
        self.fsm.to_commit()  # type: ignore[attr-defined]
        seq += 1
        self._schedule_decision(
            persistence_ok, run_id, seq, "REVIEW", "COMMIT",
            rationale="safety gate passed, committing result",
        )

        self.fsm.complete()  # type: ignore[attr-defined]
        seq += 1
        self._schedule_decision(
            persistence_ok, run_id, seq, "COMMIT", "IDLE",
            rationale=f"Brain.decide() complete latency_ms={latency_ms} cost={total_cost:.4f}",
            latency_ms=latency_ms,
        )

        # status mapping (F.6.2 logic preserved)
        result_status = intent_result.get("status", "completed")
        if intent_result.get("ok") or result_status == "utility_no_llm":
            decide_status = "completed"
        else:
            decide_status = "error"

        await self._persist_run_final(
            persistence_ok, run_id, decide_status,
            intent_result, latency_ms, total_cost, confidence,
        )
        self._maybe_save_agentmemory(run_id, intent, ctx, intent_result, status=decide_status)

        return {
            "run_id": run_id,
            "status": decide_status,
            "result": intent_result,
            "requires_confirm": False,
            "latency_ms": latency_ms,
            "total_cost_credits": total_cost,
            "final_state": self.fsm.current_state,
        }

    # ----- F.7 cobaia domain fast-path (separate from F.6 FSM) -------------

    async def _decide_cobaia(
        self,
        intent: str,
        ctx: dict[str, Any],
        run_id: str,
        start: float,
    ) -> dict[str, Any]:
        """Route cobaia_* intents without F.6 FSM or INTENT_REGISTRY.

        Returns same shape as Brain.decide() for caller compatibility.
        Daemon reads result["result"]["final_answer"] for action_data.
        """
        from .cobaia_intent import COBAIA_INTENT_REGISTRY
        from .intents import (
            _handle_cobaia_warmup_intent,
            _handle_cobaia_autotune_synthesis_intent,
        )

        if intent not in COBAIA_INTENT_REGISTRY:
            return {
                "run_id": run_id,
                "status": "error",
                "result": {"error": f"unknown_cobaia_intent:{intent}"},
                "requires_confirm": False,
                "latency_ms": int((time.monotonic() - start) * 1000),
                "total_cost_credits": 0.0,
                "final_state": self.fsm.current_state,
            }

        if intent == "cobaia_warmup_next_action":
            intent_result = _handle_cobaia_warmup_intent(ctx)
        elif intent == "cobaia_autotune_synthesis":
            intent_result = _handle_cobaia_autotune_synthesis_intent(ctx)
        else:
            intent_result = {
                "ok": False,
                "intent": intent,
                "error": f"cobaia_intent_not_wired:{intent}",
                "status": "error",
            }

        ok = bool(intent_result.get("ok"))
        return {
            "run_id": run_id,
            "status": "completed" if ok else "error",
            "result": intent_result,
            "requires_confirm": False,
            "latency_ms": int((time.monotonic() - start) * 1000),
            "total_cost_credits": 0.0,
            "final_state": self.fsm.current_state,
        }

    # ----- F.6.4 resume from owner confirm ---------------------------------

    async def resume_from_run_id(
        self,
        run_id: str,
        approved: bool,
        comment: str = "",
    ) -> dict[str, Any]:
        """F.6.4 — restore FSM from brain_runs row + commit OR abort + persist final.

        Flow:
          1. load_run_for_resume(run_id) → 404 if missing
          2. Assert final_state == 'requires_confirm' (else 409 conflict, idempotent re-check)
          3. Fresh FSM IDLE → CLASSIFY → REASON → ACT → REVIEW (deterministic restore)
          4a. approved=True  → to_commit → COMMIT → complete → IDLE; final='owner_approved'
          4b. approved=False → abort → IDLE; final='owner_rejected'
          5. UPDATE brain_runs with final_state + owner_comment.

        Returns:
            {ok, run_id, final_state, result, comment} on success
            {ok: False, error} on failure (run_not_found / not_awaiting_confirm)
        """
        run = await self.persistence.load_run_for_resume(run_id)
        if not run:
            return {"ok": False, "error": "run_not_found", "run_id": run_id}

        if run.get("final_state") != "requires_confirm":
            return {
                "ok": False,
                "error": "not_awaiting_confirm",
                "current_state": run.get("final_state"),
                "run_id": run_id,
            }

        # Restore FSM deterministically through IDLE→CLASSIFY→REASON→ACT→REVIEW
        self.fsm = BrainStateMachine()
        self.fsm.start_classify()  # type: ignore[attr-defined]
        self.fsm.to_reason()       # type: ignore[attr-defined]
        self.fsm.to_act()          # type: ignore[attr-defined]
        self.fsm.to_review()       # type: ignore[attr-defined]

        # Reconstruct react_result from persisted brain_decisions (DRY via replay.py)
        react_result = await self._reconstruct_react_result(run_id, run)
        latency_ms = int(run.get("total_latency_ms") or 0)
        total_cost = float(run.get("total_cost_credits") or 0.0)
        confidence = float(run.get("confidence_score") or 0.5)

        if approved:
            self.fsm.to_commit()   # type: ignore[attr-defined]
            self.fsm.complete()    # type: ignore[attr-defined]
            new_state = "owner_approved"
        else:
            self.fsm.abort()       # type: ignore[attr-defined]
            new_state = "owner_rejected"

        try:
            await self.persistence.update_run_final(
                run_id=run_id,
                final_state=new_state,
                final_result=react_result,
                total_latency_ms=latency_ms,
                total_cost_credits=total_cost,
                confidence_score=confidence,
                owner_comment=comment,
            )
        except Exception as exc:  # noqa: BLE001 — defensive
            log.warning("resume update_run_final failed run_id=%s err=%s", run_id, exc)

        return {
            "ok": True,
            "run_id": run_id,
            "final_state": new_state,
            "result": react_result,
            "comment": comment,
            "final_fsm_state": self.fsm.current_state,
        }

    async def _reconstruct_react_result(
        self,
        run_id: str,
        run: dict[str, Any],
    ) -> dict[str, Any]:
        """F.6.4 — rebuild react_result from brain_decisions rows (replay reuse).

        Returns dict compatible with brain.intents.handle_intent() output shape
        (ok, intent, accumulated, final_answer, confidence, iterations, ...).
        """
        try:
            import json
            base: dict[str, Any] = {}
            raw = run.get("final_result")
            if isinstance(raw, str) and raw:
                try:
                    base = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    base = {}
            elif isinstance(raw, dict):
                base = raw
        except Exception:  # noqa: BLE001
            base = {}

        # Hydrate accumulated from brain_decisions (ACT→ACT iters with tool_invoked != null)
        try:
            from .replay import replay_run
            replay = await replay_run(run_id, mode="show_recorded")
            decisions = replay.get("decisions", []) if replay.get("ok") else []
        except Exception:  # noqa: BLE001
            decisions = []

        accumulated: list[dict[str, Any]] = []
        for d in decisions:
            tool = d.get("tool_invoked")
            if not tool:
                continue
            parts = tool.split(".")
            server_name = parts[1] if len(parts) >= 3 else ""
            tool_name = parts[2] if len(parts) >= 3 else (parts[-1] if parts else "")
            accumulated.append({
                "iteration": int(d.get("sequence") or 0),
                "thought": str(d.get("rationale") or "")[:1000],
                "tool_call": {
                    "server": server_name,
                    "tool": tool_name,
                    "args": d.get("tool_args") or {},
                },
                "tool_result": d.get("tool_result") or {},
            })

        merged = dict(base)
        merged["accumulated"] = accumulated
        merged.setdefault("ok", True)
        return merged

    # ----- persistence helpers (best-effort, never aborts decide flow) ----

    async def _persist_run_start(
        self, run_id: str, intent: str, context: dict[str, Any], requester: str,
    ) -> bool:
        try:
            await self.persistence.insert_run(run_id, intent, context, requester=requester)
            return True
        except Exception as exc:  # noqa: BLE001 — defensive
            log.warning("persistence.insert_run failed run_id=%s err=%s", run_id, exc)
            return False

    async def _persist_run_final(
        self,
        persistence_ok: bool,
        run_id: str,
        final_state: str,
        final_result: dict[str, Any],
        total_latency_ms: int,
        total_cost_credits: float,
        confidence_score: float,
    ) -> None:
        if not persistence_ok:
            return
        try:
            await self.persistence.update_run_final(
                run_id=run_id,
                final_state=final_state,
                final_result=final_result,
                total_latency_ms=total_latency_ms,
                total_cost_credits=total_cost_credits,
                confidence_score=confidence_score,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("persistence.update_run_final failed run_id=%s err=%s", run_id, exc)

    def _schedule_decision(
        self,
        persistence_ok: bool,
        run_id: str,
        sequence: int,
        state_from: str,
        state_to: str,
        *,
        tool_invoked: str | None = None,
        tool_args: dict[str, Any] | None = None,
        tool_result: dict[str, Any] | None = None,
        rationale: str = "",
        latency_ms: int = 0,
    ) -> None:
        if not persistence_ok:
            return
        try:
            self.persistence.schedule_decision(
                run_id=run_id,
                sequence=sequence,
                state_from=state_from,
                state_to=state_to,
                tool_invoked=tool_invoked,
                tool_args=tool_args,
                tool_result=tool_result,
                rationale=rationale,
                latency_ms=latency_ms,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("schedule_decision failed run_id=%s seq=%d err=%s", run_id, sequence, exc)

    # ----- agentmemory opt-in (F.6.3 D4) ----------------------------------

    def _maybe_save_agentmemory(
        self,
        run_id: str,
        intent: str,
        context: dict[str, Any],
        result: dict[str, Any],
        status: str,
    ) -> None:
        """D4 opt-in: agentmemory MCP save async fire-and-forget per INTENT_REGISTRY config.

        Owner override via context['force_agentmemory_save']=True.
        """
        cfg = INTENT_REGISTRY.get(intent, {})
        enabled = bool(cfg.get("agentmemory_save", False)) or bool(context.get("force_agentmemory_save"))
        if not enabled:
            return
        # Fire-and-forget: NÃO await, NÃO bloqueia decide() return.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._agentmemory_save_task(run_id, intent, context, result, status))

    async def _agentmemory_save_task(
        self,
        run_id: str,
        intent: str,
        context: dict[str, Any],
        result: dict[str, Any],
        status: str,
    ) -> None:
        """Background agentmemory save via gateway dispatch. Timeout 10s. Errors → Sentry."""
        try:
            content = self._build_agentmemory_content(intent, context, result, status)
            concepts = ",".join([f"brain-{intent}", f"run-{run_id[:8]}", f"status-{status}"])
            # Fire via gateway dispatch — timeout already in GatewayDispatcher default 30s.
            await asyncio.wait_for(
                self.dispatcher.invoke_tool(
                    server="agentmemory",
                    tool="memory_save",
                    args={
                        "content": content,
                        "type": "decision",
                        "concepts": concepts,
                        "files": "",
                    },
                ),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            log.warning("agentmemory save timeout run_id=%s intent=%s", run_id, intent)
        except Exception as exc:  # noqa: BLE001
            log.warning("agentmemory save failed run_id=%s intent=%s err=%s", run_id, intent, exc)
            from core.sentry_via_gateway import capture_exception as _sentry_capture
            _sentry_capture(exc, requester="brain-core")

    async def stream_decide(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        intent_hint: str | None = None,
        image_b64: str | None = None,
    ):
        """Async generator yielding SSE event dicts for Cmd+K AI streaming (UX-RM-F5-A/B).

        F5-B: citation events after final, image_b64 graceful 501 stub.
        Uses intent_hint if in INTENT_REGISTRY, else defaults to 'answer_owner'.
        Yields: thought | tool_call | tool_result | citation | final | error dicts.
        """
        from ._react import react_loop_streaming
        from .citation_resolver import resolve_citation

        ctx = dict(context or {})
        ctx.setdefault("user_prompt", prompt)

        # F5-B: image analysis — graceful 501 stub (vision not configured)
        if image_b64:
            yield {"type": "thought", "chunk": "Analisando imagem recebida..."}
            yield {
                "type": "final",
                "answer": (
                    "Análise de imagem não disponível nesta versão (F.future). "
                    "Envie texto com sua pergunta."
                ),
                "confidence": 0.0,
                "iterations": 0,
                "status": "not_implemented",
                "intent": "image_analysis",
            }
            return

        intent = intent_hint if (intent_hint and intent_hint in INTENT_REGISTRY) else "answer_owner"

        yield {"type": "thought", "chunk": f"Analisando solicitação ({intent})..."}

        intent_config = INTENT_REGISTRY[intent]
        tool_calls_seen: list[dict[str, Any]] = []

        async for event in react_loop_streaming(intent, ctx, intent_config, self.dispatcher):
            if event.get("type") == "tool_call":
                tool_calls_seen.append(event)
                yield event
            elif event.get("type") == "final":
                yield {**event, "intent": intent}
                # F5-B: emit citation pills for each tool invoked
                for tc in tool_calls_seen:
                    tool_full = tc.get("tool", "")
                    parts = tool_full.split(".", 1)
                    server = parts[0] if parts else ""
                    tool_name = parts[1] if len(parts) > 1 else tool_full
                    source_type, source_id = _map_tool_to_citation(
                        server, tool_name, tc.get("args") or {}
                    )
                    resolved = resolve_citation(source_type, source_id)
                    yield {
                        "type": "citation",
                        "source_type": source_type,
                        "source_id": source_id,
                        "source_url": resolved.get("url", "#dashboard"),
                        "title": resolved.get("title", source_id),
                        "snippet": resolved.get("snippet", ""),
                        "confidence": 0.8,
                    }
            else:
                yield event

    @staticmethod
    def _build_agentmemory_content(
        intent: str, context: dict[str, Any], result: dict[str, Any], status: str,
    ) -> str:
        """Compact 1-3 sentence summary (per CLAUDE.md memory rules)."""
        ctx_preview = str({k: context[k] for k in list(context.keys())[:3]})[:200]
        ans = result.get("final_answer")
        ans_preview = str(ans)[:300] if ans else f"status={status}"
        return (
            f"Brain.decide intent={intent} status={status}. "
            f"Context preview: {ctx_preview}. Result: {ans_preview}"
        )[:2000]


# F5-B module-level helper — used by Brain.stream_decide citation emit.

def _map_tool_to_citation(server: str, tool: str, args: dict[str, Any]) -> tuple[str, str]:
    """Map (server, tool, args) → (source_type, source_id) for citation resolver."""
    if "agentmemory" in server:
        sid = args.get("key") or args.get("source_id") or args.get("type") or "memory"
        return "memory", str(sid)[:80]
    if "hermes-skills" in server or "skill" in tool.lower():
        sid = args.get("skill_id") or args.get("name") or tool
        return "skill", str(sid)[:80]
    if "hermes-linkedin" in server:
        return "tool_result", f"linkedin.{tool}"[:80]
    if "hermes-llm" in server:
        return "tool_result", f"llm.{tool}"[:80]
    if server:
        return "tool_result", f"{server}.{tool}"[:80]
    return "tool_result", str(tool)[:80]
