"""F.8.1 Observability core — perf metrics rolling 1h + cost aggregator helpers.

Cross-ref: .claude/PLAN.md § "F.8 Decisões Cristalizadas" D2/D3 + migration
2026_06_observability.sql.

Components:
- PerfMetricsCollector — in-memory rolling 1h window, asyncio-safe, hourly flush.
- perf_middleware — FastAPI middleware capturing per-request latency.
- cost_aggregate — JOIN mcp_calls F.5.7 × mcp_pricing for USD estimate.
- record_error_inbox — append errors_inbox triage entries (F.8.2 endpoint reads).

D2 REUSE mcp_calls (NÃO criar tabela llm_calls).
D3 JSON custom rolling (NÃO Prometheus exposition F.8.1).
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("hermes.observability")

# Optional Sentry capture (graceful absent in dev)
try:
    import sentry_sdk  # type: ignore
    _SENTRY_OK = True
except ImportError:
    sentry_sdk = None  # type: ignore
    _SENTRY_OK = False


# ---------------------------------------------------------------------------
# PerfMetricsCollector — rolling 1h window per endpoint (D3)
# ---------------------------------------------------------------------------

class PerfMetricsCollector:
    """Rolling 1h window per endpoint. Hourly flush -> perf_metrics table.

    asyncio.Lock prevents race condition between record() (per-request) and
    flush_to_db() (hourly task). maxlen cap on deque prevents unbounded growth
    if requests > 10k/hr per endpoint.
    """

    def __init__(self, window_seconds: int = 3600, service: str = "pc"):
        self.window = window_seconds
        self.service = service
        # endpoint -> deque[(monotonic_ts, latency_ms)]
        self.data: dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self._lock = asyncio.Lock()

    async def record(self, endpoint: str, latency_ms: float) -> None:
        async with self._lock:
            now = time.monotonic()
            buf = self.data[endpoint]
            buf.append((now, latency_ms))
            while buf and (now - buf[0][0]) > self.window:
                buf.popleft()

    def get_percentiles(self, endpoint: str) -> dict[str, Any]:
        latencies = [lat for _, lat in self.data.get(endpoint, [])]
        if not latencies:
            return {"count": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0,
                    "min": 0.0, "max": 0.0, "avg": 0.0}
        sorted_lat = sorted(latencies)
        n = len(sorted_lat)
        def pct(p: float) -> float:
            idx = min(n - 1, int(n * p))
            return float(sorted_lat[idx])
        return {
            "count": n,
            "p50": round(pct(0.50), 2),
            "p95": round(pct(0.95), 2),
            "p99": round(pct(0.99), 2),
            "min": round(sorted_lat[0], 2),
            "max": round(sorted_lat[-1], 2),
            "avg": round(sum(sorted_lat) / n, 2),
        }

    def get_all_endpoints(self) -> list[str]:
        return list(self.data.keys())

    async def flush_to_db(self, db_path: Path) -> int:
        """Hourly snapshot all endpoints -> perf_metrics.

        Returns rows inserted. Wraps DB errors in errors_inbox via record_error_inbox.
        """
        async with self._lock:
            endpoints = list(self.data.keys())
            snapshots = [(ep, self.get_percentiles(ep)) for ep in endpoints]

        if not snapshots:
            return 0

        now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
        try:
            conn = sqlite3.connect(str(db_path), timeout=5.0)
            try:
                conn.executemany(
                    """INSERT INTO perf_metrics
                       (endpoint, service, recorded_at, count, p50, p95, p99, min, max, avg)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        (ep, self.service, now_iso, s["count"],
                         s["p50"], s["p95"], s["p99"], s["min"], s["max"], s["avg"])
                        for ep, s in snapshots if s["count"] > 0
                    ],
                )
                conn.commit()
            finally:
                conn.close()
            return sum(1 for _, s in snapshots if s["count"] > 0)
        except Exception as exc:
            logger.error("perf flush_to_db failed: %s", exc)
            record_error_inbox(
                db_path,
                category="perf_flush_error",
                severity="warning",
                title="perf_metrics hourly flush failed",
                message=str(exc)[:1000],
            )
            if _SENTRY_OK and sentry_sdk is not None:
                sentry_sdk.capture_exception(exc)
            return 0


# Module-level singleton — server.py wires perf_middleware to this instance.
_COLLECTOR: PerfMetricsCollector = PerfMetricsCollector(service="pc")


