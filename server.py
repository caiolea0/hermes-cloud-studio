"""Hermes Command Center v2 — Local Dashboard Server.

Serves the dashboard HTML + provides API endpoints for:
- Prospect management (local SQLite, paginated sync from VM)
- Task orchestration (Claude Code <-> Hermes)
- Activity feed
- Pipeline stats
- Photo proxy with local cache
- Scraper control (start/stop/history)
- Auto-sync with VM Hermes API every 60s

Port: 8500 (avoids Higgsfield Studio conflicts)
"""
import hashlib
import json
import os
import secrets
import sqlite3
import sys
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from config import settings  # MERGED-013 — Settings central pydantic-settings
import core.state as state
from core.state import (
    AUTH_TOKEN,
    INTERNAL_TOKEN,
    VM_API_URL,
    AGENT_ZERO_URL,
    AGENT_ZERO_API_KEY,
    GOOGLE_API_KEY,
    SYNC_INTERVAL,
    DASHBOARD_DIR,
    DB_PATH,
    PHOTO_CACHE_DIR,
    PROJECT_ROOT,
    _check_internal,
    _telegram_notify,
    _local_error_until_ack,
    _persist_local_errors,
    get_db,
    get_runtime_state,
    init_db,
    logger,
    set_runtime_state,
    spawn,
    ws_manager,
)
from core.models import (
    ActivityCreate,
    AgentZeroChatRequest,
    AuditConfig,
    BulkProspectAction,
    ClaudeCommand,
    PipelineExecuteRequest,
    PipelineTemplateCreate,
    PipelineTemplateUpdate,
    ProspectCreate,
    ProspectUpdate,
    ScraperConfig,
    ScraperPrompt,
    TaskCreate,
    TaskUpdate,
)


