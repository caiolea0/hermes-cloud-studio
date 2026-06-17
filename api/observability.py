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
# F.8.2 Errors HYBRID Sentry MCP + local errors_inbox (D1+D2+D3+D5)
# ---------------------------------------------------------------------------

_DEFAULT_CATEGORIES = ("mcp_bypass", "brain_safety_gate", "validation_phase_fail")
_ALLOWED_STATUS = {"open", "resolved", "wontfix"}
# D5 — Sentry MCP timeout cap (graceful fallback to local-only).
_SENTRY_TIMEOUT_SECS = 10.0

# Lazy gateway dispatcher (per-request would re-init httpx client; module-level reuse).
_DISPATCHER: GatewayDispatcher | None = None


def _get_dispatcher() -> GatewayDispatcher:
    global _DISPATCHER
    if _DISPATCHER is None:
        _DISPATCHER = GatewayDispatcher(timeout=_SENTRY_TIMEOUT_SECS)
    return _DISPATCHER


async def _query_sentry_issues(category: str, range_str: str) -> list[dict[str, Any]]:
    """D1 — Sentry MCP F.5.6 FILTER by category tag + severity level.

    Returns [] gracefully on timeout/connect_error/MCP-missing (preserves local-only
    fallback path). NEVER raises — defense-in-depth (errors UI must not crash).
    """
    stats_period = range_str if range_str in {"24h", "7d", "30d"} else "24h"
    args = {
        "level": "warning,error,fatal",          # D1 severity filter
        "query": f"tags[category]:{category}",   # D1 category filter via Sentry tags
        "statsPeriod": stats_period,
        "limit": 100,
    }
    try:
        resp = await _get_dispatcher().invoke_tool(
            server="sentry", tool="list_issues", args=args,
        )
    except Exception as exc:  # noqa: BLE001 — defensive boundary
        log.warning("sentry list_issues exception: %s", type(exc).__name__)
        return []
    if not resp.get("ok"):
        log.debug("sentry list_issues not_ok: %s", resp.get("error"))
        return []
    payload = resp.get("response") or {}
    if isinstance(payload, dict):
        issues = payload.get("issues") or payload.get("data") or []
    elif isinstance(payload, list):
        issues = payload
    else:
        issues = []
    return [i for i in issues if isinstance(i, dict)]


