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


async def sync_from_vm():
    """Pull ALL prospects and activities from VM API into local SQLite (paginated)."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Paginated prospect fetch
            vm_prospects = []
            offset = 0
            page_size = 500
            while True:
                r = await client.get(
                    f"{VM_API_URL}/api/prospects?limit={page_size}&offset={offset}"
                )
                if r.status_code != 200:
                    break
                batch = r.json().get("prospects", [])
                vm_prospects.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size

            # Paginated activities fetch
            vm_activities = []
            offset = 0
            while True:
                r = await client.get(
                    f"{VM_API_URL}/api/activities?limit={page_size}&offset={offset}"
                )
                if r.status_code != 200:
                    break
                batch = r.json().get("activities", [])
                vm_activities.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size

            r_dashboard = await client.get(f"{VM_API_URL}/api/dashboard")
            vm_dashboard = r_dashboard.json() if r_dashboard.status_code == 200 else {}

            # Cache scraper status
            try:
                r_scraper = await client.get(f"{VM_API_URL}/api/scraper/status")
                if r_scraper.status_code == 200:
                    scraper_data = r_scraper.json()
                else:
                    scraper_data = None
            except Exception:  # noqa: silenciado intencional — fallback de sonda
                scraper_data = None

    except Exception as e:
        logger.warning("Sync failed — VM unreachable: %s", e)
        return {"ok": False, "error": str(e)}

    if not vm_prospects and not vm_activities:
        return {"ok": True, "prospects": 0, "new_prospects": 0, "activities": 0, "new_activities": 0}

    conn = get_db()
    try:
        synced_p = 0
        for p in vm_prospects:
            vm_id = p.get("id")
            existing = conn.execute("SELECT id FROM prospects WHERE vm_id = ?", (vm_id,)).fetchone()
            if existing:
                conn.execute("""
                    UPDATE prospects SET
                        name=?, business_name=?, category=?, phone=?, email=?,
                        address=?, city=?, state=?, website=?, has_website=?,
                        google_maps_url=?, google_rating=?, google_reviews=?,
                        photo_ref=?,
                        social_instagram=?, social_facebook=?, source=?,
                        score=?, stage=?, audit_summary=?,
                        outreach_message=?, outreach_status=?,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE vm_id = ?
                """, (
                    p.get("name"), p.get("business_name"), p.get("category"),
                    p.get("phone"), p.get("email"), p.get("address"),
                    p.get("city", "Cuiaba"), p.get("state", "MT"),
                    p.get("website"), p.get("has_website", 0),
                    p.get("google_maps_url"), p.get("google_rating"),
                    p.get("google_reviews", 0), p.get("photo_ref"),
                    p.get("social_instagram"), p.get("social_facebook"),
                    p.get("source", "google_maps"),
                    p.get("score", 0), p.get("stage", "discovered"),
                    p.get("audit_summary"), p.get("outreach_message"),
                    p.get("outreach_status"), vm_id,
                ))
            else:
                conn.execute("""
                    INSERT INTO prospects (
                        vm_id, name, business_name, category, phone, email,
                        address, city, state, website, has_website,
                        google_maps_url, google_rating, google_reviews,
                        photo_ref,
                        social_instagram, social_facebook, source,
                        score, stage, audit_summary,
                        outreach_message, outreach_status, created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    vm_id, p.get("name"), p.get("business_name"), p.get("category"),
                    p.get("phone"), p.get("email"), p.get("address"),
                    p.get("city", "Cuiaba"), p.get("state", "MT"),
                    p.get("website"), p.get("has_website", 0),
                    p.get("google_maps_url"), p.get("google_rating"),
                    p.get("google_reviews", 0), p.get("photo_ref"),
                    p.get("social_instagram"), p.get("social_facebook"),
                    p.get("source", "google_maps"),
                    p.get("score", 0), p.get("stage", "discovered"),
                    p.get("audit_summary"), p.get("outreach_message"),
                    p.get("outreach_status"), p.get("created_at"),
                ))
                synced_p += 1

        synced_a = 0
        for a in vm_activities:
            vm_id = a.get("id")
            exists = conn.execute("SELECT id FROM activities WHERE vm_id = ?", (vm_id,)).fetchone()
            if not exists:
                vm_prospect_id = a.get("prospect_id")
                local_prospect_id = None
                if vm_prospect_id:
                    row = conn.execute("SELECT id FROM prospects WHERE vm_id = ?", (vm_prospect_id,)).fetchone()
                    if row:
                        local_prospect_id = row[0]
                conn.execute(
                    "INSERT INTO activities (vm_id, type, title, description, prospect_id, metadata, created_at) VALUES (?,?,?,?,?,?,?)",
                    (vm_id, a.get("type"), a.get("title"), a.get("description"),
                     local_prospect_id, a.get("metadata"), a.get("created_at"))
                )
                synced_a += 1

        by_stage = vm_dashboard.get("by_stage", {})
        if by_stage:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            conn.execute("""
                INSERT OR REPLACE INTO pipeline_stats (date, discovered, qualified, audited, outreach_sent)
                VALUES (?, ?, ?, ?, ?)
            """, (
                today,
                by_stage.get("discovered", 0),
                by_stage.get("qualified", 0),
                by_stage.get("audited", 0),
                by_stage.get("outreach", 0),
            ))

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES ('last_sync', ?, ?)",
            (now, now)
        )
        conn.execute(
            "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES ('vm_status', 'online', ?)",
            (now,)
        )
        conn.execute(
            "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES ('total_synced', ?, ?)",
            (str(len(vm_prospects)), now)
        )
        if scraper_data:
            conn.execute(
                "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES ('scraper_cache', ?, ?)",
                (json.dumps(scraper_data), now)
            )
        conn.commit()

        total_p = len(vm_prospects)
        total_a = len(vm_activities)
        logger.info("Sync OK — %d prospects (%d new), %d activities (%d new)", total_p, synced_p, total_a, synced_a)
        result = {"ok": True, "prospects": total_p, "new_prospects": synced_p, "activities": total_a, "new_activities": synced_a}
        await ws_manager.broadcast({"type": "sync", "data": result})
        return result

    except Exception as e:
        logger.error("Sync DB error: %s", e)
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()


