"""F.4.2 — Auto-Skill Loop orchestrator (lab sandbox + GitHub MCP PR + Workflow trigger).

Sub-commits:
  C1 (this commit) — dispatch_sandbox_test (D1 PIVOT inline YAML validation)
  C2 (next)        — dispatch_github_pr (D2/D3/D4/D5 GitHub MCP PR creation)
  C3 (last)        — trigger_workflow_synthesis (D6 manual API trigger)

PIVOT D1 — Lab sandbox = inline YAML validation + mock (NOT REUSE
mcp.hermes-skills.test_skill_dryrun direct). Reason: F.5.2
test_skill_dryrun(skill_name, input_data, mock_llm=True) reads YAML from disk
(skills/*.yaml), does NOT accept yaml_blob param. Proposal YAML is staging-only
(skill_proposals.yaml_blob), not yet in skills/. Inline validation is an honest
match of F.5.2 mock_llm=True scaffold semantics (both return stub responses).

PIVOT D7 — Cost tracking via mcp_calls.requester='brain-f4' (NOT extra schema
column). Reason: F.5.3 mcp_calls schema 9 cols original (id, server, tool, args,
response, error, duration_ms, requester, created_at). Aggregate cost via
`WHERE requester LIKE 'brain-%'`.

F.future backlogs:
  - F.5.2 enhance test_skill_dryrun to accept yaml_blob param → refactor here.
  - Migration extra column quando F.8/F.future precisar nova dimensão.

Cross-ref:
  .claude/PLAN.md § "F.4.2 Decisões Cristalizadas" (commit 4f09f52)
    + PIVOT D1/D7 owner alignment (commit b8fe9d2)
  api/skills.py F.4.1 stubs labeled → substituídos C1/C2/C3
  core/skill_proposals.py F.4.1 update_lab_result + update_pr_status (wired)
  brain/dispatch.py F.6.2 GatewayDispatcher (consumir mcp.* via gateway)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Optional

import yaml

from brain.dispatch import GatewayDispatcher
from core.skill_proposals import SkillProposalsManager, manager as proposals_manager

log = logging.getLogger("hermes.auto_skill_runner")


# D1 PIVOT — minimum YAML keys required to be considered a valid skill proposal.
_REQUIRED_YAML_KEYS: tuple[str, ...] = ("name", "version")

# At least ONE of these required (LLM-driven skill OR declarative pipeline).
_REQUIRE_EITHER: tuple[str, ...] = ("provider", "steps")

# D1 — lab sandbox timeout cap (defensive; inline validation is microseconds).
LAB_TIMEOUT_SECONDS: float = 60.0

# D7 PIVOT — requester encodes chapter context in mcp_calls (no schema change).
F4_REQUESTER: str = "brain-f4"


def _slugify(name: str, max_len: int = 40) -> str:
    """D3 — lowercase-dashed slug max 40 chars (trailing dash stripped)."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    truncated = slug[:max_len].rstrip("-")
    return truncated or "unnamed"


def _shortid(proposal_id: str) -> str:
    """D3 — first 6 chars of proposal_id (UUID first segment)."""
    head = (proposal_id or "").split("-")[0]
    return head[:6] or "000000"


