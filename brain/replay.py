"""F.6.3 Brain decision replay (D3 cristalizado — SHOW RECORDED, read-only).

F.6.1 STUB returned 501 not_implemented.
F.6.3 IMPLEMENTS REAL — load brain_runs + brain_decisions ordered by sequence ASC,
       reconstruct full ReAct trace + state transitions + final result.

D3: replay APENAS exibe recorded sequence — NÃO re-invoke tool calls (side effects
double send_outreach catastrofe + mcp_calls duplicates + LLM cost waste).
F.future mode='re_invoke' explicit flag para debug deterministic.

Output API consumed by:
  - api/brain.py GET /api/brain/runs/{run_id} (replay summary)
  - api/brain.py POST /api/brain/replay/{run_id} (full payload)
  - F.future UI dashboard tab (F.8 cost observability cross-ref)
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .persistence import get_persistence

__all__ = ["replay_run", "list_runs"]

log = logging.getLogger("brain.replay")


async def replay_run(run_id: str, mode: str = "show_recorded") -> dict[str, Any]:
    """F.6.3 REAL replay. Loads brain_runs row + brain_decisions ordered by sequence.

    Args:
        run_id: uuid4 string returned by Brain.decide().
        mode: 'show_recorded' (default, only mode F.6.3) — read-only.
              F.future 're_invoke' (debug) re-roda LLM + tools determinístico.

    Returns shape:
      {
        ok: bool,
        mode: str,
        run_id: str,
        run: dict | None,            # brain_runs row
        decisions: list[dict],       # brain_decisions ordered by sequence
        total_decisions: int,
        truncated: bool,             # True se run row has finished_at NULL (partial crash mid-flow)
        error?: str
      }
    """
    if mode != "show_recorded":
        return {
            "ok": False,
            "mode": mode,
            "run_id": run_id,
            "run": None,
            "decisions": [],
            "total_decisions": 0,
            "truncated": False,
            "error": f"mode '{mode}' not implemented F.6.3 (only 'show_recorded'). re_invoke F.future.",
        }

    persistence = get_persistence()

    try:
        run = await persistence.get_run(run_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("replay_run get_run failed run_id=%s", run_id)
        return {
            "ok": False,
            "mode": mode,
            "run_id": run_id,
            "run": None,
            "decisions": [],
            "total_decisions": 0,
            "truncated": False,
            "error": f"db_error:{type(exc).__name__}",
        }

    if not run:
        return {
            "ok": False,
            "mode": mode,
            "run_id": run_id,
            "run": None,
            "decisions": [],
            "total_decisions": 0,
            "truncated": False,
            "error": "run_not_found",
        }

    try:
        decisions = await persistence.get_decisions(run_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("replay_run get_decisions failed run_id=%s", run_id)
        decisions = []

    # Hydrate context_json + final_result JSON strings into dicts for client convenience.
    try:
        run["context"] = json.loads(run.get("context_json") or "{}")
    except (json.JSONDecodeError, ValueError):
        run["context"] = {}
    try:
        run["final_result"] = json.loads(run.get("final_result") or "{}") if run.get("final_result") else None
    except (json.JSONDecodeError, ValueError):
        run["final_result"] = None

    # Truncated flag: run started but finished_at NULL → partial crash mid-flow (D6 documented).
    truncated = run.get("finished_at") is None

    return {
        "ok": True,
        "mode": mode,
        "run_id": run_id,
        "run": run,
        "decisions": decisions,
        "total_decisions": len(decisions),
        "truncated": truncated,
    }


async def list_runs(intent: str | None = None, limit: int = 50) -> dict[str, Any]:
    """F.6.3 REAL list. Recent runs (replay UI). Optional intent filter."""
    persistence = get_persistence()
    try:
        runs = await persistence.list_runs(intent=intent, limit=limit)
    except Exception as exc:  # noqa: BLE001
        log.exception("list_runs failed intent=%s limit=%d", intent, limit)
        return {
            "ok": False,
            "filter_intent": intent,
            "limit": limit,
            "runs": [],
            "error": f"db_error:{type(exc).__name__}",
        }
    return {
        "ok": True,
        "filter_intent": intent,
        "limit": limit,
        "count": len(runs),
        "runs": runs,
    }