async def sync_loop():
    """Background loop that syncs from VM every SYNC_INTERVAL seconds."""
    await asyncio.sleep(2)
    while True:
        await sync_from_vm()
        await asyncio.sleep(SYNC_INTERVAL)


async def sync_linkedin_campaigns():
    """Pull running LinkedIn campaigns from VM and update local DB +
    broadcast WS event if state changed. Runs every 10s."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{VM_API_URL}/api/linkedin/campaigns?limit=50")
            if r.status_code != 200:
                return
            data = r.json()
            campaigns = data.get("campaigns", [])
    except Exception:  # noqa: silenciado intencional — fallback seguro
        return

    if not campaigns:
        return

    conn = get_db()
    try:
        any_change = False
        for c in campaigns:
            # Look up local copy by id
            local = conn.execute(
                "SELECT status, progress FROM linkedin_campaigns WHERE id=?",
                (c["id"],)
            ).fetchone()
            if not local:
                # Insert
                conn.execute("""
                    INSERT INTO linkedin_campaigns
                      (id, type, config, status, progress, total, results, log, started_at, completed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    c["id"], c.get("type"),
                    json.dumps(c.get("config")) if isinstance(c.get("config"), (dict, list)) else (c.get("config") or "{}"),
                    c.get("status"), c.get("progress", 0), c.get("total", 0),
                    json.dumps(c.get("results")) if c.get("results") else None,
                    json.dumps(c.get("log", [])) if isinstance(c.get("log"), list) else (c.get("log") or "[]"),
                    c.get("started_at"), c.get("completed_at"),
                ))
                any_change = True
            elif local["status"] in ("scheduled", "cancelled"):
                # v6: PC owns these states. Skip — never let VM overwrite scheduled/cancelled.
                pass
            elif str(c["id"]) in _local_error_until_ack:
                # MERGED-016: erro de dispatch pendente de ack — não sobrescrever com dados da VM
                logger.debug("sync skip overwrite campaign %s (local error pendente)", c["id"])
            elif local["status"] != c.get("status") or local["progress"] != c.get("progress"):
                conn.execute("""
                    UPDATE linkedin_campaigns
                    SET status=?, progress=?, results=?, completed_at=?
                    WHERE id=?
                """, (
                    c.get("status"), c.get("progress", 0),
                    json.dumps(c.get("results")) if c.get("results") else None,
                    c.get("completed_at"),
                    c["id"],
                ))
                any_change = True
                # Broadcast progress
                try:
                    await ws_manager.broadcast({
                        "type": "linkedin_progress",
                        "data": {
                            "campaign_id": c["id"],
                            "status": c.get("status"),
                            "progress": c.get("progress", 0),
                            "partial_results": c.get("results"),
                        }
                    })
                except Exception:  # noqa: silenciado intencional — fallback seguro
                    pass
        if any_change:
            conn.commit()
    finally:
        conn.close()


