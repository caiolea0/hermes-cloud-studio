"""Hermes Command Center v2 — VM API Bridge (post MERGED-011 split).

FastAPI server on the VM that serves prospect data, activity logs,
pipeline status, scraper control, and photo references to the dashboard.

Routes movidas para vm_api/routes.py. Helpers compartilhados em vm_core/state.py.
"""
import os
import secrets
import sys
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).parent))
from config import settings
from vm_core.state import (
    VM_AUTH_TOKEN,
    _audit_lock,
    _audit_state,
    get_db,
    init_db,
    logger,
    terminate_tracked_subprocs,
)
import time
from vm_api.routes import router as vm_router
from vm_api.mcp_coverage import router as mcp_coverage_router


async def _f5_strict_mcp_gate() -> None:
    """F.5.1 startup gate — STRICT_MODE FAIL-OPEN dev / FAIL-CLOSED prod.

    HERMES_STRICT_MCP=0 (default, dev local): warn-only se gateway down, continua.
    HERMES_STRICT_MCP=1 (VM prod): RuntimeError se gateway down, lifespan abort.

    Probes gateway /health endpoint (loopback bypass auth). 5s timeout.
    Cross-ref: mcps/gateway/server.py, MCP-ENFORCEMENT-STRATEGY.md s4.
    """
    strict = os.getenv("HERMES_STRICT_MCP") == "1"
    gateway_url = os.getenv("HERMES_GATEWAY_URL", "http://localhost:55401")
    health_url = f"{gateway_url.rstrip('/')}/health"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(health_url)
            r.raise_for_status()
            data = r.json()
            logger.info(
                "F.5.1 STRICT_MCP gate: gateway OK v%s upstream=%d strict=%s",
                data.get("version", "?"),
                data.get("upstream_count", 0),
                strict,
            )
    except Exception as exc:
        msg = f"F.5.1 STRICT_MCP gate: gateway probe failed at {health_url}: {exc}"
        if strict:
            logger.critical(msg + " — FAIL-CLOSED, aborting lifespan")
            raise RuntimeError(msg) from exc
        logger.warning(msg + " — FAIL-OPEN (dev mode, HERMES_STRICT_MCP=0)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await _f5_strict_mcp_gate()
    # Reconciliar campaign_runs: heartbeat parado > 5min = orphaned (MERGED-004)
    db = get_db()
    try:
        stale_cutoff = time.time() - 300
        cur = db.execute(
            "UPDATE campaign_runs SET status = 'orphaned' WHERE status = 'running' AND (last_heartbeat IS NULL OR last_heartbeat < ?)",
            (stale_cutoff,),
        )
        db.commit()
        if cur.rowcount:
            logger.warning("lifespan: %d campaign_runs marcadas orphaned", cur.rowcount)
    except Exception:
        logger.exception("lifespan reconciliation falhou")
    finally:
        db.close()
    yield
    # MERGED-017 — terminate subprocs rastreados (scraper etc) antes do DB cleanup
    terminate_tracked_subprocs()
    # Marcar runs ainda 'running' como interrupted no shutdown
    db = get_db()
    try:
        db.execute("UPDATE campaign_runs SET status = 'interrupted' WHERE status = 'running'")
        db.commit()
    except Exception:
        logger.exception("shutdown finalize falhou")
    finally:
        with suppress(Exception):
            db.close()


app = FastAPI(title="Hermes Command Center API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_F53_OAUTH_BYPASS_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # /api/_ping eh probe leve pro PC health-check, sem auth pra evitar timeout em datasets grandes
    if request.url.path == "/api/_ping":
        return await call_next(request)
    # F.5.3 — /api/mcp/* gerenciado por oauth_bearer_check (Bearer required, NÃO X-Hermes-Token)
    if request.url.path.startswith("/api/mcp/"):
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        token = request.headers.get("X-Hermes-Token", "")
        if not secrets.compare_digest(token, VM_AUTH_TOKEN):
            return JSONResponse(status_code=401, content={"detail": "Token invalido"})
    return await call_next(request)


@app.middleware("http")
async def oauth_bearer_check(request: Request, call_next):
    """F.5.3 — OAuth Bearer middleware específico pra /api/mcp/* endpoints.

    Allowlist bypass: STRICT set literal (NÃO regex amplo) — /health, /docs etc.
    Outros endpoints (não /api/mcp/*) passam sem checagem (auth_middleware lida).
    """
    if request.url.path in _F53_OAUTH_BYPASS_PATHS:
        return await call_next(request)
    if not request.url.path.startswith("/api/mcp/"):
        return await call_next(request)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"error": "missing_bearer", "path": request.url.path},
        )
    token = auth.removeprefix("Bearer ").strip()
    expected = os.getenv("HERMES_GATEWAY_OAUTH_SECRET", "")
    if not expected or not secrets.compare_digest(token, expected):
        return JSONResponse(
            status_code=401,
            content={"error": "invalid_bearer"},
        )
    return await call_next(request)


@app.get("/api/_ping")
async def vm_ping():
    """Probe leve (~5ms). Usado pelo PC server.py em vm_health_loop +
    /api/hermes/status pra evitar timeout em /api/dashboard (agregacao pesada).
    Sem auth — apenas confirma processo vivo."""
    return {"ok": True, "ts": time.time(), "service": "hermes_api_v2"}


app.include_router(vm_router)
app.include_router(mcp_coverage_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8420, log_level="info")
