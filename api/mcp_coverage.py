"""F.5.6f — MCP Gateway coverage proxy + local fallback (PC backend → UI).

UI /mcp/gateway READ-ONLY consumes este router pra renderizar:
- Gateway health badge (VM gateway :55401 alive + PC server alive)
- Tier summary (active/warning/orphan/deprecated/quarantine/reserved + drift)
- Tabela MCPs registry (server + tools + tier + calls 24h + avg ms + errors)
- Audit log tail (recent calls last 24h)

Decisão D3 cristalizada: zero write actions (toggle/quarantine = RBAC F.future).
Auto-refresh client-side 60s. Backend reuso F.5.3+F.5.5 endpoints (sem schema novo).

Data source strategy:
1. Try VM api :8420 proxy (vm_api/mcp_coverage.py). Works quando VM rodando
   hermes_api_v2 (F.future migration LEGACY→v2).
2. FALLBACK PC hermes_local.db query direto (mcp_registry + mcp_calls populated
   via seed_mcp_registry.py PC-side). UI sempre renderiza, sem hard dependency VM.

Cross-ref: PLAN.md F.5.6 D3 + vm_api/mcp_coverage.py (source) +
dashboard/components/mcp_gateway.js (consumer) + mcps/gateway/server.py classify_coverage.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter

from core.state import VM_API_URL
from vm_core.mcp_tiering import classify_coverage

router = APIRouter(prefix="/api/mcp", tags=["mcp-gateway-ui"])


def _query_local_coverage() -> dict[str, Any]:
    """FALLBACK PC hermes_local.db local query (mirror lógica vm_api/mcp_coverage.py).

    Sem dependência de hermes_api_v2 wire-up VM (atualmente LEGACY hermes_api.py runs).
    Replica _coverage_latest() shape de mcps/gateway/server.py.
    """
    db_path = Path(__file__).resolve().parent.parent / "hermes_local.db"
    empty_summary = {"total_tools": 0, "active": 0, "warning": 0, "orphan": 0,
                     "deprecated": 0, "quarantine": 0, "reserved": 0}
    if not db_path.exists():
        return {"period_days": 30, "summary": empty_summary, "items": [],
                "note": f"PC DB not found: {db_path}"}
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        existing = {
            r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "mcp_calls" not in existing or "mcp_registry" not in existing:
            return {"period_days": 30, "summary": empty_summary, "items": [],
                    "note": "mcp_registry/mcp_calls table missing — run scripts/seed_mcp_registry.py"}
        call_rows = [dict(r) for r in conn.execute("""
            SELECT server, tool, COUNT(*) as calls,
                   ROUND(AVG(duration_ms), 1) as avg_ms,
                   MAX(created_at) as last_call,
                   SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as errors
            FROM mcp_calls
            WHERE created_at > datetime('now', '-30 days')
            GROUP BY server, tool
            ORDER BY calls DESC
        """).fetchall()]
        registry_rows = [dict(r) for r in conn.execute(
            "SELECT server, tools, tier, chapter_owner FROM mcp_registry"
        ).fetchall()]
        classification = classify_coverage(call_rows, registry_rows)
        return {"period_days": 30, "source": "pc_local_db", **classification}
    finally:
        conn.close()


@router.get("/coverage/latest")
async def mcp_coverage_latest() -> dict:
    """Proxy GET /api/mcp/coverage/latest VM → PC UI com fallback local.

    Try VM api primeiro (vm_api/mcp_coverage.py). Se VM 404 (LEGACY hermes_api.py
    rodando) ou unreachable, fallback PC hermes_local.db query direto.
    Returns classify_coverage shape:
    {period_days, summary{by_tier+totals}, items[server,tool,calls,avg_ms,last_call,
    errors,tier,registry_tier,chapter_owner], source}.
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{VM_API_URL}/api/mcp/coverage/latest")
            if r.status_code == 200:
                data = r.json()
                data.setdefault("source", "vm_api_proxy")
                return data
    except Exception:
        pass  # noqa: VM unreachable — fallback PC local DB
    return _query_local_coverage()


@router.get("/gateway/health")
async def mcp_gateway_health() -> dict:
    """Probe gateway liveness via VM api proxy to gateway /health endpoint.

    VM api :8420 e gateway :55401 sao process distintos. PC reach VM api,
    VM api curls localhost gateway. Returns combined health badge data.
    """
    health = {"pc": {"ok": True, "ts": None},
              "vm_api": {"ok": False, "url": VM_API_URL},
              "gateway": {"ok": False, "version": None, "upstream_active": None}}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{VM_API_URL}/api/_ping")
            health["vm_api"]["ok"] = (r.status_code == 200)
    except Exception as exc:
        health["vm_api"]["error"] = str(exc)
    # Gateway health probe via VM api proxy (vm_api/gateway_proxy.py F.future)
    # Por ora: confia que se vm_api OK + coverage retorna shape, gateway OK
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{VM_API_URL}/api/mcp/coverage/latest")
            if r.status_code == 200:
                data = r.json()
                health["gateway"]["ok"] = "summary" in data and data.get("summary", {}).get("total_tools", 0) > 0
                health["gateway"]["upstream_active"] = data.get("summary", {}).get("active", 0)
    except Exception:
        pass  # noqa: gateway probe best-effort
    return health
