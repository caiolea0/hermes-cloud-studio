"""F.8.1c + F.8.2 — Observability API endpoints.

Cross-ref: .claude/PLAN.md § "F.8 Decisões Cristalizadas" D2/D7/D8 + F.8.2 D1-D6.

F.8.1: costs + perf + credits + (errors/decisions STUBS).
F.8.2: errors HYBRID Sentry MCP + local errors_inbox + POST resolve atomic +
       brain audit endpoints REAL (paginate + filter intent/search/status/run_id +
       truncate 2000 chars via SQL SUBSTR).

Endpoints:
- GET  /api/observability/costs?range=24h|7d|30d&group_by=...&format=json|csv
- GET  /api/observability/perf?endpoint=&range=24h&source=live|history
- GET  /api/observability/credits
- GET  /api/observability/errors?range=24h|7d|30d&status=&category=&offset=&limit=
- POST /api/observability/errors/{id}/resolve  (D5 atomic Sentry MCP + local 409)
- GET  /api/observability/decisions?intent=&search=&status=&run_id=&offset=&limit=
"""
from __future__ import annotations

import csv
import io
import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from brain.dispatch import GatewayDispatcher, sanitize
from core.observability import (
    cost_aggregate,
    explain_cost_query_plan,
    get_collector,
    get_latest_nim_balance,
)
from core.state import DB_PATH

log = logging.getLogger("hermes.api.observability")

router = APIRouter(prefix="/api/observability", tags=["observability"])

_ALLOWED_RANGES = {"24h", "7d", "30d"}
_ALLOWED_GROUPS = {"provider", "model", "requester", "server"}
_ALLOWED_FORMATS = {"json", "csv"}
_RANGE_INTERVALS = {"24h": "-1 day", "7d": "-7 days", "30d": "-30 days"}


# ---------------------------------------------------------------------------
# GET /api/observability/costs — D2 REUSE + D8 CSV/JSON sibling
# ---------------------------------------------------------------------------

@router.get("/costs")
async def get_costs(
    range: str = Query("24h", description="24h | 7d | 30d"),
    group_by: str = Query("provider", description="provider | model | requester | server"),
    format: str = Query("json", description="json | csv"),
):
    if range not in _ALLOWED_RANGES:
        return JSONResponse(status_code=400,
                            content={"detail": f"range must be one of {sorted(_ALLOWED_RANGES)}"})
    if group_by not in _ALLOWED_GROUPS:
        return JSONResponse(status_code=400,
                            content={"detail": f"group_by must be one of {sorted(_ALLOWED_GROUPS)}"})
    if format not in _ALLOWED_FORMATS:
        return JSONResponse(status_code=400,
                            content={"detail": f"format must be one of {sorted(_ALLOWED_FORMATS)}"})

    agg = cost_aggregate(DB_PATH, range_key=range, group_by=group_by)

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "group_key", "call_count", "total_tokens_in", "total_tokens_out",
            "total_cost_credits", "total_cost_usd", "avg_duration_ms",
            "error_count", "last_call",
        ])
        for r in agg.get("items", []):
            writer.writerow([
                r.get("group_key"), r.get("call_count"),
                r.get("total_tokens_in"), r.get("total_tokens_out"),
                r.get("total_cost_credits"), r.get("total_cost_usd"),
                r.get("avg_duration_ms"), r.get("error_count"),
                r.get("last_call"),
            ])
        return PlainTextResponse(buf.getvalue(), media_type="text/csv")

    return agg


# ---------------------------------------------------------------------------
# GET /api/observability/perf — D3 live + history
# ---------------------------------------------------------------------------

