"""F.6.2 Brain smoke — REAL dispatch via gateway OR OFFLINE_MODE deterministic.
F.6.3 extends — persistence + replay + agentmemory opt-in smokes.

Modes:
  HERMES_BRAIN_OFFLINE=1 (default)  -> MockDispatcher, deterministic, no network
  HERMES_BRAIN_OFFLINE=0            -> real GatewayDispatcher (requires gateway up + NIM key)

OFFLINE smoke validates:
  1. All 6 intents route through Brain.decide() correctly.
  2. Destructive intents (send_outreach) -> requires_confirm regardless of confidence.
  3. Utility intent (route_skill_run) -> no LLM call.
  4. Unknown intent -> status=error, FSM stays IDLE.
  5. Two Brain() instances independent (no shared FSM).
  6. ReAct multi-step + tool dispatch ordering.

F.6.3 PERSISTENCE smoke validates (always runs after OFFLINE):
  P1. Each Brain.decide() persists 1 brain_runs row.
  P2. Each Brain.decide() persists N brain_decisions rows (sequence 1..N ordered).
  P3. replay_run(run_id) returns ok=True with full run + decisions.
  P4. replay_run(bogus_uuid) returns ok=False err=run_not_found (no crash).
  P5. list_runs() returns recent persisted runs.
  P6. Sequential 20 concurrent runs — no sqlite3 lock contention (all persist).
  P7. INTENT_REGISTRY has agentmemory_save field per D4 (3 True + 3 False).

REAL smoke (HERMES_BRAIN_OFFLINE=0) validates:
  R1. classify task_type -> T1 NIM Free response real.
  R2. Brain handles dispatch tool failures gracefully (low_conf -> requires_confirm).

Run:
  python -m brain._smoke                       # OFFLINE deterministic (CI safe)
  HERMES_BRAIN_OFFLINE=0 python -m brain._smoke  # REAL gateway dispatch
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

from .decide import Brain
from .intents import INTENT_REGISTRY
from .persistence import get_persistence, reset_persistence
from .replay import list_runs, replay_run
from .safety import DESTRUCTIVE_ACTIONS
from .states import BrainState

OFFLINE_MODE = os.getenv("HERMES_BRAIN_OFFLINE", "1") != "0"


class _MockDispatcher:
    """Deterministic mock: emits canned LLM responses per intent task_type."""

    def __init__(self) -> None:
        self.route_calls: list[tuple[str, str]] = []
        self.invoke_calls: list[tuple[str, str]] = []

    async def route(self, task_type: str, prompt: str, **kw: Any) -> dict[str, Any]:
        self.route_calls.append((task_type, prompt[:80]))
        # Deterministic: emit JSON final_answer = "mock_response_<task_type>", conf=0.85
        # confidence 0.85 > 0.5 -> non-destructive intents complete; destructive still gate.
        canned = (
            f'{{"rationale": "mock {task_type}", "planned_tool": null, '
            f'"final_answer": "mock_response_{task_type}", "confidence": 0.85}}'
        )
        return {
            "ok": True,
            "response": {"ok": True, "response": canned, "cost_credits": 0.0},
        }

    async def invoke_tool(self, server: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        self.invoke_calls.append((server, tool))
        return {"ok": True, "response": {"ok": True}, "cost_credits": 0.0}


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}", file=sys.stderr)
        sys.exit(1)


async def _run_offline_smoke() -> list[str]:
    """OFFLINE deterministic — 6 intents + unknown + isolation."""
    passes: list[str] = []
    mock = _MockDispatcher()

    # Case 1-6: each registered intent yields a deterministic outcome.
    for intent_name, cfg in INTENT_REGISTRY.items():
        brain = Brain(dispatcher=mock)
        result = await brain.decide(intent_name, {"smoke": True, "id": intent_name})

        _assert(bool(result["run_id"]), f"{intent_name}: run_id missing")
        _assert(
            result["final_state"] == BrainState.IDLE.value,
            f"{intent_name}: final_state must be IDLE, got {result['final_state']}",
        )

        if cfg["destructive"] or intent_name in DESTRUCTIVE_ACTIONS:
            _assert(
                result["status"] == "requires_confirm",
                f"{intent_name}: destructive must require confirm, got {result['status']}",
            )
            _assert(result["requires_confirm"] is True, f"{intent_name}: requires_confirm flag")
            _assert(
                "confirm_reason" in result["result"],
                f"{intent_name}: confirm_reason missing",
            )
            passes.append(f"  [confirm-gate] {intent_name}: {result['result']['confirm_reason']}")
        elif cfg["task_type"] is None:
            # utility intent: status=completed, no LLM call
            _assert(
                result["status"] == "completed",
                f"{intent_name}: utility must complete, got {result['status']}",
            )
            _assert(
                result["result"]["status"] == "utility_no_llm",
                f"{intent_name}: react_status must be utility_no_llm",
            )
            passes.append(f"  [utility]      {intent_name}: no LLM call")
        else:
            _assert(
                result["status"] == "completed",
                f"{intent_name}: non-destructive must complete, got {result['status']}",
            )
            _assert(result["requires_confirm"] is False, f"{intent_name}: must NOT require confirm")
            _assert(
                result["result"].get("final_answer") == f"mock_response_{cfg['task_type']}",
                f"{intent_name}: mock final_answer mismatch",
            )
            passes.append(
                f"  [completed]    {intent_name}: task_type={cfg['task_type']} iter={result['result']['iterations']}"
            )

    # Case 7: unknown intent error-handling (no FSM crash).
    brain = Brain(dispatcher=mock)
    result = await brain.decide("intent_does_not_exist_xyz", {})
    _assert(result["status"] == "error", "unknown intent must return status='error'")
    _assert("error" in result["result"], "unknown intent must include error field")
    _assert(
        result["final_state"] == BrainState.IDLE.value,
        f"unknown intent must leave FSM at IDLE, got {result['final_state']}",
    )
    passes.append(f"  [error]        unknown_intent: {result['result']['error']}")

    # Case 8: independence — two Brain() instances do not share FSM state.
    brain_a = Brain(dispatcher=_MockDispatcher())
    brain_b = Brain(dispatcher=_MockDispatcher())
    res_a = await brain_a.decide("answer_owner", {"who": "a"})
    res_b = await brain_b.decide("send_outreach", {"who": "b"})
    _assert(res_a["status"] == "completed", "brain_a should complete")
    _assert(res_b["status"] == "requires_confirm", "brain_b should require confirm")
    _assert(res_a["run_id"] != res_b["run_id"], "run_ids must differ across instances")
    passes.append("  [isolation]    two Brain() instances independent")

    # Case 9: max_iter cap functional with looping mock
    class _LoopMock(_MockDispatcher):
        async def route(self, task_type: str, prompt: str, **kw: Any) -> dict[str, Any]:
            self.route_calls.append((task_type, prompt[:80]))
            # Always plan a tool, never final_answer -> forces max_iter
            return {
                "ok": True,
                "response": {
                    "ok": True,
                    "response": '{"rationale":"loop","planned_tool":{"server":"x","tool":"y","args":{}},"final_answer":null,"confidence":0.5}',
                    "cost_credits": 0.0,
                },
            }

    loop_mock = _LoopMock()
    brain_c = Brain(dispatcher=loop_mock)
    res_c = await brain_c.decide("answer_owner", {"loop": True})
    _assert(res_c["result"]["iterations"] == 5, f"max_iter cap 5, got {res_c['result']['iterations']}")
    _assert(res_c["result"]["status"] == "max_iterations_reached", f"got {res_c['result']['status']}")
    passes.append(f"  [max_iter]     cap=5 functional, react_status=max_iterations_reached")

    return passes


async def _run_real_smoke() -> list[str]:
    """REAL — Brain.decide() via real gateway dispatch."""
    passes: list[str] = []

    # Test A: classify task — known reliable T1 NIM Free
    brain = Brain()
    result = await brain.decide(
        "classify_prospect",
        {"name": "TechCorp", "category": "B2B SaaS", "website": "techcorp.com"},
    )
    _assert(result["status"] in ("completed", "requires_confirm", "error"), f"unexpected status {result['status']}")
    _assert(result["latency_ms"] > 0, "latency must be positive")
    _assert(result["result"].get("iterations", 0) >= 1, "must complete at least 1 iteration")
    react_status = result["result"].get("status")
    passes.append(
        f"  [real]    classify_prospect status={result['status']} react={react_status} "
        f"iter={result['result']['iterations']} conf={result['result'].get('confidence', 0)} "
        f"latency={result['latency_ms']}ms"
    )

    # Test B: utility intent — no LLM call even in REAL mode
    brain_b = Brain()
    result_b = await brain_b.decide("route_skill_run", {"skill": "test"})
    _assert(result_b["status"] == "completed", f"utility must complete, got {result_b['status']}")
    _assert(result_b["result"]["status"] == "utility_no_llm", "react_status must be utility_no_llm")
    passes.append(f"  [real]    route_skill_run utility no_llm latency={result_b['latency_ms']}ms")

    # Test C: destructive intent always requires_confirm
    brain_c = Brain()
    result_c = await brain_c.decide("send_outreach", {"prospect_id": "test"})
    _assert(result_c["status"] == "requires_confirm", f"destructive must require confirm")
    _assert(
        "destructive" in result_c["result"].get("confirm_reason", "").lower()
        or "low_confidence" in result_c["result"].get("confirm_reason", "").lower(),
        "confirm_reason must indicate destructive or low_confidence",
    )
    passes.append(f"  [real]    send_outreach destructive {result_c['result']['confirm_reason']}")

    return passes


async def _run_persistence_smoke() -> list[str]:
    """F.6.3 — validate persistence + replay + agentmemory field.

    Uses a per-smoke isolated DB (tmp file) so smoke is hermetic.
    """
    import tempfile

    # Ensure brain_runs + brain_decisions schema applied to tmp DB.
    tmp_db = Path(tempfile.mkdtemp(prefix="brain_smoke_")) / "smoke.db"
    mig_dir = Path(__file__).resolve().parent.parent / "migrations"
    schema_path = mig_dir / "2026_06_brain_runs_decisions.sql"
    # F.6.4: apply owner_comment ALTER too (list_runs SELECT now includes owner_comment)
    owner_comment_path = mig_dir / "2026_06_brain_runs_owner_comment.sql"
    conn = sqlite3.connect(str(tmp_db))
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    if owner_comment_path.exists():
        conn.executescript(owner_comment_path.read_text(encoding="utf-8"))
    conn.close()

    # Reset singleton then point persistence to tmp DB.
    reset_persistence()
    persistence = get_persistence(db_path=tmp_db)

    passes: list[str] = []
    mock = _MockDispatcher()

    # P7: INTENT_REGISTRY agentmemory_save field structure (D4).
    am_true = [n for n, c in INTENT_REGISTRY.items() if c.get("agentmemory_save")]
    am_false = [n for n, c in INTENT_REGISTRY.items() if not c.get("agentmemory_save")]
    _assert(len(am_true) == 3, f"D4 expected 3 True, got {len(am_true)}: {am_true}")
    _assert(len(am_false) == 3, f"D4 expected 3 False, got {len(am_false)}: {am_false}")
    _assert(set(am_true) == {"answer_owner", "synth_skill", "classify_prospect"}, f"D4 True set mismatch: {am_true}")
    passes.append(f"  [D4]           agentmemory_save = {sorted(am_true)} True / {sorted(am_false)} False")

    # P1 + P2: persistence per Brain.decide() invocation.
    brain = Brain(dispatcher=mock, persistence=persistence)
    res = await brain.decide("answer_owner", {"smoke": "P1"})
    run_id = res["run_id"]
    # Drain async writer queue.
    drained = await persistence.drain(timeout=3.0)
    _assert(drained, "P2 decision writer must drain within 3s")

    run_row = await persistence.get_run(run_id)
    _assert(run_row is not None, f"P1 brain_runs row missing for run_id={run_id}")
    _assert(run_row["intent"] == "answer_owner", f"P1 intent mismatch: {run_row['intent']}")
    _assert(run_row["final_state"] == "completed", f"P1 final_state mismatch: {run_row['final_state']}")
    _assert(run_row["finished_at"] is not None, "P1 finished_at must be set")
    passes.append(f"  [P1 brain_runs] row persisted run_id={run_id[:8]} final_state={run_row['final_state']}")

    decisions = await persistence.get_decisions(run_id)
    _assert(len(decisions) >= 6, f"P2 expected >=6 decisions (full flow), got {len(decisions)}")
    # Sequence ascending check
    seqs = [d["sequence"] for d in decisions]
    _assert(seqs == sorted(seqs), f"P2 decisions must be sequence ordered, got {seqs}")
    _assert(decisions[0]["state_from"] == "IDLE" and decisions[0]["state_to"] == "CLASSIFY",
            f"P2 first transition wrong: {decisions[0]}")
    _assert(decisions[-1]["state_to"] == "IDLE", f"P2 final state must be IDLE, got {decisions[-1]['state_to']}")
    passes.append(f"  [P2 decisions]  N={len(decisions)} seq=1..{seqs[-1]} ordered IDLE->...->IDLE")

    # P3: replay_run real
    replay = await replay_run(run_id)
    _assert(replay["ok"], f"P3 replay must return ok=True, got {replay.get('error')}")
    _assert(replay["total_decisions"] == len(decisions), "P3 replay decisions count mismatch")
    _assert(replay["truncated"] is False, "P3 truncated must be False for completed run")
    _assert(replay["run"]["intent"] == "answer_owner", "P3 replay intent mismatch")
    passes.append(f"  [P3 replay]     show_recorded ok total_decisions={replay['total_decisions']} truncated=False")

    # P4: run_not_found graceful
    bogus = "00000000-0000-0000-0000-000000000000"
    nf = await replay_run(bogus)
    _assert(nf["ok"] is False, "P4 not_found must return ok=False")
    _assert(nf["error"] == "run_not_found", f"P4 err string mismatch: {nf['error']}")
    passes.append(f"  [P4 not_found]  ok=False err=run_not_found (no crash)")

    # P5: list_runs returns recent
    lst = await list_runs(limit=10)
    _assert(lst["ok"], "P5 list_runs must return ok=True")
    _assert(lst["count"] >= 1, f"P5 list_runs count must be >=1, got {lst['count']}")
    passes.append(f"  [P5 list_runs]  ok count={lst['count']}")

    # P6: 20 concurrent runs — lock contention stress.
    async def _one(idx: int) -> str:
        b = Brain(dispatcher=_MockDispatcher(), persistence=persistence)
        r = await b.decide("classify_prospect", {"i": idx})
        return r["run_id"]

    run_ids = await asyncio.gather(*[_one(i) for i in range(20)])
    drained20 = await persistence.drain(timeout=10.0)
    _assert(drained20, "P6 concurrent drain must complete within 10s")
    persisted_count = 0
    for rid in run_ids:
        if await persistence.get_run(rid):
            persisted_count += 1
    _assert(persisted_count == 20, f"P6 expected 20 persisted runs, got {persisted_count}")
    passes.append(f"  [P6 concurrent] 20 runs persisted, drain ok, zero lock contention")

    # Cleanup tmp DB singleton (don't pollute real hermes_local.db on next tests).
    reset_persistence()

    return passes


async def _run_confirm_smoke() -> list[str]:
    """F.6.4 — validate confirm endpoint resume + owner_comment + idempotency.

    Uses tmp DB; tests:
      P8 approve flow: send_outreach -> requires_confirm -> resume approved
                       -> final_state=owner_approved + comment persisted
      P9 deny flow:    send_outreach -> requires_confirm -> resume denied
                       -> final_state=owner_rejected + comment persisted
      P10 idempotency: resume already-resolved run -> not_awaiting_confirm
      P11 missing run: resume non-existent run_id -> run_not_found
    """
    import sqlite3
    import tempfile
    from pathlib import Path

    from brain.decide import Brain
    from brain.persistence import get_persistence, reset_persistence

    passes: list[str] = []
    tmp = Path(tempfile.gettempdir()) / "hermes_brain_smoke_f64_confirm.db"
    if tmp.exists():
        tmp.unlink()
    # Apply both migrations (base + owner_comment) to tmp DB
    base_sql = (Path(__file__).resolve().parent.parent / "migrations" / "2026_06_brain_runs_decisions.sql").read_text()
    own_sql = (Path(__file__).resolve().parent.parent / "migrations" / "2026_06_brain_runs_owner_comment.sql").read_text()
    c = sqlite3.connect(str(tmp))
    c.executescript(base_sql)
    c.executescript(own_sql)
    c.commit()
    c.close()

    reset_persistence()
    get_persistence(tmp)

    # P8 approve flow
    b = Brain()
    r = await b.decide("send_outreach", {"prospect_id": "smoke-p8", "name": "P8"})
    rid_approve = r["run_id"]
    _assert(r["requires_confirm"] is True, "P8 expected requires_confirm=True for send_outreach")
    res_a = await b.resume_from_run_id(rid_approve, approved=True, comment="P8 approve smoke")
    _assert(res_a.get("ok") is True, f"P8 resume approve ok expected True, got {res_a}")
    _assert(res_a.get("final_state") == "owner_approved", f"P8 expected owner_approved got {res_a.get('final_state')}")
    # Verify DB row
    c = sqlite3.connect(str(tmp))
    row = c.execute("SELECT final_state, owner_comment FROM brain_runs WHERE id = ?", (rid_approve,)).fetchone()
    c.close()
    _assert(row[0] == "owner_approved", f"P8 DB final_state mismatch: {row[0]}")
    _assert("P8 approve smoke" in (row[1] or ""), f"P8 owner_comment not persisted: {row[1]!r}")
    passes.append("  [P8 approve flow] requires_confirm -> resume approved -> owner_approved + comment persisted")

    # P9 deny flow
    r2 = await b.decide("send_outreach", {"prospect_id": "smoke-p9"})
    rid_deny = r2["run_id"]
    res_d = await b.resume_from_run_id(rid_deny, approved=False, comment="P9 deny: wrong ICP")
    _assert(res_d.get("final_state") == "owner_rejected", f"P9 expected owner_rejected got {res_d.get('final_state')}")
    c = sqlite3.connect(str(tmp))
    row2 = c.execute("SELECT final_state, owner_comment FROM brain_runs WHERE id = ?", (rid_deny,)).fetchone()
    c.close()
    _assert(row2[0] == "owner_rejected", f"P9 DB final_state mismatch: {row2[0]}")
    _assert("P9 deny" in (row2[1] or ""), f"P9 owner_comment not persisted: {row2[1]!r}")
    passes.append("  [P9 deny flow] requires_confirm -> resume denied -> owner_rejected + comment persisted")

    # P10 idempotency: second resume on already-resolved run
    res_dup = await b.resume_from_run_id(rid_approve, approved=True, comment="should fail")
    _assert(res_dup.get("ok") is False, "P10 expected ok=False on already-resolved run")
    _assert(res_dup.get("error") == "not_awaiting_confirm", f"P10 expected not_awaiting_confirm got {res_dup.get('error')}")
    passes.append("  [P10 idempotency] resume already-resolved -> not_awaiting_confirm (409 surface)")

    # P11 run_not_found
    res_404 = await b.resume_from_run_id("non-existent-uuid-zz", approved=True)
    _assert(res_404.get("ok") is False, "P11 expected ok=False on missing run")
    _assert(res_404.get("error") == "run_not_found", f"P11 expected run_not_found got {res_404.get('error')}")
    passes.append("  [P11 run_not_found] non-existent run_id -> run_not_found (404 surface)")

    reset_persistence()
    return passes


async def _run_smoke() -> None:
    if OFFLINE_MODE:
        print("F.6.3 BRAIN SMOKE (OFFLINE_MODE — deterministic mock dispatcher)")
        passes = await _run_offline_smoke()
        print("F.6.3 PERSISTENCE SMOKE")
        passes_persist = await _run_persistence_smoke()
        print("F.6.4 CONFIRM SMOKE (approve/deny/idempotency/404)")
        passes_confirm = await _run_confirm_smoke()
        passes = passes + passes_persist + passes_confirm
    else:
        print("F.6.3 BRAIN SMOKE (REAL — gateway dispatch via NIM + Ollama)")
        passes = await _run_real_smoke()
        print("F.6.3 PERSISTENCE SMOKE (real DB)")
        passes_persist = await _run_persistence_smoke()
        print("F.6.4 CONFIRM SMOKE (real DB resume + owner_comment)")
        passes_confirm = await _run_confirm_smoke()
        passes = passes + passes_persist + passes_confirm

    print("ALL PASS:")
    for line in passes:
        print(line)
    print(f"\nTotal: {len(passes)} assertions.")


if __name__ == "__main__":
    asyncio.run(_run_smoke())
