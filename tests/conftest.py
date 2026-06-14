"""F.6.5 pytest harness fixtures + golden case schema validator.

Reuses MockDispatcher from brain._smoke (D4 — NÃO new fixture pattern) and
extends with per-case canned responses via GoldenMockDispatcher subclass.

Schema validation (Pydantic) executed at collection time — malformed YAML
breaks collection loud (não silently skipped).

Cross-ref:
  .claude/PLAN.md § F.6.5 Decisões D1-D6 (commit 4778e7b)
  brain/_smoke.py F.6.2 MockDispatcher (route/invoke_tool contract)
  .claude/brain-golden-cases/*.yaml (12 cases × 2 per intent × 6 intents)
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel, Field, ValidationError

from brain._smoke import MockDispatcher
from brain.decide import Brain
from brain.persistence import get_persistence, reset_persistence

GOLDEN_DIR = Path(__file__).parent.parent / ".claude" / "brain-golden-cases"


# ---------------------------------------------------------------------------
# Pydantic schema — fail loud at YAML load (reviewer dim 8 cristalizado).
# ---------------------------------------------------------------------------

class GoldenCaseExpected(BaseModel):
    """Expected outcome fields. All optional except status + requires_confirm."""

    status: str
    requires_confirm: bool
    intent_classified: str | None = None
    min_confidence: float | None = None
    max_confidence: float | None = None
    max_iterations: int | None = None
    final_state: str | None = None
    tools_invoked: list[str] = Field(default_factory=list)
    final_state_fsm: str | None = None  # FSM ("IDLE") if owner wants strict check


class GoldenCase(BaseModel):
    """Golden case YAML schema. Validated at collection time."""

    intent: str
    case_id: str
    description: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    mock_dispatcher_responses: dict[str, Any] = Field(default_factory=dict)
    expected: GoldenCaseExpected


# ---------------------------------------------------------------------------
# GoldenMockDispatcher — subclass of MockDispatcher with YAML-driven responses.
# ---------------------------------------------------------------------------

class GoldenMockDispatcher(MockDispatcher):
    """MockDispatcher with per-case canned responses.

    YAML key conventions:
      - "hermes-llm.route" → catch-all for all route() calls (any task_type)
      - <task_type> (e.g. "reasoning", "code_gen") → route() match by task_type
      - "<server>.<tool>" (e.g. "hermes-prospects.score_lead") → invoke_tool() match

    Response value can be:
      - dict {ok, response, cost_credits} (single call)
      - list of dicts (sequential calls — iteration N uses list[min(N, len-1)])

    Falls back to base MockDispatcher behavior when key missing (safe default).
    """

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        super().__init__()
        self.responses = responses or {}
        # Counters for list-based responses (loops/max_iter cases).
        self._route_counter: dict[str, int] = {}
        self._invoke_counter: dict[str, int] = {}

    async def route(self, task_type: str, prompt: str, **kw: Any) -> dict[str, Any]:
        self.route_calls.append((task_type, prompt[:80]))
        # Match precedence: catch-all "hermes-llm.route" > task_type > base mock.
        config = self.responses.get("hermes-llm.route") or self.responses.get(task_type)
        if config is None:
            # Build canned response inline (avoid re-recording call in super()).
            canned = (
                f'{{"rationale": "mock {task_type}", "planned_tool": null, '
                f'"final_answer": "mock_response_{task_type}", "confidence": 0.85}}'
            )
            return {
                "ok": True,
                "response": {"ok": True, "response": canned, "cost_credits": 0.0},
            }
        config = self._resolve_seq(config, self._route_counter, task_type or "default")
        return self._format_route_response(config)

    async def invoke_tool(self, server: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        self.invoke_calls.append((server, tool))
        key = f"{server}.{tool}"
        config = self.responses.get(key)
        if config is None:
            return {"ok": True, "response": {"ok": True}, "cost_credits": 0.0}
        config = self._resolve_seq(config, self._invoke_counter, key)
        return self._format_invoke_response(config)

    # ----- helpers --------------------------------------------------------

    def _resolve_seq(
        self, config: Any, counter: dict[str, int], key: str,
    ) -> dict[str, Any]:
        """Multi-call support: if config is list, pick by call index (clamped)."""
        if isinstance(config, list):
            idx = counter.get(key, 0)
            counter[key] = idx + 1
            return config[min(idx, len(config) - 1)]
        return config

    def _format_route_response(self, config: dict[str, Any]) -> dict[str, Any]:
        ok = bool(config.get("ok", True))
        resp = config.get("response", "")
        # If response is dict, JSON-encode for LLM text contract.
        if isinstance(resp, dict):
            resp = json.dumps(resp)
        return {
            "ok": ok,
            "response": {
                "ok": ok,
                "response": str(resp),
                "cost_credits": float(config.get("cost_credits", 0.0)),
                "provider": config.get("provider", "mock"),
                "model": config.get("model", "mock-model"),
            },
        }

    def _format_invoke_response(self, config: dict[str, Any]) -> dict[str, Any]:
        ok = bool(config.get("ok", True))
        inner = config.get("response", {"ok": ok})
        if not isinstance(inner, dict):
            inner = {"ok": ok, "raw": str(inner)}
        return {
            "ok": ok,
            "response": inner,
            "cost_credits": float(config.get("cost_credits", 0.0)),
        }


# ---------------------------------------------------------------------------
# Golden case loader — validates schema, fails collection loud on error.
# ---------------------------------------------------------------------------

def load_all_golden_cases() -> list[dict[str, Any]]:
    """Load + validate all YAML golden cases. Returns list of validated dicts."""
    if not GOLDEN_DIR.exists():
        return []
    cases: list[dict[str, Any]] = []
    errors: list[str] = []
    for yaml_file in sorted(GOLDEN_DIR.glob("*.yaml")):
        try:
            with open(yaml_file, encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            if not isinstance(raw, dict):
                errors.append(f"{yaml_file.name}: not a YAML dict")
                continue
            validated = GoldenCase(**raw)
            case_dict = validated.model_dump()
            case_dict["_file"] = yaml_file.name
            cases.append(case_dict)
        except (ValidationError, yaml.YAMLError) as exc:
            errors.append(f"{yaml_file.name}: {type(exc).__name__}: {exc}")
    if errors:
        raise RuntimeError(
            "Golden case schema validation failed:\n  " + "\n  ".join(errors)
        )
    return cases


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def golden_db_path() -> Path:
    """Per-test tmp SQLite DB with brain_runs schema applied."""
    tmp = Path(tempfile.mkdtemp(prefix="brain_golden_")) / "golden.db"
    mig_dir = Path(__file__).parent.parent / "migrations"
    base_sql = (mig_dir / "2026_06_brain_runs_decisions.sql").read_text(encoding="utf-8")
    owner_sql_path = mig_dir / "2026_06_brain_runs_owner_comment.sql"
    conn = sqlite3.connect(str(tmp))
    conn.executescript(base_sql)
    if owner_sql_path.exists():
        conn.executescript(owner_sql_path.read_text(encoding="utf-8"))
    conn.close()
    return tmp


@pytest.fixture
def brain_instance(golden_db_path: Path) -> Brain:
    """Fresh Brain instance with isolated tmp DB persistence."""
    reset_persistence()
    persistence = get_persistence(db_path=golden_db_path)
    brain = Brain(persistence=persistence)
    yield brain
    reset_persistence()


@pytest.fixture
def mock_dispatcher_factory():
    """Factory: build GoldenMockDispatcher with per-test YAML responses."""
    def _build(responses: dict[str, Any] | None = None) -> GoldenMockDispatcher:
        return GoldenMockDispatcher(responses)
    return _build