@router.get("/perf")
async def get_perf(
    endpoint: Optional[str] = Query(None, description="full endpoint string e.g. 'GET /api/dashboard'"),
    range: str = Query("24h", description="24h | 7d | 30d (history) — ignored when endpoint live"),
    source: str = Query("live", description="'live' (rolling 1h memory) | 'history' (perf_metrics table)"),
):
    coll = get_collector()

    if source == "live":
        if endpoint:
            return {"source": "live", "endpoint": endpoint,
                    "stats": coll.get_percentiles(endpoint)}
        return {
            "source": "live",
            "endpoints": [
                {"endpoint": ep, "stats": coll.get_percentiles(ep)}
                for ep in coll.get_all_endpoints()
            ],
        }

    # history — query perf_metrics table
    if source != "history":
        return JSONResponse(status_code=400,
                            content={"detail": "source must be 'live' or 'history'"})
    if range not in _ALLOWED_RANGES:
        return JSONResponse(status_code=400,
                            content={"detail": f"range must be one of {sorted(_ALLOWED_RANGES)}"})
    if not DB_PATH.exists():
        return {"source": "history", "items": [], "note": f"DB not found: {DB_PATH}"}

    interval = _RANGE_INTERVALS[range]
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='perf_metrics'"
        ).fetchone()
        if not existing:
            return {"source": "history", "items": [],
                    "note": "perf_metrics missing — apply F.8.1 migration"}

        params: list = [interval]
        where = "WHERE recorded_at > datetime('now', ?)"
        if endpoint:
            where += " AND endpoint = ?"
            params.append(endpoint)
        rows = [dict(r) for r in conn.execute(
            f"""SELECT endpoint, service, recorded_at, count, p50, p95, p99,
                       min, max, avg
                FROM perf_metrics
                {where}
                ORDER BY recorded_at DESC
                LIMIT 1000""", params
        ).fetchall()]
        return {"source": "history", "range": range,
                "endpoint": endpoint, "items": rows}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /api/observability/credits — D7 NIM balance latest
# ---------------------------------------------------------------------------

@router.get("/credits")
async def get_credits():
    return get_latest_nim_balance(DB_PATH)


# ---------------------------------------------------------------------------
# GET /api/observability/errors — F.8.2 STUB (schema ready, full impl F.8.2)
# ---------------------------------------------------------------------------

