"""F.5.5 D5 — MCP coverage audit jobs status router (hermes_api_v2 wire-up).

Mirror endpoint do gateway `/api/mcp/coverage/jobs/{job_id}`. Runtime real
hoje vive em mcps/gateway/server.py (PIVOT F.5.3 — gateway source-of-truth
endpoints MCP). Este router fica reservado pra wire-up quando VM migrar
hermes_api.py LEGACY → hermes_api_v2.py.

Cross-process: gateway :55401 e hermes_api_v2 :8420 sao processos distintos
em runtime. `_AUDIT_JOBS` import-from-gateway eh module-level — dict
compartilha SOMENTE se ambos loaded mesmo Python interpreter (test harness
OR F.future merge). Em producao corrente, gateway endpoint eh authoritative.

Cross-ref: PLAN.md F.5.5 D5 + mcps/gateway/server.py _AUDIT_JOBS.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from mcps.gateway.server import _AUDIT_JOBS

router = APIRouter(prefix="/api/mcp", tags=["mcp-jobs"])


@router.get("/coverage/jobs/{job_id}")
async def mcp_coverage_job_status(job_id: str) -> dict[str, Any]:
    """Poll status audit async job. 404 jobs antigos pos-restart (in-memory)."""
    job = _AUDIT_JOBS.get(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"job not found: {job_id} (in-memory dict, pode ter expirado pos-restart)",
        )
    return job