from loops.sync import sync_loop
from loops.linkedin_sync import linkedin_sync_loop
from loops.linkedin_scheduler import linkedin_scheduler_loop
from loops.linkedin_health import linkedin_health_monitor_loop
from loops.linkedin_session import linkedin_session_monitor_loop
from loops.vm_watchdog import vm_health_watchdog_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Apply LinkedIn migration if exists
    try:
        sql_path = PROJECT_ROOT / "migrations" / "2026_06_linkedin_full.sql"
        if sql_path.exists():
            conn = get_db()
            conn.executescript(sql_path.read_text(encoding="utf-8"))
            conn.commit()
            conn.close()
            logger.info("LinkedIn migration applied")
    except Exception as e:
        logger.warning(f"LinkedIn migration failed: {e}")
    # F.5.3 Apply MCP registry+calls migrations (idempotent)
    try:
        for mig_name in ("2026_06_mcp_registry.sql", "2026_06_mcp_calls.sql"):
            mig_path = PROJECT_ROOT / "migrations" / mig_name
            if mig_path.exists():
                conn = get_db()
                conn.executescript(mig_path.read_text(encoding="utf-8"))
                conn.commit()
                conn.close()
        logger.info("F.5.3 MCP migrations applied (registry + calls)")
    except Exception as e:
        logger.warning(f"F.5.3 MCP migrations failed: {e}")
    # F.6.1 Apply brain_runs + brain_decisions migration (idempotent)
    try:
        mig_path = PROJECT_ROOT / "migrations" / "2026_06_brain_runs_decisions.sql"
        if mig_path.exists():
            conn = get_db()
            conn.executescript(mig_path.read_text(encoding="utf-8"))
            conn.commit()
            conn.close()
            logger.info("F.6.1 Brain migration applied (brain_runs + brain_decisions)")
    except Exception as e:
        logger.warning(f"F.6.1 Brain migration failed: {e}")
    # F.6.4 ALTER brain_runs ADD COLUMN owner_comment (idempotent — catches duplicate column)
    try:
        mig_path = PROJECT_ROOT / "migrations" / "2026_06_brain_runs_owner_comment.sql"
        if mig_path.exists():
            conn = get_db()
            try:
                conn.executescript(mig_path.read_text(encoding="utf-8"))
                conn.commit()
                logger.info("F.6.4 owner_comment migration applied")
            except sqlite3.OperationalError as alter_exc:
                if "duplicate column name" in str(alter_exc).lower():
                    logger.info("F.6.4 owner_comment already present (idempotent)")
                else:
                    raise
            finally:
                conn.close()
    except Exception as e:
        logger.warning(f"F.6.4 owner_comment migration failed: {e}")
    # F.8.1 observability migration (mcp_pricing + perf_metrics + errors_inbox)
    try:
        mig_path = PROJECT_ROOT / "migrations" / "2026_06_observability.sql"
        if mig_path.exists():
            conn = get_db()
            conn.executescript(mig_path.read_text(encoding="utf-8"))
            conn.commit()
            conn.close()
            logger.info("F.8.1 observability migration applied (mcp_pricing + perf_metrics + errors_inbox)")
    except Exception as e:
        logger.warning(f"F.8.1 observability migration failed: {e}")
    # F.7 C1 — Apply cobaia warmup migration (idempotent)
    try:
        mig_path = PROJECT_ROOT / "migrations" / "2026_06_cobaia_warmup_state.sql"
        if mig_path.exists():
            conn = get_db()
            conn.executescript(mig_path.read_text(encoding="utf-8"))
            conn.commit()
            conn.close()
            logger.info("F.7 C1 cobaia warmup migration applied")
    except Exception as e:
        logger.warning(f"F.7 C1 cobaia migration failed: {e}")
    # F.7 P5 — Hunter.io email verifier cache (idempotent)
    try:
        mig_path = PROJECT_ROOT / "migrations" / "2026_06_hunter_email_cache.sql"
        if mig_path.exists():
            conn = get_db()
            conn.executescript(mig_path.read_text(encoding="utf-8"))
            conn.commit()
            conn.close()
            logger.info("F.7 P5 hunter_email_cache migration applied")
    except Exception as e:
        logger.warning(f"F.7 P5 hunter migration failed: {e}")
    # Restaurar globals persistidos em runtime_state (MERGED-004 / MERGED-016)
    state._LI_SESSION_LAST_OK = get_runtime_state("li_session_last_ok", True)
    state._LI_SESSION_LAST_NOTIFIED = get_runtime_state("li_session_last_notified", 0.0)
    state._LI_SESSION_FAIL_STREAK = get_runtime_state("li_session_fail_streak", 0)  # MERGED-018
    state._LI_HEALTH_LAST_STATE = get_runtime_state("li_health_last_state", None)
    state._LI_HEALTH_NOTIFIED_AT = get_runtime_state("li_health_notified_at", 0.0)
    restored_errors = get_runtime_state("local_error_until_ack", {})
    if isinstance(restored_errors, dict):
        _local_error_until_ack.update(restored_errors)
    logger.info(
        "runtime_state restaurado: session_ok=%s health_state=%s local_errors=%d",
        state._LI_SESSION_LAST_OK, state._LI_HEALTH_LAST_STATE, len(_local_error_until_ack),
    )
    logger.info("Starting server — sync will run in background")
    task = spawn(sync_loop())
    li_task = spawn(linkedin_sync_loop())
    li_monitor_task = spawn(linkedin_session_monitor_loop())
    li_health_task = spawn(linkedin_health_monitor_loop())
    li_scheduler_task = spawn(linkedin_scheduler_loop())
    vm_watchdog_task = spawn(vm_health_watchdog_loop())
    # F.8.1 perf metrics hourly flush (rolling 1h -> perf_metrics table)
    from core.observability import perf_flush_loop
    perf_flush_task = spawn(perf_flush_loop(DB_PATH))
    # F.7 C1 — Cobaia warmup APScheduler (09:00 BRT daily check)
    # F.7 C4 — Email digest job registered on same scheduler instance
    _cobaia_scheduler = None
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from daemon.cobaia_warmup_scheduler import init_cobaia_scheduler
        from daemon.email_digest import init_email_digest_scheduler
        from daemon.cobaia_autotune_loop import init_cobaia_autotune_scheduler
        _cobaia_scheduler = AsyncIOScheduler()
        _cobaia_scheduler.start()
        init_cobaia_scheduler(_cobaia_scheduler)
        init_email_digest_scheduler(_cobaia_scheduler)
        init_cobaia_autotune_scheduler(_cobaia_scheduler)
        logger.info("F.7 C1/C4/C5 cobaia APScheduler started (warmup + email digest + autotune)")
    except ImportError:
        logger.info("APScheduler not installed — cobaia daily scheduler disabled")
    except Exception as _e:
        logger.warning(f"F.7 C1 cobaia scheduler start failed: {_e}")
    yield
    task.cancel()
    li_task.cancel()
    li_monitor_task.cancel()
    li_health_task.cancel()
    li_scheduler_task.cancel()
    vm_watchdog_task.cancel()
    perf_flush_task.cancel()
    if _cobaia_scheduler:
        try:
            _cobaia_scheduler.shutdown(wait=False)
        except Exception:
            pass