def get_collector() -> PerfMetricsCollector:
    return _COLLECTOR


# ---------------------------------------------------------------------------
# FastAPI middleware (D3)
# ---------------------------------------------------------------------------

def install_perf_middleware(app, collector: Optional[PerfMetricsCollector] = None):
    """Register @app.middleware('http') capturing per-request latency.

    Owner adds via `install_perf_middleware(app)` after FastAPI() creation,
    BEFORE auth_middleware so even 401 responses get timed.
    """
    coll = collector or _COLLECTOR

    @app.middleware("http")
    async def _perf_middleware(request, call_next):
        start = time.monotonic()
        try:
            response = await call_next(request)
            return response
        finally:
            latency_ms = (time.monotonic() - start) * 1000.0
            endpoint = f"{request.method} {request.url.path}"
            try:
                await coll.record(endpoint, latency_ms)
            except Exception as exc:
                logger.debug("perf record failed: %s", exc)

    return _perf_middleware


async def perf_flush_loop(db_path: Path, interval_seconds: int = 3600):
    """Background task — flush rolling buffer hourly. Spawn in lifespan."""
    logger.info("perf_flush_loop started interval=%ds db=%s", interval_seconds, db_path)
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            inserted = await _COLLECTOR.flush_to_db(db_path)
            logger.info("perf_metrics hourly flush: %d rows inserted", inserted)
        except asyncio.CancelledError:
            logger.info("perf_flush_loop cancelled")
            raise
        except Exception as exc:
            logger.error("perf_flush_loop iteration error: %s", exc)
            if _SENTRY_OK and sentry_sdk is not None:
                sentry_sdk.capture_exception(exc)


# ---------------------------------------------------------------------------
# Cost aggregator (D2 — REUSE mcp_calls × mcp_pricing JOIN)
# ---------------------------------------------------------------------------

_RANGE_INTERVALS = {
    "24h": "-1 day",
    "7d":  "-7 days",
    "30d": "-30 days",
}


def cost_aggregate(
    db_path: Path,
    range_key: str = "24h",
    group_by: str = "provider",
) -> dict[str, Any]:
    """Aggregate mcp_calls × mcp_pricing for /api/observability/costs.

    Args:
        db_path: SQLite DB path (PC hermes_local.db or VM command_center.db).
        range_key: '24h' | '7d' | '30d'.
        group_by: 'provider' | 'model' | 'requester' | 'server'.

    Returns dict {period, range, group_by, items[], total_*}.

    Items contain: group_key, call_count, total_tokens_in/out, total_cost_credits,
    total_cost_usd (JOIN mcp_pricing.cost_per_credit_usd COALESCE 0).

    Empty result if mcp_calls absent (graceful — gateway F.5.3 may not yet
    populate cost cols).
    """
    interval = _RANGE_INTERVALS.get(range_key, "-1 day")
    valid_group = {"provider", "model", "requester", "server"}
    group_col = group_by if group_by in valid_group else "provider"

    if not db_path.exists():
        return {"range": range_key, "group_by": group_col, "items": [],
                "note": f"DB not found: {db_path}"}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        existing = {
            r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "mcp_calls" not in existing:
            return {"range": range_key, "group_by": group_col, "items": [],
                    "note": "mcp_calls missing — apply F.5.3 migrations"}

        # COALESCE NULL -> 0 (provider/model cols may be NULL pre-F.5.7 wiring).
        # JOIN mcp_pricing on model_id; missing model = 0 USD.
        sql = f"""
            SELECT
                COALESCE(c.{group_col}, 'unknown') AS group_key,
                COUNT(*) AS call_count,
                COALESCE(SUM(c.tokens_in), 0) AS total_tokens_in,
                COALESCE(SUM(c.tokens_out), 0) AS total_tokens_out,
                ROUND(COALESCE(SUM(c.cost_credits), 0), 4) AS total_cost_credits,
                ROUND(
                    COALESCE(SUM(
                        c.cost_credits * COALESCE(p.cost_per_credit_usd, 0)
                        + (c.tokens_in  / 1000.0) * COALESCE(p.cost_per_1k_tokens_in_usd,  0)
                        + (c.tokens_out / 1000.0) * COALESCE(p.cost_per_1k_tokens_out_usd, 0)
                    ), 0),
                    6
                ) AS total_cost_usd,
                ROUND(AVG(c.duration_ms), 1) AS avg_duration_ms,
                SUM(CASE WHEN c.error IS NOT NULL THEN 1 ELSE 0 END) AS error_count,
                MAX(c.created_at) AS last_call
            FROM mcp_calls c
            LEFT JOIN mcp_pricing p ON p.model_id = c.model
            WHERE c.created_at > datetime('now', ?)
            GROUP BY group_key
            ORDER BY total_cost_credits DESC, call_count DESC
        """
        rows = [dict(r) for r in conn.execute(sql, [interval]).fetchall()]

        totals = {
            "total_calls":  sum(r["call_count"] for r in rows),
            "total_tokens_in":  sum(r["total_tokens_in"] for r in rows),
            "total_tokens_out": sum(r["total_tokens_out"] for r in rows),
            "total_cost_credits": round(sum(r["total_cost_credits"] for r in rows), 4),
            "total_cost_usd":     round(sum(r["total_cost_usd"] for r in rows), 6),
            "error_count": sum(r["error_count"] for r in rows),
        }
        return {
            "range": range_key,
            "group_by": group_col,
            "items": rows,
            "totals": totals,
        }
    finally:
        conn.close()


def explain_cost_query_plan(db_path: Path) -> dict[str, Any]:
    """Debug helper: EXPLAIN QUERY PLAN for cost aggregate.

    Used by smoke tests + reviewer dim 13 (idx usage). Surfaces whether SQLite
    uses idx_mcp_calls_* (created F.5.3/F.5.7) vs full SCAN.
    """
    if not db_path.exists():
        return {"plan": "DB not found"}
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            """EXPLAIN QUERY PLAN
               SELECT c.provider, SUM(c.cost_credits)
               FROM mcp_calls c
               LEFT JOIN mcp_pricing p ON p.model_id = c.model
               WHERE c.created_at > datetime('now', '-1 day')
               GROUP BY c.provider"""
        ).fetchall()
        plan_lines = [str(r[-1]) for r in rows]
        uses_idx = any("idx_" in line for line in plan_lines)
        return {"plan": plan_lines, "uses_index": uses_idx}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Errors inbox helper (F.8.2 endpoint reads — F.8.1 producers write)
