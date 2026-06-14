"""F.9.2 — Pipeline Studio execution engine.

REUSE Brain.decide() route_skill_run (F.6.2 + F.9.2 enhancement) → gateway dispatch.
NÃO duplicates GatewayDispatcher logic — Brain.decide() owns audit trail
(brain_runs + brain_decisions per step), cost aggregation, and dispatch infrastructure.

Cross-ref:
  .claude/PLAN.md § "F.9.2 Decisões Cristalizadas" D1-D8 (commit b0f2f84)
  api/pipeline_studio.py F.9.1 CRUD (drafts) + F.9.2 execute/runs/abort
  brain/decide.py F.6.2 Brain orchestrator
  brain/intents.py F.9.2 route_skill_run direct dispatch path
  migrations/2026_06_pipeline_studio.sql F.9.1 pipeline_runs_granular schema

8 decisões cristalizadas:
  D1 ASYNC BACKGROUND + POLLING        — execute returns 202 + run_id immediately
  D2 STOP DEFAULT + continue_on_error  — per-step opt-in, default abort on error
  D3 JINJA2 STRICT + SANDBOXED         — StrictUndefined missing var raises
  D4 PRE-EXECUTE VALIDATION            — batch mcp_registry query, fail-fast 400
  D5 COST sync via Brain.decide()      — total_cost_credits propagated per step
  D6 A/B PARALLEL asyncio.gather       — return_exceptions=True OBRIGATÓRIO (mem_mq7i9caw)
  D7 SOFT ABORT in-memory flag         — current step finishes, subsequent aborted
  D8 STEP TIMEOUT 5min                 — asyncio.wait_for per step

BLACKLIST R2 intacto: engine NUNCA chama linkedin/* direto, sempre via Brain → gateway.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
import uuid
from typing import Any, Optional

import yaml
from jinja2 import StrictUndefined, UndefinedError
from jinja2.sandbox import SandboxedEnvironment

from brain.decide import Brain
from core.state import DB_PATH, ws_manager

log = logging.getLogger("hermes.pipeline_engine")

# D7: in-memory abort registry (run_id → reason). Process-local, transient.
_ABORT_REQUESTED: dict[str, str] = {}

# D8: per-step timeout hard cap (5min — long enough for slow LLM tier T3 fallback).
STEP_TIMEOUT_SECONDS = 300

# D5: output_json truncation (F.6.3 D6 pattern — sqlite TEXT performance).
_OUTPUT_TRUNCATE = 2000

# D4: tool tiers blocked from execution (registry governance).
_BLOCKED_TIERS = frozenset({"reserved", "quarantine", "deprecated"})


def _db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


class PipelineEngine:
    """Async background executor for owner-built YAML pipelines.

    Lifecycle:
      1. execute_draft endpoint validates tools via validate_tools() (D4 fail-fast).
      2. INSERT pipeline_runs_granular step_idx=-1 _run_init_ row (reserves run_id).
      3. BackgroundTasks dispatches execute_run() (D1 returns 202 immediately).
      4. Per step: render Jinja args (D3) → Brain.decide route_skill_run (D5) → persist row.
      5. On error: stop unless continue_on_error (D2). On timeout: error row (D8).
      6. On abort flag: current step finishes, subsequent rows status='aborted' (D7).

    Poll via GET /api/pipeline-studio/runs/{run_id} (api/pipeline_studio.py).
    """

    def __init__(self, brain: Brain | None = None) -> None:
        self.brain = brain or Brain()
        # D3 SandboxedEnvironment: blocks arbitrary attr access, getattr, builtins.
        # StrictUndefined: missing variable → UndefinedError (NÃO silent empty string).
        self.jinja_env = SandboxedEnvironment(undefined=StrictUndefined)

    # -------------------- F.9.3 WS broadcast (fire-and-forget) --------------------

    @staticmethod
    def _broadcast_pipeline_event(event_type: str, payload: dict[str, Any]) -> None:
        """Fire-and-forget WS broadcast per step event (F.9.3 D4 pattern).

        Does NOT block execute_run — asyncio.ensure_future schedules on running loop.
        Silently swallowed if no loop running or ws_manager unavailable.
        Canonical event_type dot-notation: pipeline.step_start / pipeline.step_done /
        pipeline.step_error / pipeline.run_complete / pipeline.run_aborted.
        """
        try:
            event = {"event_type": event_type, "payload": payload}
            loop = asyncio.get_running_loop()
            loop.create_task(ws_manager.broadcast(event))
        except Exception:  # noqa: silenciado intencional — WS broadcast não bloqueia engine
            pass

    # -------------------- D7 abort registry --------------------

    @classmethod
    def request_abort(cls, run_id: str, reason: str = "") -> None:
        """SOFT abort signal — current step finishes, subsequent skipped."""
        _ABORT_REQUESTED[run_id] = reason or "owner_requested"

    @classmethod
    def is_abort_requested(cls, run_id: str) -> bool:
        return run_id in _ABORT_REQUESTED

    # -------------------- D4 pre-execute validation --------------------

    async def validate_tools(self, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Batch validate ALL step tools exist in mcp_registry + tier OK.

        Single SELECT (NÃO N+1). Returns list of errors (empty if valid).
        Each error: {step_idx, step_name, tool?, error}.
        """
        errors: list[dict[str, Any]] = []

        if not steps:
            return [{"step_idx": -1, "step_name": "_global_", "error": "empty_steps"}]

        # Build available tools map from mcp_registry (active rows only).
        available_tools: dict[str, dict[str, Any]] = {}
        conn = _db_connect()
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='mcp_registry'"
            ).fetchone()
            if not row:
                # No registry seeded → cannot validate; allow but warn.
                log.warning("mcp_registry missing — D4 validation degraded (allowing all)")
                return []
            rows = conn.execute(
                "SELECT server, tools, status, tier FROM mcp_registry WHERE status = 'active'"
            ).fetchall()
            for r in rows:
                tools_field = r["tools"] or "[]"
                try:
                    tools_list = json.loads(tools_field) if isinstance(tools_field, str) else (tools_field or [])
                except Exception:
                    tools_list = []
                for tname in tools_list:
                    full_name = f"{r['server']}.{tname}"
                    available_tools[full_name] = {
                        "server": r["server"],
                        "tier": r["tier"],
                    }
        finally:
            conn.close()

        for idx, step in enumerate(steps):
            tool = (step.get("tool") or "").strip()
            step_name = step.get("name", f"step_{idx}")

            if not tool:
                errors.append({"step_idx": idx, "step_name": step_name, "error": "missing_tool"})
                continue

            if tool not in available_tools:
                errors.append({
                    "step_idx": idx, "step_name": step_name, "tool": tool,
                    "error": "tool_not_found_in_mcp_registry",
                })
                continue

            tier = available_tools[tool]["tier"]
            if tier in _BLOCKED_TIERS:
                errors.append({
                    "step_idx": idx, "step_name": step_name, "tool": tool,
                    "error": f"tool_tier_{tier}_blocked",
                })

        return errors

    # -------------------- D3 Jinja2 render --------------------

    def _render_jinja(self, value: Any, variables: dict[str, Any]) -> Any:
        """Strict render. Missing var → RuntimeError('jinja_undefined: ...').

        Non-strings pass through (numbers, lists, dicts handled per-leaf by _render_args).
        Strings without `{{` fast-path skip render.
        """
        if not isinstance(value, str):
            return value
        if "{{" not in value and "{%" not in value:
            return value
        try:
            tmpl = self.jinja_env.from_string(value)
            return tmpl.render(**variables)
        except UndefinedError as exc:
            raise RuntimeError(f"jinja_undefined: {exc}") from exc

    def _render_args(self, args: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
        """Render each arg value via Jinja (recursive for nested dicts/lists)."""
        out: dict[str, Any] = {}
        for k, v in (args or {}).items():
            out[k] = self._render_value(v, variables)
        return out

    def _render_value(self, value: Any, variables: dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {k: self._render_value(v, variables) for k, v in value.items()}
        if isinstance(value, list):
            return [self._render_value(v, variables) for v in value]
        return self._render_jinja(value, variables)

    # -------------------- DB writers --------------------

    def _insert_step_started(
        self, run_id: str, draft_id: str, step_idx: int, step_name: str,
        tool: Optional[str], ab_group: Optional[str] = None,
    ) -> None:
        conn = _db_connect()
        try:
            conn.execute(
                """INSERT INTO pipeline_runs_granular
                   (run_id, draft_id, step_idx, step_name, tool_invoked, status, started_at, ab_group)
                   VALUES (?, ?, ?, ?, ?, 'running', CURRENT_TIMESTAMP, ?)""",
                (run_id, draft_id, step_idx, step_name, tool, ab_group),
            )
            conn.commit()
        finally:
            conn.close()

    def _update_step_finished(
        self, run_id: str, step_idx: int, status: str,
        output_json: Optional[str], error: Optional[str],
        latency_ms: int, cost_credits: float,
    ) -> None:
        conn = _db_connect()
        try:
            conn.execute(
                """UPDATE pipeline_runs_granular
                   SET status = ?, output_json = ?, error = ?, ended_at = CURRENT_TIMESTAMP,
                       latency_ms = ?, cost_credits = ?
                   WHERE run_id = ? AND step_idx = ?""",
                (status, output_json, error, latency_ms, float(cost_credits), run_id, step_idx),
            )
            conn.commit()
        finally:
            conn.close()

    def _insert_aborted_step(
        self, run_id: str, draft_id: str, step_idx: int, step_name: str,
        tool: Optional[str], reason: str, ab_group: Optional[str] = None,
    ) -> None:
        conn = _db_connect()
        try:
            conn.execute(
                """INSERT INTO pipeline_runs_granular
                   (run_id, draft_id, step_idx, step_name, tool_invoked, status, error,
                    started_at, ended_at, latency_ms, cost_credits, ab_group)
                   VALUES (?, ?, ?, ?, ?, 'skipped', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0, 0, ?)""",
                (run_id, draft_id, step_idx, step_name, tool, f"aborted: {reason}"[:_OUTPUT_TRUNCATE], ab_group),
            )
            conn.commit()
        finally:
            conn.close()

    def _update_init_status(self, run_id: str, status: str) -> None:
        """Update the _run_init_ row (step_idx=-1)."""
        conn = _db_connect()
        try:
            conn.execute(
                """UPDATE pipeline_runs_granular
                   SET status = ?, ended_at = CURRENT_TIMESTAMP
                   WHERE run_id = ? AND step_idx = -1""",
                (status, run_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _load_draft_yaml(self, draft_id: str) -> Optional[str]:
        conn = _db_connect()
        try:
            row = conn.execute(
                "SELECT yaml_blob FROM pipeline_drafts WHERE id = ?", (draft_id,)
            ).fetchone()
            return row["yaml_blob"] if row else None
        finally:
            conn.close()

    # -------------------- main loop --------------------

    async def execute_run(
        self,
        run_id: str,
        draft_id: str,
        variables: Optional[dict[str, Any]] = None,
        ab_group: Optional[str] = None,
    ) -> None:
        """Main background execution. Persists per-step rows in pipeline_runs_granular.

        ab_group: 'A' | 'B' | None — passed through context for downstream observability.
        """
        variables = dict(variables or {})
        variables["_system"] = {
            "run_id": run_id, "draft_id": draft_id, "ab_group": ab_group,
        }

        self._update_init_status(run_id, "running")

        yaml_blob = self._load_draft_yaml(draft_id)
        if not yaml_blob:
            self._update_init_status(run_id, "error")
            log.warning("execute_run: draft %s not found", draft_id)
            return

        try:
            parsed = yaml.safe_load(yaml_blob)
        except yaml.YAMLError as exc:
            self._update_init_status(run_id, "error")
            log.warning("execute_run: yaml parse fail %s: %s", draft_id, exc)
            return

        steps = (parsed or {}).get("steps", []) if isinstance(parsed, dict) else []
        if not steps:
            self._update_init_status(run_id, "error")
            return

        previous_outputs: dict[str, Any] = {}

        for step_idx, step in enumerate(steps):
            # D7 abort check BEFORE starting next step.
            if self.is_abort_requested(run_id):
                reason = _ABORT_REQUESTED.pop(run_id, "owner_requested")
                # Mark this + subsequent steps as skipped/aborted.
                for remaining_idx in range(step_idx, len(steps)):
                    rstep = steps[remaining_idx]
                    self._insert_aborted_step(
                        run_id, draft_id, remaining_idx,
                        rstep.get("name", f"step_{remaining_idx}"),
                        rstep.get("tool"),
                        reason,
                        ab_group,
                    )
                self._update_init_status(run_id, "aborted")
                self._broadcast_pipeline_event("pipeline.run_aborted", {
                    "run_id": run_id, "status": "aborted", "reason": reason,
                })
                return

            step_name = step.get("name", f"step_{step_idx}")
            tool = step.get("tool")
            args = step.get("args", {}) or {}
            continue_on_error = bool(step.get("continue_on_error", False))

            self._insert_step_started(run_id, draft_id, step_idx, step_name, tool, ab_group)
            self._broadcast_pipeline_event("pipeline.step_start", {
                "run_id": run_id, "step_idx": step_idx, "step_name": step_name,
                "tool": tool, "draft_id": draft_id,
            })
            start_ts = time.monotonic()

            try:
                rendered_args = self._render_args(args, {**variables, **previous_outputs})

                if not tool or "." not in tool:
                    raise RuntimeError(f"invalid_tool_format: {tool!r} (expected 'server.tool')")
                server_part, _, tool_part = tool.partition(".")

                # D5 cost via Brain.decide() route_skill_run (F.9.2 enhanced direct dispatch).
                # D8 per-step timeout 5min hard.
                decide_result = await asyncio.wait_for(
                    self.brain.decide(
                        intent="route_skill_run",
                        context={
                            "tool_call": {
                                "server": server_part,
                                "tool": tool_part,
                                "args": rendered_args,
                            },
                            "_pipeline": {
                                "run_id": run_id,
                                "step_idx": step_idx,
                                "ab_group": ab_group,
                            },
                        },
                        requester="pipeline_engine",
                    ),
                    timeout=STEP_TIMEOUT_SECONDS,
                )

                latency_ms = int((time.monotonic() - start_ts) * 1000)
                decide_status = decide_result.get("status")
                cost = float(decide_result.get("total_cost_credits", 0.0) or 0.0)

                if decide_status == "completed":
                    inner = decide_result.get("result", {}) or {}
                    output_payload = json.dumps(inner, default=str)[:_OUTPUT_TRUNCATE]
                    previous_outputs[f"step_{step_idx}"] = inner
                    self._update_step_finished(
                        run_id, step_idx, "completed",
                        output_payload, None, latency_ms, cost,
                    )
                    self._broadcast_pipeline_event("pipeline.step_done", {
                        "run_id": run_id, "step_idx": step_idx, "step_name": step_name,
                        "status": "completed", "latency_ms": latency_ms, "cost": cost,
                    })
                else:
                    error_msg = json.dumps(decide_result, default=str)[:_OUTPUT_TRUNCATE]
                    self._update_step_finished(
                        run_id, step_idx, "error",
                        None, error_msg, latency_ms, cost,
                    )
                    self._broadcast_pipeline_event("pipeline.step_error", {
                        "run_id": run_id, "step_idx": step_idx, "step_name": step_name,
                        "status": "error", "error": error_msg[:200],
                    })
                    if not continue_on_error:
                        self._update_init_status(run_id, "error")
                        self._broadcast_pipeline_event("pipeline.run_complete", {
                            "run_id": run_id, "status": "error",
                        })
                        return

            except asyncio.TimeoutError:
                latency_ms = STEP_TIMEOUT_SECONDS * 1000
                self._update_step_finished(
                    run_id, step_idx, "error",
                    None, f"step_timeout_{STEP_TIMEOUT_SECONDS}s", latency_ms, 0.0,
                )
                self._broadcast_pipeline_event("pipeline.step_error", {
                    "run_id": run_id, "step_idx": step_idx, "step_name": step_name,
                    "status": "error", "error": f"timeout_{STEP_TIMEOUT_SECONDS}s",
                })
                if not continue_on_error:
                    self._update_init_status(run_id, "error")
                    self._broadcast_pipeline_event("pipeline.run_complete", {
                        "run_id": run_id, "status": "error",
                    })
                    return

            except RuntimeError as exc:
                # D3 Jinja UndefinedError + invalid tool format
                latency_ms = int((time.monotonic() - start_ts) * 1000)
                self._update_step_finished(
                    run_id, step_idx, "error",
                    None, str(exc)[:_OUTPUT_TRUNCATE], latency_ms, 0.0,
                )
                self._broadcast_pipeline_event("pipeline.step_error", {
                    "run_id": run_id, "step_idx": step_idx, "step_name": step_name,
                    "status": "error", "error": str(exc)[:200],
                })
                if not continue_on_error:
                    self._update_init_status(run_id, "error")
                    self._broadcast_pipeline_event("pipeline.run_complete", {
                        "run_id": run_id, "status": "error",
                    })
                    return

            except Exception as exc:  # noqa: BLE001 — defensive boundary
                latency_ms = int((time.monotonic() - start_ts) * 1000)
                self._update_step_finished(
                    run_id, step_idx, "error",
                    None, f"{type(exc).__name__}: {exc}"[:_OUTPUT_TRUNCATE], latency_ms, 0.0,
                )
                try:
                    import sentry_sdk  # type: ignore[import-not-found]
                    sentry_sdk.capture_exception(exc)
                except Exception:  # noqa: BLE001
                    pass
                self._broadcast_pipeline_event("pipeline.step_error", {
                    "run_id": run_id, "step_idx": step_idx, "step_name": step_name,
                    "status": "error", "error": f"{type(exc).__name__}"[:100],
                })
                if not continue_on_error:
                    self._update_init_status(run_id, "error")
                    self._broadcast_pipeline_event("pipeline.run_complete", {
                        "run_id": run_id, "status": "error",
                    })
                    return

        self._update_init_status(run_id, "completed")
        self._broadcast_pipeline_event("pipeline.run_complete", {
            "run_id": run_id, "status": "completed",
        })


# ----- D6 A/B parallel test -----

async def execute_ab_test(
    draft_a_id: str,
    draft_b_id: str,
    variables: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """D6 PARALLEL A/B asyncio.gather (return_exceptions=True OBRIGATÓRIO).

    Reference: mem_mq7i9caw_cfc90416f23e — without return_exceptions=True,
    one task's exception silently kills sibling tasks via cancellation.

    Returns dict with both run_ids + any exceptions encountered.
    """
    engine = PipelineEngine()
    run_a_id = str(uuid.uuid4())
    run_b_id = str(uuid.uuid4())

    # Insert init rows for both (so polling works before background tasks land).
    for rid, did in [(run_a_id, draft_a_id), (run_b_id, draft_b_id)]:
        conn = _db_connect()
        try:
            conn.execute(
                """INSERT INTO pipeline_runs_granular
                   (run_id, draft_id, step_idx, step_name, status, started_at)
                   VALUES (?, ?, -1, '_run_init_', 'pending', CURRENT_TIMESTAMP)""",
                (rid, did),
            )
            conn.commit()
        finally:
            conn.close()

    results = await asyncio.gather(
        engine.execute_run(run_a_id, draft_a_id, variables, ab_group="A"),
        engine.execute_run(run_b_id, draft_b_id, variables, ab_group="B"),
        return_exceptions=True,  # D6 CRITICAL (mem_mq7i9caw)
    )

    errors = [
        f"{type(r).__name__}: {r}" for r in results if isinstance(r, BaseException)
    ]

    return {
        "ab_test_started": True,
        "run_a_id": run_a_id,
        "run_b_id": run_b_id,
        "errors": errors,
    }