def _query_local_errors(
    db_path,
    category: str,
    range_str: str,
    status: str,
) -> list[dict[str, Any]]:
    """Local errors_inbox query aligned on category + status + time range."""
    interval = _RANGE_INTERVALS.get(range_str, "-1 day")
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='errors_inbox'"
        ).fetchone()
        if not existing:
            return []
        rows = conn.execute(
            """SELECT id, category, severity, title, message, sentry_issue_id,
                      status, resolved_by, resolved_at, metadata_json, created_at
               FROM errors_inbox
               WHERE category = ? AND status = ? AND created_at > datetime('now', ?)
               ORDER BY created_at DESC
               LIMIT 500""",
            (category, status, interval),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _merge_errors(
    sentry_items: list[dict[str, Any]],
    local_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge Sentry MCP issues + local errors_inbox rows.

    Dedup key: sentry_issue_id (when local row references same Sentry issue).
    Sentry-only items are tagged source='sentry'; local-only source='local';
    overlap source='both' (local resolution wins for status).
    """
    by_sentry_id: dict[str, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []

    for s in sentry_items:
        sid = str(s.get("id") or s.get("issue_id") or "")
        if not sid:
            continue
        s_norm = {
            "source": "sentry",
            "sentry_issue_id": sid,
            "title": s.get("title") or s.get("message") or "(no title)",
            "category": (s.get("tags") or {}).get("category") if isinstance(s.get("tags"), dict) else None,
            "severity": s.get("level") or s.get("severity") or "warning",
            "status": s.get("status") or "open",
            "created_at": s.get("lastSeen") or s.get("firstSeen") or s.get("created_at"),
            "count": s.get("count"),
            "permalink": s.get("permalink"),
        }
        by_sentry_id[sid] = s_norm
        out.append(s_norm)

    for loc in local_items:
        sid = loc.get("sentry_issue_id")
        if sid and str(sid) in by_sentry_id:
            existing = by_sentry_id[str(sid)]
            existing["source"] = "both"
            existing["local_id"] = loc["id"]
            existing["status"] = loc["status"]                  # local resolution wins
            existing["resolved_by"] = loc.get("resolved_by")
            existing["resolved_at"] = loc.get("resolved_at")
            existing["metadata_json"] = loc.get("metadata_json")
        else:
            out.append({
                "source": "local",
                "local_id": loc["id"],
                "sentry_issue_id": loc.get("sentry_issue_id"),
                "title": loc.get("title"),
                "message": loc.get("message"),
                "category": loc.get("category"),
                "severity": loc.get("severity"),
                "status": loc.get("status"),
                "resolved_by": loc.get("resolved_by"),
                "resolved_at": loc.get("resolved_at"),
                "metadata_json": loc.get("metadata_json"),
                "created_at": loc.get("created_at"),
            })

    out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return out


@router.get("/errors")
async def get_errors(
    range: str = Query("24h", description="D2 24h | 7d | 30d"),
    status: str = Query("open", description="open | resolved | wontfix"),
    category: Optional[str] = Query(None, description="filter single category (else 3 defaults)"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """F.8.2 REAL — Errors HYBRID Sentry MCP + local errors_inbox.

    D1 Sentry MCP filter level + tags category (graceful fallback local-only).
    D2 ?range=24h|7d|30d default 24h.
    D3 ?offset=&limit= per category (default 50 max 200) + X-Total-Count header.

    Returns items_by_category{cat -> {items, total, offset, limit}} + total_count.
    """
    if range not in _ALLOWED_RANGES:
        raise HTTPException(400, f"range must be one of {sorted(_ALLOWED_RANGES)}")
    if status not in _ALLOWED_STATUS:
        raise HTTPException(400, f"status must be one of {sorted(_ALLOWED_STATUS)}")

    categories = (category,) if category else _DEFAULT_CATEGORIES

    result: dict[str, Any] = {
        "period": range,
        "status_filter": status,
        "items_by_category": {},
        "total_count": 0,
        "sentry_available": True,
    }

    for cat in categories:
        sentry_items = await _query_sentry_issues(cat, range)
        if not sentry_items:
            result["sentry_available"] = False
        local_items = _query_local_errors(DB_PATH, cat, range, status)
        merged = _merge_errors(sentry_items, local_items)
        # Status filter applied consistently — Sentry items default to "open" (line 275)
        merged = [m for m in merged if m.get("status") == status]

        total = len(merged)
        paginated = merged[offset:offset + limit]
        result["items_by_category"][cat] = {
            "items": paginated,
            "total": total,
            "offset": offset,
            "limit": limit,
        }
        result["total_count"] += total

    return Response(
        content=json.dumps(result, default=str),
        media_type="application/json",
        headers={"X-Total-Count": str(result["total_count"])},
    )


# ---------------------------------------------------------------------------
# POST /api/observability/errors/{id}/resolve — F.8.2 D5 atomic + optimistic lock
# ---------------------------------------------------------------------------

class ResolveErrorRequest(BaseModel):
    """D5 payload — action + optional 500-char comment (sanitized server-side)."""
    action: str = Field(..., pattern="^(resolve|wontfix)$")
    comment: str = Field(default="", max_length=500)


@router.post("/errors/{error_id}/resolve")
async def resolve_error(error_id: str, req: ResolveErrorRequest):
    """F.8.2 D5 — atomic Sentry MCP resolve + local UPDATE optimistic lock 409.

    Flow:
      1. Load local errors_inbox row (404 if not_found).
      2. Optimistic lock: 409 if status != 'open' (idempotent re-check).
      3. Sanitize comment via brain.dispatch.sanitize (SENSITIVE_KEYS — defesa em
         profundidade vs Pydantic max_length already 500).
      4. If sentry_issue_id present: dispatch sentry.resolve_issue (timeout 10s).
         Fallback graceful: local UPDATE still proceeds + warning.
      5. Local UPDATE WHERE status='open' (atomic — race-free with other tabs).
    """
    if not DB_PATH.exists():
        raise HTTPException(503, "DB unavailable")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT id, status, sentry_issue_id FROM errors_inbox WHERE id = ?",
            (error_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "error_not_found")
        error = dict(row)

        if error["status"] != "open":
            raise HTTPException(409, f"already_{error['status']}")

        # Sanitize comment SENSITIVE_KEYS (pattern F.6.4 D2)
        sanitized = sanitize({"comment": req.comment or ""})
        safe_comment = str(sanitized.get("comment") or "")[:500]

        sentry_resolved = False
        sentry_warning: str | None = None
        if error.get("sentry_issue_id"):
            try:
                sresp = await _get_dispatcher().invoke_tool(
                    server="sentry",
                    tool="resolve_issue",
                    args={"issue_id": error["sentry_issue_id"]},
                )
                sentry_resolved = bool(sresp.get("ok"))
                if not sentry_resolved:
                    sentry_warning = "sentry_mcp_failed_fallback_local_only"
            except Exception as exc:  # noqa: BLE001
                sentry_warning = f"sentry_mcp_exception:{type(exc).__name__}"

        new_status = "resolved" if req.action == "resolve" else "wontfix"
        metadata = json.dumps({
            "comment": safe_comment,
            "sentry_resolved": sentry_resolved,
            "sentry_warning": sentry_warning,
        })
        resolved_at_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"

        # Optimistic lock — UPDATE WHERE status='open' atomic (rowcount=0 → race)
        cursor = conn.execute(
            """UPDATE errors_inbox
                  SET status = ?,
                      resolved_by = ?,
                      resolved_at = ?,
                      metadata_json = ?
                WHERE id = ? AND status = 'open'""",
            (new_status, "owner", resolved_at_iso, metadata, error_id),
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(409, "race_condition_status_changed")

        response: dict[str, Any] = {
            "ok": True,
            "error_id": error_id,
            "action": req.action,
            "new_status": new_status,
            "sentry_resolved": sentry_resolved,
            "resolved_at": resolved_at_iso,
        }
        if sentry_warning:
            response["warning"] = sentry_warning
        return response
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
# GET /api/observability/mcp-coverage-history — F.8.4 D2 JSON files glob
# ---------------------------------------------------------------------------

@router.get("/mcp-coverage-history")
async def get_mcp_coverage_history(
    months: int = Query(6, ge=1, le=24, description="Max months to return (1-24)"),
):
    """F.8.4 D2 — Read audit JSON snapshots from .claude/audits/mcp-coverage/ glob.

    Returns latest month first. No live DB query — reads F.5.5 cron audit files.
    Pattern: MCP-COVERAGE-YYYY-MM.json (sorted desc by filename = chronological desc).
    Graceful: missing dir OR malformed JSON → skip + warning (NÃO 500).
    """
    from pathlib import Path

    audit_dir = Path(__file__).parent.parent / ".claude" / "audits" / "mcp-coverage"

    if not audit_dir.exists():
        return {
            "months_requested": months,
            "months_found": 0,
            "history": [],
            "latest": None,
            "warning": "no_audit_dir",
        }

    json_files = sorted(audit_dir.glob("MCP-COVERAGE-*.json"), reverse=True)[:months]

    history: list[dict] = []
    for jf in json_files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            data["_file"] = jf.name
            history.append(data)
        except Exception as exc:  # noqa: BLE001
            log.warning("Skip malformed audit %s: %s", jf.name, exc)
            continue

    return {
        "months_requested": months,
        "months_found": len(history),
        "latest": history[0] if history else None,
        "history": history,
    }


# ---------------------------------------------------------------------------
# Debug helper — reviewer dim 13 EXPLAIN PLAN smoke
# ---------------------------------------------------------------------------

@router.get("/_debug/explain_cost_plan")
async def debug_explain_cost_plan():
    """Owner-side smoke: EXPLAIN QUERY PLAN cost aggregate (reviewer dim 13)."""
    return explain_cost_query_plan(DB_PATH)