# ---------------------------------------------------------------------------

def record_error_inbox(
    db_path: Path,
    *,
    category: str,
    severity: str = "warning",
    title: str,
    message: Optional[str] = None,
    stack_trace: Optional[str] = None,
    sentry_issue_id: Optional[str] = None,
    metadata_json: Optional[str] = None,
) -> Optional[str]:
    """Insert errors_inbox row. Categories per migration:
       mcp_bypass | brain_safety_gate | validation_phase_fail
       | nim_polling_error | perf_flush_error.

    Returns inserted id or None on failure (never raises — defesa-em-profundidade).
    """
    if not db_path.exists():
        return None
    eid = str(uuid.uuid4())
    try:
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        try:
            conn.execute(
                """INSERT INTO errors_inbox
                   (id, category, severity, title, message, stack_trace,
                    sentry_issue_id, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (eid, category, severity, title,
                 (message or "")[:4000],
                 (stack_trace or "")[:2000],
                 sentry_issue_id,
                 metadata_json),
            )
            conn.commit()
            return eid
        finally:
            conn.close()
    except Exception as exc:
        logger.error("record_error_inbox failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# NIM credit balance (D7) — reads existing nim_credit_history F.5.7 schema
# ---------------------------------------------------------------------------

def get_latest_nim_balance(db_path: Path) -> dict[str, Any]:
    """Read nim_credit_history latest row. Schema F.5.7:
       (balance_credits, free_rpm_window_count, recorded_at, source)."""
    if not db_path.exists():
        return {"ok": False, "error": "DB not found"}
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='nim_credit_history'"
        ).fetchone()
        if not existing:
            return {"ok": False, "error": "nim_credit_history missing — apply F.5.7"}
        row = conn.execute(
            "SELECT balance_credits, free_rpm_window_count, recorded_at, source "
            "FROM nim_credit_history ORDER BY recorded_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return {"ok": True, "balance_credits": None,
                    "note": "no NIM polling rows yet (cron not run)"}
        balance = float(row["balance_credits"])
        return {
            "ok": True,
            "balance_credits": balance,
            "free_rpm_window_count": row["free_rpm_window_count"],
            "recorded_at": row["recorded_at"],
            "source": row["source"],
            "warning":  balance < 1000,
            "critical": balance < 200,
        }
    finally:
        conn.close()