app = FastAPI(title="Hermes Command Center", version="2.0.0", lifespan=lifespan)

# MERGED-020 — slowapi rate-limit pra /api/server/restart-* (DoS guard)
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from core.limiter import limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.mount("/dashboard", StaticFiles(directory=str(DASHBOARD_DIR)), name="dashboard-static")


# WebSocket manager + _check_internal viveram aqui — moveram pra core/state.py (MERGED-011).


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token", "") or websocket.headers.get("x-hermes-token", "")
    if not token or not secrets.compare_digest(token, AUTH_TOKEN):
        await websocket.close(code=1008, reason="Unauthorized")
        return
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:  # noqa: silenciado intencional — WS/broadcast opcional
        ws_manager.disconnect(websocket)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    # /api/internal/* tem auth proprio via _check_internal (X-Internal-Token + loopback bind).
    # /api/_bootstrap tem check loopback proprio no endpoint, sem token (retorna tokens pra clientes locais).
    # F.4.4 FIX: webhook movido para VM (hermes_api_v2.py). PC router removido.
    if path.startswith("/api/internal/") or path.startswith("/api/_bootstrap"):
        return await call_next(request)
    if path.startswith("/api/"):
        token = request.headers.get("X-Hermes-Token", "")
        if not secrets.compare_digest(token, AUTH_TOKEN):
            return JSONResponse(status_code=401, content={"detail": "Token invalido"})
    return await call_next(request)


# F.8.1 perf metrics middleware — added AFTER auth so it wraps outermost,
# capturing full request lifetime (including 401 responses).
from core.observability import install_perf_middleware
install_perf_middleware(app)


# Pydantic models viveram aqui — moveram pra core/models.py (MERGED-011).


# --- Routers extraidos pra api/ (MERGED-011) ---
from api.dashboard import router as dashboard_router
from api.prospects import router as prospects_router
from api.activities import router as activities_router
from api.tasks import router as tasks_router
from api.claude import router as claude_router
from api.agent_zero import router as agent_zero_router
from api.audit import router as audit_router
from api.outreach import router as outreach_router
from api.photos import router as photos_router
from api.scraper import router as scraper_router
from api.stats import router as stats_router

app.include_router(dashboard_router)
app.include_router(prospects_router)
app.include_router(activities_router)
app.include_router(tasks_router)
app.include_router(claude_router)
app.include_router(agent_zero_router)
app.include_router(audit_router)
app.include_router(outreach_router)
app.include_router(photos_router)
app.include_router(scraper_router)
app.include_router(stats_router)