class AutoSkillRunner:
    """F.4.2 orchestrator: lab sandbox dispatch + GitHub MCP PR + Workflow trigger.

    C1 implements only dispatch_sandbox_test + helpers (D1/D3/D7 PIVOTs).
    C2 will add dispatch_github_pr; C3 will add trigger_workflow_synthesis.
    """

    def __init__(
        self,
        dispatcher: Optional[GatewayDispatcher] = None,
        manager: Optional[SkillProposalsManager] = None,
    ) -> None:
        self.dispatcher = dispatcher or GatewayDispatcher()
        self.manager = manager or proposals_manager

    # ------------------------------------------------------------------
    # D1 PIVOT — inline YAML validation (lab sandbox mock)
    # ------------------------------------------------------------------

    def _validate_yaml_inline(self, yaml_blob: str) -> dict[str, Any]:
        """Parse + validate proposed skill YAML inline.

        Returns lab_test_result dict matching the schema persisted in
        skill_proposals.lab_test_result:

            {status, stdout, stderr, latency_ms, exit_code, mock}

        D1 honest match of F.5.2 mock_llm=True scaffold semantics.
        """
        start = time.perf_counter()
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        status = "passed"
        exit_code = 0
        parsed: Any = None

        # Parse
        try:
            parsed = yaml.safe_load(yaml_blob)
        except yaml.YAMLError as exc:
            stderr_lines.append(f"yaml.YAMLError: {exc}")
            status = "failed"
            exit_code = 1

        # Structure check
        if status == "passed" and not isinstance(parsed, dict):
            stderr_lines.append("YAML root must be a mapping (dict)")
            status = "failed"
            exit_code = 1

        # Required keys present
        if status == "passed":
            missing = [k for k in _REQUIRED_YAML_KEYS if k not in parsed]
            if missing:
                stderr_lines.append(f"Missing required key(s): {missing}")
                status = "failed"
                exit_code = 1

        # At least one of provider | steps
        if status == "passed":
            if not any(k in parsed for k in _REQUIRE_EITHER):
                stderr_lines.append(
                    f"At least one of {list(_REQUIRE_EITHER)} required"
                )
                status = "failed"
                exit_code = 1

        if status == "passed":
            present = sorted(
                k for k in parsed
                if k in (_REQUIRED_YAML_KEYS + _REQUIRE_EITHER)
            )
            stdout_lines.append(f"Validation OK: keys {present}")

        latency_ms = int((time.perf_counter() - start) * 1000)
        return {
            "status": status,
            "stdout": "\n".join(stdout_lines),
            "stderr": "\n".join(stderr_lines),
            "latency_ms": latency_ms,
            "exit_code": exit_code,
            "mock": True,
        }

    # ------------------------------------------------------------------
    # dispatch_sandbox_test — fetch proposal → validate → persist
    # ------------------------------------------------------------------

    async def dispatch_sandbox_test(self, proposal_id: str) -> dict[str, Any]:
        """C1 — orchestrate lab validation for a single proposal.

        Transitions proposal.status: lab_running → lab_passed | lab_failed.
        Persists lab_test_result via manager.update_lab_result.

        Returns:
            {ok, proposal_id, lab_test_result, new_status}

        Raises:
            LookupError when proposal_id missing (api layer maps to 404).
        """
        proposal = self.manager.get(proposal_id)  # raises LookupError

        try:
            await asyncio.wait_for(
                self._run_validation(proposal),
                timeout=LAB_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            lab_result = {
                "status": "failed",
                "stdout": "",
                "stderr": f"lab timeout after {LAB_TIMEOUT_SECONDS}s",
                "latency_ms": int(LAB_TIMEOUT_SECONDS * 1000),
                "exit_code": 124,
                "mock": True,
            }
            self.manager.update_lab_result(
                proposal_id, lab_result, lab_test_status="failed",
            )
            log.warning(
                "lab dispatch timeout proposal_id=%s requester=%s",
                proposal_id, F4_REQUESTER,
            )
            await self._ws_emit("brain.skill_lab_validated", {
                "proposal_id": proposal_id,
                "status": "failed",
                "reason": "timeout",
            })
            return {
                "ok": False,
                "proposal_id": proposal_id,
                "lab_test_result": lab_result,
                "new_status": "lab_failed",
            }

        updated = self.manager.get(proposal_id)
        lab_result = json.loads(updated.get("lab_test_result") or "{}")
        new_status = updated.get("status")

        await self._ws_emit("brain.skill_lab_validated", {
            "proposal_id": proposal_id,
            "status": lab_result.get("status"),
            "latency_ms": lab_result.get("latency_ms"),
        })

        log.info(
            "lab dispatch proposal_id=%s requester=%s status=%s latency=%sms",
            proposal_id, F4_REQUESTER, lab_result.get("status"),
            lab_result.get("latency_ms"),
        )
        return {
            "ok": lab_result.get("status") == "passed",
            "proposal_id": proposal_id,
            "lab_test_result": lab_result,
            "new_status": new_status,
        }

    async def _run_validation(self, proposal: dict[str, Any]) -> None:
        """Inline validation wrapped in coroutine for asyncio.wait_for compat."""
        yaml_blob = proposal.get("yaml_blob") or ""
        lab_result = self._validate_yaml_inline(yaml_blob)
        self.manager.update_lab_result(
            proposal["id"], lab_result, lab_test_status=lab_result["status"],
        )

    async def _ws_emit(self, event_type: str, payload: dict[str, Any]) -> None:
        """Fire-and-forget WS broadcast. Failures captured to Sentry if available."""
        try:
            from core.state import ws_manager
            await ws_manager.broadcast({
                "event_type": event_type,
                "payload": payload,
            })
        except Exception as exc:  # noqa: BLE001 — broadcast must never block dispatch
            log.debug("ws emit %s failed: %s", event_type, exc)
            try:
                import sentry_sdk  # type: ignore[import-not-found]
                sentry_sdk.capture_exception(exc)
            except Exception:
                pass