async def linkedin_sync_loop():
    """10s LinkedIn campaigns sync. Lighter than the 60s general sync."""
    await asyncio.sleep(5)
    while True:
        try:
            await sync_linkedin_campaigns()
        except Exception as e:
            logger.warning(f"linkedin_sync_loop error: {e}")
        await asyncio.sleep(10)


async def linkedin_scheduler_loop():
    """Every 30s: find scheduled campaigns whose scheduled_for has elapsed AND
    all gates are clear, then dispatch them. Postpones (recomputes scheduled_for)
    if gates still active."""
    await asyncio.sleep(20)
    while True:
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            conn = get_db()
            try:
                rows = conn.execute(
                    "SELECT id, type, config FROM linkedin_campaigns "
                    "WHERE status='scheduled' AND scheduled_for <= ? "
                    "ORDER BY scheduled_for ASC",
                    (now_iso,)
                ).fetchall()
            finally:
                conn.close()

            for r in rows:
                cid = r["id"]
                ctype = r["type"]
                try:
                    cfg = json.loads(r["config"] or "{}")
                except Exception:  # noqa: silenciado intencional — fallback de sonda
                    cfg = {}

                # Re-check gates one more time before dispatching
                from api.linkedin import _compute_schedule_state
                new_sched, reasons = await _compute_schedule_state()
                if new_sched:
                    # Still gated — push schedule forward
                    msg = " · ".join(reasons)
                    conn2 = get_db()
                    try:
                        conn2.execute(
                            "UPDATE linkedin_campaigns SET scheduled_for=?, schedule_reason=? "
                            "WHERE id=? AND status='scheduled'",
                            (new_sched, msg, cid)
                        )
                        conn2.commit()
                    finally:
                        conn2.close()
                    try:
                        await ws_manager.broadcast({
                            "type": "linkedin_progress",
                            "data": {"campaign_id": cid, "status": "scheduled",
                                     "scheduled_for": new_sched, "schedule_reason": msg}
                        })
                    except Exception:  # noqa: silenciado intencional — WS/broadcast opcional
                        pass
                    continue

                # All clear → flip to pending and dispatch
                conn3 = get_db()
                try:
                    conn3.execute(
                        "UPDATE linkedin_campaigns SET status='pending', "
                        "started_at=?, scheduled_for=NULL, schedule_reason=NULL "
                        "WHERE id=? AND status='scheduled'",
                        (datetime.now(timezone.utc).isoformat(), cid)
                    )
                    conn3.commit()
                finally:
                    conn3.close()

                # WS notify dashboard the transition
                try:
                    await ws_manager.broadcast({
                        "type": "linkedin_progress",
                        "data": {"campaign_id": cid, "status": "pending",
                                 "msg": "Scheduler disparou campanha agendada"}
                    })
                except Exception:  # noqa: silenciado intencional — WS/broadcast opcional
                    pass

                # Fire dispatch (same flow as immediate path)
                async def _fire(cid=cid, ctype=ctype, cfg=cfg):
                    try:
                        async with httpx.AsyncClient(timeout=30) as client:
                            r = await client.post(
                                f"{VM_API_URL}/api/linkedin/campaigns/{ctype}",
                                json={"campaign_id": cid, **cfg},
                            )
                            ack = r.json() if r.status_code == 200 else {"ok": False}
                            if not ack.get("ok"):
                                raise RuntimeError(f"VM rejected: HTTP {r.status_code}")
                        # Telegram alert: scheduler fired
                        type_label = {"view": "Visitar Perfis", "engage": "Engajar Posts",
                                      "connect": "Enviar Conexões", "discover": "Descobrir Empresas"}.get(ctype, ctype)
                        await _telegram_notify(
                            f"🚀 Hermes disparou campanha agendada #{cid} ({type_label})"
                        )
                    except Exception as e:
                        logger.error(f"Scheduler dispatch error for #{cid}: {e}")
                        conn_e = get_db()
                        try:
                            conn_e.execute(
                                "UPDATE linkedin_campaigns SET status='error', completed_at=? WHERE id=?",
                                (datetime.now(timezone.utc).isoformat(), cid)
                            )
                            conn_e.commit()
                        finally:
                            conn_e.close()
                spawn(_fire())
        except Exception as e:
            logger.warning(f"linkedin_scheduler_loop error: {e}")
        await asyncio.sleep(30)