# --- Routers extraidos pra api/ (MERGED-011) ---
from api.pipelines import router as pipelines_router
from api.linkedin import router as linkedin_router
from api.internal import router as internal_router
from api.server_ctrl import router as server_ctrl_router
from api.hermes import router as hermes_router
from api.daemon import router as daemon_router
from api.tunnel import router as tunnel_router
from api.bootstrap import router as bootstrap_router
from api.user_prefs import router as user_prefs_router  # F.2.5b
from api.lab import router as lab_router  # F.3.1 — Lab Cockpit
from api.observability import router as observability_router  # F.8.1c
from api.mcp_coverage import router as mcp_coverage_router  # F.5.6f — MCP Gateway UI proxy
from api.brain import router as brain_router  # F.6.1 — Brain orchestrator scaffold
from api.pipeline_studio import router as pipeline_studio_router  # F.9.1 — Pipeline Studio CRUD + step library
from api.skills import router as skills_router  # F.4.1 — Skill Proposals CRUD + lifecycle
from api.config import router as config_router  # F.4.3 — /api/config whitelisted feature flags
# F.4.4 FIX: webhook router MOVED to VM hermes_api.py — see api/skills_webhook.py
from api.cobaia import router as cobaia_router  # F.7 C1 — Cobaia warmup endpoints

app.include_router(pipelines_router)
app.include_router(linkedin_router)
app.include_router(internal_router)
app.include_router(server_ctrl_router)
app.include_router(hermes_router)
app.include_router(daemon_router)
app.include_router(tunnel_router)
app.include_router(bootstrap_router)
app.include_router(user_prefs_router)  # F.2.5b — /api/user-prefs GET/PUT
app.include_router(lab_router)  # F.3.1 — /api/lab/* (Lab Cockpit backend)
app.include_router(observability_router)  # F.8.1c — /api/observability/* (costs/perf/credits/errors/decisions)
app.include_router(mcp_coverage_router)  # F.5.6f — /api/mcp/coverage/latest + /api/mcp/gateway/health (UI proxy)
app.include_router(brain_router)  # F.6.1 — /api/brain/* (Brain orchestrator scaffold)
app.include_router(pipeline_studio_router)  # F.9.1 — /api/pipeline-studio/* (CRUD + step library + templates)
app.include_router(skills_router)  # F.4.1 — /api/skills/proposals/* CRUD + /api/skills/health
app.include_router(config_router)  # F.4.3 — /api/config whitelisted feature flags
# F.4.4 FIX: webhook include removed (endpoint lives on VM via Cloudflare tunnel)
app.include_router(cobaia_router)  # F.7 C1 — /api/linkedin/cobaia/* warmup endpoints


if __name__ == "__main__":
    import uvicorn
    # Port allocator: idempotencia + alocacao livre cross-projeto
    try:
        from scripts.port_allocator import allocate_port, is_self_already_running
        if is_self_already_running("dashboard"):
            print("[hermes] server.py JA esta rodando em outra instancia. Saindo (idempotencia).")
            sys.exit(0)
        _DASHBOARD_PORT = allocate_port("dashboard", reserve=True)
    except Exception as _e:
        print(f"[hermes] WARN: port_allocator falhou ({_e}). Caindo no default 55000.")
        _DASHBOARD_PORT = settings.dashboard_port

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    print("\n  Hermes Command Center v2")
    print(f"  Dashboard:  http://localhost:{_DASHBOARD_PORT}")
    print(f"  VM API:     {VM_API_URL}")
    print(f"  Sync every: {SYNC_INTERVAL}s")
    print(f"  API Docs:   http://localhost:{_DASHBOARD_PORT}/docs\n")
    try:
        uvicorn.run(app, host="127.0.0.1", port=_DASHBOARD_PORT, log_level="info")
    finally:
        try:
            from scripts.port_allocator import release_port
            release_port("dashboard")
        except Exception:  # noqa: silenciado intencional — fallback seguro
            pass
