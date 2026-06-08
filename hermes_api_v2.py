"""Hermes Command Center v2 — VM API Bridge (post MERGED-011 split).

FastAPI server on the VM that serves prospect data, activity logs,
pipeline status, scraper control, and photo references to the dashboard.

Routes movidas para vm_api/routes.py. Helpers compartilhados em vm_core/state.py.
"""
import secrets
import sys
from contextlib import asynccontextmanager, suppress
from pathlib import Path

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
)
import time
from vm_api.routes import router as vm_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # /api/_ping eh probe leve pro PC health-check, sem auth pra evitar timeout em datasets grandes
    if request.url.path == "/api/_ping":
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        token = request.headers.get("X-Hermes-Token", "")
        if not secrets.compare_digest(token, VM_AUTH_TOKEN):
            return JSONResponse(status_code=401, content={"detail": "Token invalido"})
    return await call_next(request)


@app.get("/api/_ping")
async def vm_ping():
    """Probe leve (~5ms). Usado pelo PC server.py em vm_health_loop +
    /api/hermes/status pra evitar timeout em /api/dashboard (agregacao pesada).
    Sem auth — apenas confirma processo vivo."""
    return {"ok": True, "ts": time.time(), "service": "hermes_api_v2"}


app.include_router(vm_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8420, log_level="info")