async def linkedin_health_monitor_loop():
    """Probe health every 3min. Telegram on state transitions. WS broadcast."""
    await asyncio.sleep(30)
    while True:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                # force_refresh sometimes to catch recovery; otherwise cached probe
                fr = "true" if state._LI_HEALTH_LAST_STATE not in (None, "ok") else "false"
                r = await client.get(f"{VM_API_URL}/api/linkedin/health",
                                     params={"force_refresh": fr})
                health = r.json() if r.status_code == 200 else {}
            new_state = health.get("state")
        except Exception as e:
            logger.warning(f"health monitor probe failed: {e}")
            await asyncio.sleep(180)
            continue

        if new_state and new_state != state._LI_HEALTH_LAST_STATE:
            # Transition detected
            if state._LI_HEALTH_LAST_STATE is None:
                # First run — just record state, only alert if not ok
                if new_state != "ok":
                    await _telegram_notify(
                        f"⚠️ Hermes LinkedIn: estado inicial é {new_state.upper()} — "
                        f"motivo: {health.get('reason')} — "
                        f"HTTP {health.get('http_code')}. Não rode campanhas até liberar."
                    )
            elif state._LI_HEALTH_LAST_STATE == "ok":
                await _telegram_notify(
                    f"🛑 Hermes LinkedIn entrou em {new_state.upper()}\n"
                    f"Motivo: {health.get('reason')}\n"
                    f"HTTP: {health.get('http_code')}\n"
                    f"Retry em ~{(health.get('retry_after_seconds') or 0)//60}min.\n"
                    f"Campanhas serão bloqueadas até liberar."
                )
            elif new_state == "ok":
                await _telegram_notify(
                    f"✅ Hermes LinkedIn liberado — pode rodar campanhas novamente."
                )
            # Broadcast to dashboard
            try:
                await ws_manager.broadcast({"type": "linkedin_health", "data": health})
            except Exception:  # noqa: silenciado intencional — WS/broadcast opcional
                pass
            state._LI_HEALTH_LAST_STATE = new_state
            state._LI_HEALTH_NOTIFIED_AT = time.time()
            set_runtime_state("li_health_last_state", state._LI_HEALTH_LAST_STATE)
            set_runtime_state("li_health_notified_at", state._LI_HEALTH_NOTIFIED_AT)

        # Sleep duration adapts to state:
        # - ok: 3min (light polling)
        # - cooldown/challenge: 60s (we want to detect recovery fast)
        # - blocked: 5min
        delay = {"ok": 180, "cooldown": 60, "challenge": 60, "blocked": 300}.get(new_state, 120)
        await asyncio.sleep(delay)