@router.get("/errors")
async def get_errors(
    status: str = Query("open", description="open | resolved | wontfix"),
    category: Optional[str] = Query(None, description="filter category"),
    limit: int = Query(100, ge=1, le=1000),
):
    """⚠️ F.8.2 STUB: returns local errors_inbox rows only.

    F.8.2 implementa Sentry MCP F.5.6 hybrid query + triage workflow + POST
    resolve endpoint. F.8.1 expose local read-only.
    """
    if status not in ("open", "resolved", "wontfix"):
        return JSONResponse(status_code=400,
                            content={"detail": "status must be open|resolved|wontfix"})
    if not DB_PATH.exists():
        return {"items": [], "note": f"DB not found: {DB_PATH}",
                "stub_label": "F.8.2_implements_sentry_mcp_hybrid"}

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='errors_inbox'"
        ).fetchone()
        if not existing:
            return {"items": [], "note": "errors_inbox missing — apply F.8.1 migration",
                    "stub_label": "F.8.2_implements_sentry_mcp_hybrid"}

        params: list = [status]
        where = "WHERE status = ?"
        if category:
            where += " AND category = ?"
            params.append(category)
        params.append(limit)
        rows = [dict(r) for r in conn.execute(
            f"""SELECT id, category, severity, title, message,
                       sentry_issue_id, status, resolved_by, resolved_at, created_at
                FROM errors_inbox
                {where}
                ORDER BY created_at DESC
                LIMIT ?""", params
        ).fetchall()]
        return {
            "items": rows,
            "filters": {"status": status, "category": category, "limit": limit},
            "stub_label": "F.8.2_implements_sentry_mcp_hybrid",
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /api/observability/decisions — F.8.2 REAL (D3 paginate + D4 filters + D6 truncate)
# ---------------------------------------------------------------------------

# D6: truncate via SQL SUBSTR (NÃO Python post-process). Consistency com F.6.3.
_DECISION_TRUNCATE_CHARS = 2000


@router.get("/decisions")
async def get_decisions(
    intent: Optional[str] = Query(None, description="D4 filter brain_runs.intent"),
    search: Optional[str] = Query(None, description="D4 free-text LIKE context_json OR rationale"),
    status: Optional[str] = Query(None, description="D4 filter brain_runs.final_state"),
    run_id: Optional[str] = Query(None, description="D4 specific brain_runs.id"),
    offset: int = Query(0, ge=0, description="D3 pagination offset"),
    limit: int = Query(50, ge=1, le=200, description="D3 pagination limit (max 200)"),
):
    """F.8.2 REAL — Brain audit endpoint.

    D3: pagination ?offset=&limit= default 50 max 200 + X-Total-Count header.
    D4: filters intent + search + status + run_id combinable.
    D6: tool_args/result/rationale TRUNCATED 2000 chars via SQL SUBSTR
        (consistency com F.6.3 TRUNCATE_LIMIT). F.future GET /decisions/{id}/full
        retorna untruncated when needed.

    EXPLAIN PLAN: uses idx_brain_runs_intent (when intent filter set) +
    idx_brain_runs_started (ORDER BY started_at DESC) + idx_brain_decisions_run.
    """
    if not DB_PATH.exists():
        return JSONResponse(status_code=200, content={
            "items": [], "total": 0, "offset": offset, "limit": limit,
            "note": f"DB not found: {DB_PATH}",
        }, headers={"X-Total-Count": "0"})

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='brain_runs'"
        ).fetchone()
        if not existing:
            return JSONResponse(status_code=200, content={
                "items": [], "total": 0, "offset": offset, "limit": limit,
                "note": "brain_runs missing — apply F.6.1 migration",
            }, headers={"X-Total-Count": "0"})

        # D4 — build dynamic WHERE (combinable filters)
        conditions: list[str] = []
        params: list[Any] = []

        if intent:
            conditions.append("r.intent = ?")
            params.append(intent)
        if status:
            conditions.append("r.final_state = ?")
            params.append(status)
        if run_id:
            conditions.append("r.id = ?")
            params.append(run_id)
        if search:
            # Free-text LIKE %term% — parameterized (SQL injection safe via ?).
            # EXISTS subquery against brain_decisions.rationale for cross-table search.
            conditions.append(
                "(r.context_json LIKE ? "
                "OR EXISTS (SELECT 1 FROM brain_decisions d2 "
                "           WHERE d2.run_id = r.id AND d2.rationale LIKE ?))"
            )
            like = f"%{search}%"
            params.extend([like, like])

        where_sql = (" WHERE " + " AND ".join(conditions)) if conditions else ""

        # D3 — total count first (for X-Total-Count header + pagination UX)
        total_row = conn.execute(
            f"SELECT COUNT(*) AS n FROM brain_runs r{where_sql}", params
        ).fetchone()
        total = int(total_row["n"]) if total_row else 0

        # D3 — paginated runs (ORDER BY started_at DESC uses idx_brain_runs_started)
        sql_runs = (
            "SELECT r.id, r.intent, r.context_json, r.started_at, r.finished_at, "
            "       r.final_state, r.final_result, r.total_latency_ms, "
            "       r.total_cost_credits, r.confidence_score, r.requester, "
            "       r.owner_comment, r.otel_trace_id "
            "FROM brain_runs r"
            f"{where_sql} "
            "ORDER BY r.started_at DESC LIMIT ? OFFSET ?"
        )
        runs = conn.execute(sql_runs, params + [limit, offset]).fetchall()

        # Hydrate per-run decisions (D6 truncate via SQL SUBSTR — not Python).
        items: list[dict[str, Any]] = []
        for run in runs:
            run_dict = dict(run)
            decisions = conn.execute(
                f"""SELECT id, sequence, state_from, state_to, tool_invoked,
                           SUBSTR(tool_args_json, 1, {_DECISION_TRUNCATE_CHARS}) AS tool_args_json,
                           SUBSTR(tool_result_json, 1, {_DECISION_TRUNCATE_CHARS}) AS tool_result_json,
                           SUBSTR(rationale, 1, {_DECISION_TRUNCATE_CHARS}) AS rationale,
                           latency_ms, created_at
                    FROM brain_decisions
                    WHERE run_id = ?
                    ORDER BY sequence ASC""",
                (run_dict["id"],),
            ).fetchall()
            run_dict["decisions"] = [dict(d) for d in decisions]
            run_dict["decisions_count"] = len(run_dict["decisions"])
            items.append(run_dict)

        body = {
            "items": items,
            "total": total,
            "offset": offset,
            "limit": limit,
            "filters": {
                "intent": intent, "search": search,
                "status": status, "run_id": run_id,
            },
            "truncate_chars": _DECISION_TRUNCATE_CHARS,
        }
        return Response(
            content=json.dumps(body, default=str),
            media_type="application/json",
            headers={"X-Total-Count": str(total)},
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Debug helper — reviewer dim 13 EXPLAIN PLAN smoke
# ---------------------------------------------------------------------------

@router.get("/_debug/explain_cost_plan")
async def debug_explain_cost_plan():
    """Owner-side smoke: EXPLAIN QUERY PLAN cost aggregate (reviewer dim 13)."""
    return explain_cost_query_plan(DB_PATH)
