"""F.8.1c — Observability API endpoints (4 endpoints + 1 helper).

Cross-ref: .claude/PLAN.md § "F.8 Decisões Cristalizadas" D2/D7/D8 + F.8.2 PREP
(errors + decisions endpoints STUB explicit — F.8.2 implementa real Sentry MCP
query + brain_runs/brain_decisions traversal).

Endpoints:
- GET /api/observability/costs?range=24h|7d|30d&group_by=provider|model|...
                              &format=json|csv  (D2 + D8 — REUSE mcp_calls JOIN)
- GET /api/observability/perf?endpoint=&range=24h
                              (D3 — live PerfMetricsCollector OR perf_metrics history)
- GET /api/observability/credits  (D7 — latest nim_credit_history row)
- GET /api/observability/errors?status=open|resolved  (F.8.2 STUB — schema ready)
- GET /api/observability/decisions?context_id=  (F.8.2 STUB — schema ready)
"""
from __future__ import annotations

import csv
import io
import sqlite3
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, PlainTextResponse

from core.observability import (
    cost_aggregate,
    explain_cost_query_plan,
    get_collector,
    get_latest_nim_balance,
)
from core.state import DB_PATH

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
# GET /api/observability/decisions — F.8.2 STUB
# ---------------------------------------------------------------------------

@router.get("/decisions")
async def get_decisions(
    run_id: Optional[str] = Query(None, description="specific brain_runs.id"),
    intent: Optional[str] = Query(None, description="filter intent"),
    limit: int = Query(50, ge=1, le=500),
):
    """⚠️ F.8.2 STUB: returns brain_runs latest list. F.8.2 implementa full
    audit trail with brain_decisions[] traversal + replay + filters."""
    if not DB_PATH.exists():
        return {"items": [], "note": f"DB not found: {DB_PATH}",
                "stub_label": "F.8.2_implements_full_audit_trail"}

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='brain_runs'"
        ).fetchone()
        if not existing:
            return {"items": [], "note": "brain_runs missing — apply F.6.1 migration",
                    "stub_label": "F.8.2_implements_full_audit_trail"}

        if run_id:
            row = conn.execute(
                """SELECT id, intent, started_at, finished_at, final_state,
                          total_latency_ms, total_cost_credits, confidence_score,
                          requester, owner_comment
                   FROM brain_runs WHERE id = ?""",
                (run_id,)
            ).fetchone()
            if not row:
                return {"items": [], "note": "run_not_found",
                        "stub_label": "F.8.2_implements_full_audit_trail"}
            return {"item": dict(row),
                    "stub_label": "F.8.2_implements_full_audit_trail"}

        params: list = []
        where = ""
        if intent:
            where = "WHERE intent = ?"
            params.append(intent)
        params.append(limit)
        rows = [dict(r) for r in conn.execute(
            f"""SELECT id, intent, started_at, finished_at, final_state,
                       total_latency_ms, confidence_score, requester
                FROM brain_runs
                {where}
                ORDER BY started_at DESC
                LIMIT ?""", params
        ).fetchall()]
        return {
            "items": rows,
            "filters": {"intent": intent, "limit": limit},
            "stub_label": "F.8.2_implements_full_audit_trail",
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Debug helper — reviewer dim 13 EXPLAIN PLAN smoke
# ---------------------------------------------------------------------------

@router.get("/_debug/explain_cost_plan")
async def debug_explain_cost_plan():
    """Owner-side smoke: EXPLAIN QUERY PLAN cost aggregate (reviewer dim 13)."""
    return explain_cost_query_plan(DB_PATH)