async def vm_health_watchdog_loop():
    """Monitora hermes_api_v2 na VM. Probe /api/_ping a cada 30s.

    Recovery:
      - 3 falhas consecutivas (90s sem responder) -> tenta restart via SSH
      - 6 falhas (180s) -> alerta Telegram + continua tentando
      - Reset contador apos sucesso

    Comando restart na VM (configurável via env HERMES_VM_RESTART_CMD):
      systemctl --user restart hermes-api    (se systemd unit existe)
      OR fallback: pkill -f hermes_api_v2 + nohup python3 hermes_api_v2.py
    """
    consecutive_fail = 0
    alerted = False
    RESTART_CMD = settings.hermes_vm_restart_cmd
    SSH_KEY = os.environ.get("USERPROFILE", "") + r"\.ssh\id_ed25519"
    vm_user = settings.vm_user
    vm_host = settings.vm_host

    await asyncio.sleep(30)  # warmup
    while True:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(f"{VM_API_URL}/api/_ping")
                if r.status_code == 200:
                    if consecutive_fail > 0:
                        logger.info(f"vm_watchdog: VM voltou apos {consecutive_fail} falhas")
                    consecutive_fail = 0
                    alerted = False
                else:
                    consecutive_fail += 1
                    logger.warning(f"vm_watchdog: ping status={r.status_code} (fail #{consecutive_fail})")
        except Exception as e:
            consecutive_fail += 1
            logger.warning(f"vm_watchdog: ping erro {type(e).__name__} (fail #{consecutive_fail})")

        # 3 falhas seguidas (90s) — tenta restart via SSH
        if consecutive_fail == 3:
            logger.error("vm_watchdog: 3 falhas consecutivas — tentando restart via SSH")
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ssh", "-i", SSH_KEY,
                    "-o", "ConnectTimeout=10", "-o", "BatchMode=yes",
                    f"{vm_user}@{vm_host}", RESTART_CMD,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
                logger.info(f"vm_watchdog: restart SSH rc={proc.returncode} "
                            f"out={stdout.decode()[:200]} err={stderr.decode()[:200]}")
            except Exception as e:
                logger.error(f"vm_watchdog: SSH restart falhou: {e}")

        # 6 falhas (180s) — alerta Telegram
        if consecutive_fail == 6 and not alerted:
            try:
                await _telegram_notify(
                    f"VM Hermes ({vm_host}:8420) sem responder ha {consecutive_fail*30}s. "
                    f"Restart SSH tentado mas sem efeito. Verificar manualmente:\n"
                    f"  ssh {vm_user}@{vm_host}\n"
                    f"  ps aux | grep hermes_api"
                )
                alerted = True
            except Exception as e:
                logger.warning(f"vm_watchdog: telegram alert falhou: {e}")

        await asyncio.sleep(30)


async def linkedin_session_monitor_loop():
    """Every 1h: GET /api/linkedin/status. If session_ok flips False, alert via Telegram.
    Avoids spamming — only notifies on transitions True→False (or every 12h while broken).
    """
    await asyncio.sleep(60)  # let system warm up
    while True:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{VM_API_URL}/api/linkedin/session-check")
                ok = r.status_code == 200 and r.json().get("ok")
        except Exception:  # noqa: silenciado intencional — fallback de sonda
            ok = False

        now = time.time()
        if not ok:
            need_notify = state._LI_SESSION_LAST_OK or (now - state._LI_SESSION_LAST_NOTIFIED > 43200)
            if need_notify:
                await _telegram_notify(
                    "⚠️ Hermes LinkedIn: sessão caiu (session_ok=false).\n"
                    "Renove o cookie LI_AT no Chrome e o sync rodará no próximo ciclo (03:00), "
                    "ou rode agora manualmente: python scripts/li_at_sync.py"
                )
                state._LI_SESSION_LAST_NOTIFIED = now
                set_runtime_state("li_session_last_notified", state._LI_SESSION_LAST_NOTIFIED)
        elif not state._LI_SESSION_LAST_OK:
            # session restored
            await _telegram_notify("✅ Hermes LinkedIn: sessão restaurada.")

        state._LI_SESSION_LAST_OK = ok
        set_runtime_state("li_session_last_ok", state._LI_SESSION_LAST_OK)
        await asyncio.sleep(3600)  # 1 hora


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
    # Restaurar globals persistidos em runtime_state (MERGED-004 / MERGED-016)
    state._LI_SESSION_LAST_OK = get_runtime_state("li_session_last_ok", True)
    state._LI_SESSION_LAST_NOTIFIED = get_runtime_state("li_session_last_notified", 0.0)
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
    yield
    task.cancel()
    li_task.cancel()
    li_monitor_task.cancel()
    li_health_task.cancel()
    li_scheduler_task.cancel()
    vm_watchdog_task.cancel()


app = FastAPI(title="Hermes Command Center", version="2.0.0", lifespan=lifespan)

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
    if path.startswith("/api/internal/") or path.startswith("/api/_bootstrap"):
        return await call_next(request)
    if path.startswith("/api/"):
        token = request.headers.get("X-Hermes-Token", "")
        if not secrets.compare_digest(token, AUTH_TOKEN):
            return JSONResponse(status_code=401, content={"detail": "Token invalido"})
    return await call_next(request)


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

app.include_router(pipelines_router)
app.include_router(linkedin_router)
app.include_router(internal_router)
app.include_router(server_ctrl_router)
app.include_router(hermes_router)
app.include_router(daemon_router)
app.include_router(tunnel_router)
app.include_router(bootstrap_router)


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
