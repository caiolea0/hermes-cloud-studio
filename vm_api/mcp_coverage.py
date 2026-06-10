"""F.5.3 Commit 3 — MCP coverage endpoints (live query mcp_calls + tier classify).

Endpoints:
- GET  /api/mcp/coverage/latest  — live join mcp_registry × mcp_calls last 30d
                                    + tier classification real-time
- POST /api/mcp/coverage/publish — stub manual trigger F.5.5 audit cron mensal

OAuth Bearer required (oauth_bearer_check middleware em hermes_api_v2.py).

Cross-ref: PLAN.md F.5.3 D4 + .claude/MCP-ENFORCEMENT-STRATEGY.md sections 4.1+7.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from vm_core.state import DB_PATH, logger

router = APIRouter(prefix="/api/mcp", tags=["mcp-coverage"])


def _classify_tiers_realtime(call_rows: list[dict], registry_rows: list[dict]) -> dict:
    """Tier per server+tool:
    - active: last_call < 7d (alta atividade)
    - warning: 7d <= last_call < 30d (atividade caindo)
    - orphan: registered tools sem call last 30d (drift/zombie candidato)
    - registry_tier override: deprecated/quarantine/reserved preserved from mcp_registry
    """
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    call_map = {(r["server"], r["tool"]): r for r in call_rows}
    result = []

    for reg in registry_rows:
        try:
            tools = json.loads(reg.get("tools") or "[]")
        except (ValueError, TypeError):
            tools = []
        registry_tier = reg.get("tier", "active")
        for tool in tools:
            key = (reg["server"], tool)
            if key in call_map:
                r = call_map[key]
                # Parse last_call timestamp (SQLite TIMESTAMP DEFAULT CURRENT_TIMESTAMP returns ISO)
                try:
                    last_call_dt = datetime.fromisoformat(r["last_call"].replace(" ", "T"))
                except (ValueError, AttributeError):
                    last_call_dt = None
                if last_call_dt and last_call_dt > week_ago:
                    tier = "active"
                else:
                    tier = "warning"
                result.append({
                    "server": reg["server"],
                    "tool": tool,
                    "calls": r["calls"],
                    "avg_ms": r["avg_ms"],
                    "last_call": r["last_call"],
                    "errors": r["errors"],
                    "tier": tier,
                    "registry_tier": registry_tier,
                    "chapter_owner": reg.get("chapter_owner"),
                })
            else:
                # Orphan: tool registered but zero calls last 30d
                tier = "orphan" if registry_tier in ("active",) else registry_tier
                result.append({
                    "server": reg["server"],
                    "tool": tool,
                    "calls": 0,
                    "avg_ms": None,
                    "last_call": None,
                    "errors": 0,
                    "tier": tier,
                    "registry_tier": registry_tier,
                    "chapter_owner": reg.get("chapter_owner"),
                })

    summary = {
        "total_tools": len(result),
        "active": sum(1 for i in result if i["tier"] == "active"),
        "warning": sum(1 for i in result if i["tier"] == "warning"),
        "orphan": sum(1 for i in result if i["tier"] == "orphan"),
        "deprecated": sum(1 for i in result if i["registry_tier"] == "deprecated"),
        "quarantine": sum(1 for i in result if i["registry_tier"] == "quarantine"),
        "reserved": sum(1 for i in result if i["registry_tier"] == "reserved"),
    }
    return {"summary": summary, "items": result}


@router.get("/coverage/latest")
async def mcp_coverage_latest() -> dict[str, Any]:
    """Live query mcp_calls last 30d + tier classification real-time.

    Returns:
        {period_days, summary: {active, warning, orphan, deprecated, quarantine, reserved, total_tools},
         items: [{server, tool, calls, avg_ms, last_call, errors, tier, registry_tier, chapter_owner}]}
    """
    db_path = DB_PATH
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Detect tables (graceful degrade se migration ainda não aplicada)
        existing = {
            r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "mcp_calls" not in existing or "mcp_registry" not in existing:
            return {
                "period_days": 30,
                "summary": {"total_tools": 0, "active": 0, "warning": 0, "orphan": 0,
                            "deprecated": 0, "quarantine": 0, "reserved": 0},
                "items": [],
                "note": "mcp_registry/mcp_calls table missing — apply F.5.3 migrations",
            }

        call_rows = [
            dict(r) for r in conn.execute("""
                SELECT server, tool, COUNT(*) as calls,
                       ROUND(AVG(duration_ms), 1) as avg_ms,
                       MAX(created_at) as last_call,
                       SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as errors
                FROM mcp_calls
                WHERE created_at > datetime('now', '-30 days')
                GROUP BY server, tool
                ORDER BY calls DESC
            """).fetchall()
        ]
        registry_rows = [
            dict(r) for r in conn.execute(
                "SELECT server, tools, tier, chapter_owner FROM mcp_registry"
            ).fetchall()
        ]

        classification = _classify_tiers_realtime(call_rows, registry_rows)
        return {
            "period_days": 30,
            **classification,
        }
    finally:
        conn.close()


@router.post("/coverage/publish")
async def mcp_coverage_publish() -> JSONResponse:
    """Manual trigger F.5.5 audit cron mensal.

    F.5.3 returns 202 stub. F.5.5 entrega mcp_coverage_audit.py:
    - cron `0 9 15 * *` (dia 15 9h BRT)
    - 7 phases: fetch_gateway_inventory + fetch_otel_usage + classify_tools +
      render_markdown → .claude/audits/mcp-coverage/MCP-COVERAGE-{YYYY-MM}.md
    """
    logger.info("mcp_coverage_publish stub called (F.5.5 entrega cron)")
    return JSONResponse(
        status_code=202,
        content={
            "status": "accepted",
            "next_step": "F.5.5 implementa mcp_coverage_audit.py cron mensal dia 15 9h BRT",
            "output_path_template": ".claude/audits/mcp-coverage/MCP-COVERAGE-{YYYY-MM}.md",
        },
    )
