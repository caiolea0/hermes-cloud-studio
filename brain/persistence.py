"""F.6.3 Brain memory persistence layer.

D1 Strategy: SYNC brain_runs (INSERT no inicio + UPDATE no final) + ASYNC brain_decisions
            (single writer queue consumer, fire-and-forget per state transition).

D2 Granularidade: 1 row brain_decisions por state transition (FSM trigger) + per ReAct iter.

D6 Error rows: TRUNCATED 2000 chars em rationale + Sentry capture_exception() FULL.

Constraints:
  - sqlite3.connect(check_same_thread=False) obrigatorio (async access multi-task).
  - Single asyncio.Lock para serializar writes (sqlite3 WAL multi-reader / 1-writer).
  - Single writer task drena queue de brain_decisions (evita lock contention spike).
  - JSON dumps truncated 2000 chars per col (preserves SQLite TEXT performance).

NÃO implementado F.6.3:
  - cron archive >90d → F.future scripts/archive_brain_runs.py (D5)
  - error column dedicada → embed em rationale (D6 + schema base 11 cols intacto)
  - aiosqlite — sqlite3 stdlib + lock async suficiente F.6.3 volume baseline

Cross-ref:
  .claude/PLAN.md § F.6.3 Decisões D1-D6 (commit 95f0548)
  migrations/2026_06_brain_runs_decisions.sql F.6.1 (schema 12+11 cols)
  brain/decide.py F.6.2 (hooks integration points)
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import traceback
import uuid
from pathlib import Path
from typing import Any

from .dispatch import sanitize

__all__ = ["BrainPersistence", "get_persistence", "TRUNCATE_LIMIT"]

log = logging.getLogger("brain.persistence")

# D6: TEXT truncate per col (SQLite TEXT performant; replay payload light).
TRUNCATE_LIMIT = 2000

# Default DB path (PC). VM uses ~/.hermes/data/command_center.db (set via env override).
_DEFAULT_DB = Path(__file__).resolve().parent.parent / "hermes_local.db"


def _trunc_json(value: Any) -> str:
    """Serialize value to JSON + truncate TRUNCATE_LIMIT chars. JSON-safe (sanitize done by caller)."""
    if value is None:
        return "{}"
    try:
        text = json.dumps(value, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(value)
    return text[:TRUNCATE_LIMIT]


def _trunc_text(text: str | None) -> str:
    if not text:
        return ""
    return str(text)[:TRUNCATE_LIMIT]


class BrainPersistence:
    """Async-safe sqlite3 wrapper para brain_runs + brain_decisions.

    Single shared instance per process (use get_persistence()) — single writer queue
    consumer task spawnado lazy no primeiro schedule_decision_async().

    SYNC writes (insert_run, update_run_final): await com self._lock.
    ASYNC writes (decisions): enqueue via schedule_decision_async() + drain via _writer_loop.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB
        # check_same_thread=False obrigatorio: async tasks rodam em event loop thread
        # mas connection accessed por multiple tasks via lock.
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        # WAL mode (mesmo da F.5.5) — multi-reader + 1 writer.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._lock = asyncio.Lock()
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._writer_task: asyncio.Task[None] | None = None

    # ----- SYNC writes (brain_runs) ---------------------------------------

    async def insert_run(
        self,
        run_id: str,
        intent: str,
        context: dict[str, Any],
        requester: str = "api",
        otel_trace_id: str | None = None,
    ) -> None:
        """Insert brain_runs row no inicio Brain.decide(). run_id reservado imediato."""
        ctx_sanitized = sanitize(context or {})
        async with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO brain_runs
                        (id, intent, context_json, requester, otel_trace_id)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        intent,
                        _trunc_json(ctx_sanitized),
                        requester,
                        otel_trace_id,
                    ),
                )
            except sqlite3.Error as exc:
                log.error("insert_run failed run_id=%s: %s", run_id, exc)
                self._report_sentry(exc, {"op": "insert_run", "run_id": run_id})
                raise

    async def update_run_final(
        self,
        run_id: str,
        final_state: str,
        final_result: dict[str, Any],
        total_latency_ms: int,
        total_cost_credits: float,
        confidence_score: float,
        owner_comment: str | None = None,
    ) -> None:
        """Update brain_runs final state (atomic per lock). Race-free com decisions writer.

        F.6.4: owner_comment opcional — quando final_state IN
        {'owner_approved','owner_rejected'} (resume_from_run_id), persiste comment 500 chars.
        """
        result_sanitized = sanitize(final_result or {})
        async with self._lock:
            try:
                if owner_comment is None:
                    self._conn.execute(
                        """
                        UPDATE brain_runs
                           SET finished_at = CURRENT_TIMESTAMP,
                               final_state = ?,
                               final_result = ?,
                               total_latency_ms = ?,
                               total_cost_credits = ?,
                               confidence_score = ?
                         WHERE id = ?
                        """,
                        (
                            final_state,
                            _trunc_json(result_sanitized),
                            int(total_latency_ms),
                            float(total_cost_credits),
                            float(confidence_score),
                            run_id,
                        ),
                    )
                else:
                    self._conn.execute(
                        """
                        UPDATE brain_runs
                           SET finished_at = CURRENT_TIMESTAMP,
                               final_state = ?,
                               final_result = ?,
                               total_latency_ms = ?,
                               total_cost_credits = ?,
                               confidence_score = ?,
                               owner_comment = ?
                         WHERE id = ?
                        """,
                        (
                            final_state,
                            _trunc_json(result_sanitized),
                            int(total_latency_ms),
                            float(total_cost_credits),
                            float(confidence_score),
                            _trunc_text(owner_comment)[:500],
                            run_id,
                        ),
                    )
            except sqlite3.Error as exc:
                log.error("update_run_final failed run_id=%s: %s", run_id, exc)
                self._report_sentry(exc, {"op": "update_run_final", "run_id": run_id})
                raise

    # ----- ASYNC writes (brain_decisions queue) ----------------------------

    def schedule_decision(
        self,
        run_id: str,
        sequence: int,
        state_from: str,
        state_to: str,
        tool_invoked: str | None = None,
        tool_args: dict[str, Any] | None = None,
        tool_result: dict[str, Any] | None = None,
        rationale: str = "",
        latency_ms: int = 0,
    ) -> None:
        """Enqueue decision INSERT (non-blocking). Single writer task drena."""
        try:
            self._queue.put_nowait(
                {
                    "run_id": run_id,
                    "sequence": sequence,
                    "state_from": state_from,
                    "state_to": state_to,
                    "tool_invoked": tool_invoked,
                    "tool_args": tool_args or {},
                    "tool_result": tool_result or {},
                    "rationale": rationale,
                    "latency_ms": latency_ms,
                }
            )
        except asyncio.QueueFull:
            # Bounded queue protection (F.future): drop oldest, log Sentry.
            log.warning("decision queue full run_id=%s seq=%d dropped", run_id, sequence)
        self._ensure_writer()

    def _ensure_writer(self) -> None:
        """Lazy spawn single writer task. Idempotent — checks task done()."""
        if self._writer_task is None or self._writer_task.done():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop — caller must invoke from async context.
                return
            self._writer_task = loop.create_task(self._writer_loop())

    async def _writer_loop(self) -> None:
        """Single consumer drain queue → INSERT brain_decisions. Resilient (Sentry on error, continue)."""
        while True:
            try:
                item = await self._queue.get()
            except asyncio.CancelledError:
                return
            try:
                args_sanitized = sanitize(item["tool_args"])
                result_sanitized = sanitize(item["tool_result"])
                async with self._lock:
                    self._conn.execute(
                        """
                        INSERT INTO brain_decisions
                            (id, run_id, sequence, state_from, state_to, tool_invoked,
                             tool_args_json, tool_result_json, rationale, latency_ms)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid.uuid4()),
                            item["run_id"],
                            int(item["sequence"]),
                            item["state_from"],
                            item["state_to"],
                            item.get("tool_invoked"),
                            _trunc_json(args_sanitized),
                            _trunc_json(result_sanitized),
                            _trunc_text(item["rationale"]),
                            int(item["latency_ms"]),
                        ),
                    )
            except Exception as exc:  # noqa: BLE001 — writer must not crash
                log.exception("decision writer INSERT failed run_id=%s", item.get("run_id"))
                self._report_sentry(exc, {"op": "writer_loop", "run_id": item.get("run_id")})
            finally:
                self._queue.task_done()

    async def drain(self, timeout: float = 5.0) -> bool:
        """Wait for queue drain (smoke / shutdown helper). Returns True if drained, False on timeout."""
        try:
            await asyncio.wait_for(self._queue.join(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    # ----- READS (replay support) -----------------------------------------

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Load brain_runs row by id. Returns None if not found."""
        async with self._lock:
            row = self._conn.execute(
                "SELECT * FROM brain_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return dict(row) if row else None

    async def get_decisions(self, run_id: str) -> list[dict[str, Any]]:
        """Load brain_decisions rows ordered by sequence ASC."""
        async with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM brain_decisions
                 WHERE run_id = ?
                 ORDER BY sequence ASC
                """,
                (run_id,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            try:
                d["tool_args"] = json.loads(d.get("tool_args_json") or "{}")
            except (json.JSONDecodeError, ValueError):
                d["tool_args"] = {}
            try:
                d["tool_result"] = json.loads(d.get("tool_result_json") or "{}")
            except (json.JSONDecodeError, ValueError):
                d["tool_result"] = {}
            out.append(d)
        return out

    async def list_runs(
        self,
        intent: str | None = None,
        limit: int = 50,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List recent runs (replay UI). Optional intent + status filter.

        F.6.4: status filter (e.g. 'requires_confirm') usado pelo drawer pra rehydrate
        pending owner-blocked runs ao montar (page reload survives).
        """
        limit = max(1, min(int(limit), 500))
        where: list[str] = []
        params: list[Any] = []
        if intent:
            where.append("intent = ?")
            params.append(intent)
        if status:
            where.append("final_state = ?")
            params.append(status)
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        params.append(limit)
        sql = (
            "SELECT id, intent, context_json, started_at, finished_at, final_state, "
            "       final_result, total_latency_ms, total_cost_credits, confidence_score, "
            "       requester, owner_comment "
            "  FROM brain_runs"
            f"{where_sql} "
            " ORDER BY started_at DESC LIMIT ?"
        )
        async with self._lock:
            rows = self._conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]

    async def load_run_for_resume(self, run_id: str) -> dict[str, Any] | None:
        """F.6.4 — load brain_runs row pre-resume_from_run_id.

        Returns same shape as get_run() (no async hydration). Reuses get_run().
        """
        return await self.get_run(run_id)

    # ----- helpers --------------------------------------------------------

    @staticmethod
    def _report_sentry(exc: Exception, extra: dict[str, Any]) -> None:
        """Send to Sentry via gateway wrapper. Fire-and-forget (NEVER raise)."""
        from core.sentry_via_gateway import capture_exception as _sentry_capture
        _sentry_capture(exc, requester="brain-core", extra=extra)


# ----- singleton accessor --------------------------------------------------

_INSTANCE: BrainPersistence | None = None


def get_persistence(db_path: Path | str | None = None) -> BrainPersistence:
    """Process-singleton accessor. Test code can pass db_path override (resets instance)."""
    global _INSTANCE
    if db_path is not None:
        _INSTANCE = BrainPersistence(db_path)
        return _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = BrainPersistence()
    return _INSTANCE


def reset_persistence() -> None:
    """Test helper — drop singleton (next get_persistence() creates fresh)."""
    global _INSTANCE
    _INSTANCE = None
