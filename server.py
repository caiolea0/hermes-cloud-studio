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
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

load_dotenv(Path(__file__).parent / ".env")

logger = logging.getLogger("hermes")

BASE_DIR = Path(__file__).parent
DASHBOARD_DIR = BASE_DIR / "dashboard"
DB_PATH = BASE_DIR / "hermes_local.db"
PHOTO_CACHE_DIR = BASE_DIR / "photo_cache"
VM_API_URL = os.environ.get("HERMES_VM_API", "http://localhost:8420")
AGENT_ZERO_URL = os.environ.get("AGENT_ZERO_URL", "http://localhost:50080")
AGENT_ZERO_API_KEY = os.environ.get("AGENT_ZERO_API_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")
SYNC_INTERVAL = int(os.environ.get("HERMES_SYNC_INTERVAL", "60"))
AUTH_TOKEN = os.environ.get("HERMES_AUTH_TOKEN", "").strip()
if not AUTH_TOKEN:
    raise RuntimeError(
        "HERMES_AUTH_TOKEN obrigatório. Setar em .env ou env var antes de subir o server. "
        "Gerar via: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
    )

# Persistent Agent Zero context for Hermes conversations
_agent_zero_context_id: Optional[str] = None

PHOTO_CACHE_DIR.mkdir(exist_ok=True)


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS prospects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vm_id INTEGER UNIQUE,
            name TEXT NOT NULL,
            business_name TEXT,
            category TEXT,
            phone TEXT,
            email TEXT,
            address TEXT,
            city TEXT DEFAULT 'Cuiaba',
            state TEXT DEFAULT 'MT',
            website TEXT,
            has_website BOOLEAN DEFAULT 0,
            google_maps_url TEXT,
            google_rating REAL,
            google_reviews INTEGER DEFAULT 0,
            photo_ref TEXT,
            social_instagram TEXT,
            social_facebook TEXT,
            linkedin_url TEXT,
            source TEXT DEFAULT 'google_maps',
            score INTEGER DEFAULT 0,
            stage TEXT DEFAULT 'discovered',
            notes TEXT,
            audit_summary TEXT,
            outreach_message TEXT,
            outreach_status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vm_id INTEGER UNIQUE,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            prospect_id INTEGER,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (prospect_id) REFERENCES prospects(id)
        );

        CREATE TABLE IF NOT EXISTS pipeline_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            discovered INTEGER DEFAULT 0,
            qualified INTEGER DEFAULT 0,
            audited INTEGER DEFAULT 0,
            outreach_sent INTEGER DEFAULT 0,
            responses INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'pending',
            priority TEXT DEFAULT 'medium',
            assigned_to TEXT DEFAULT 'hermes',
            created_by TEXT DEFAULT 'system',
            result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sync_state (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_prospects_stage ON prospects(stage);
        CREATE INDEX IF NOT EXISTS idx_prospects_score ON prospects(score DESC);
        CREATE INDEX IF NOT EXISTS idx_prospects_vm_id ON prospects(vm_id);
        CREATE INDEX IF NOT EXISTS idx_prospects_city ON prospects(city);
        CREATE INDEX IF NOT EXISTS idx_prospects_category ON prospects(category);
        CREATE INDEX IF NOT EXISTS idx_activities_type ON activities(type);
        CREATE INDEX IF NOT EXISTS idx_activities_vm_id ON activities(vm_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

        CREATE TABLE IF NOT EXISTS pipeline_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'custom',
            description TEXT,
            prompt TEXT,
            targets_config TEXT,
            schedule_config TEXT,
            is_active BOOLEAN DEFAULT 1,
            last_run_at TIMESTAMP,
            total_runs INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS pipeline_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            progress INTEGER DEFAULT 0,
            total_items INTEGER DEFAULT 0,
            processed_items INTEGER DEFAULT 0,
            log TEXT DEFAULT '[]',
            result TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (template_id) REFERENCES pipeline_templates(id)
        );

        CREATE INDEX IF NOT EXISTS idx_pipeline_exec_template ON pipeline_executions(template_id);
        CREATE INDEX IF NOT EXISTS idx_pipeline_exec_status ON pipeline_executions(status);

        CREATE TABLE IF NOT EXISTS daemon_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            state TEXT NOT NULL DEFAULT 'idle',
            current_task_type TEXT,
            current_task_detail TEXT,
            energy REAL DEFAULT 1.0,
            started_at TIMESTAMP,
            last_heartbeat TIMESTAMP,
            stats_today TEXT,
            stats_week TEXT
        );

        CREATE TABLE IF NOT EXISTS daemon_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            level TEXT NOT NULL DEFAULT 'info',
            category TEXT NOT NULL DEFAULT 'system',
            message TEXT NOT NULL,
            metadata TEXT,
            visual_event TEXT
        );

        CREATE TABLE IF NOT EXISTS daemon_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            action TEXT NOT NULL,
            reason TEXT NOT NULL,
            context TEXT,
            result TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_daemon_log_ts ON daemon_log(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_daemon_log_cat ON daemon_log(category);
        CREATE INDEX IF NOT EXISTS idx_daemon_decisions_ts ON daemon_decisions(timestamp DESC);

        CREATE TABLE IF NOT EXISTS linkedin_campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            config TEXT NOT NULL DEFAULT '{}',
            status TEXT DEFAULT 'pending',
            progress INTEGER DEFAULT 0,
            total INTEGER DEFAULT 0,
            results TEXT,
            log TEXT DEFAULT '[]',
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_li_campaigns_status ON linkedin_campaigns(status);
        CREATE INDEX IF NOT EXISTS idx_li_campaigns_type ON linkedin_campaigns(type);

        INSERT OR IGNORE INTO daemon_state (id, state, started_at, last_heartbeat)
        VALUES (1, 'idle', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
    """)
    conn.commit()

    # Migration: add photo_ref column if missing
    try:
        conn.execute("SELECT photo_ref FROM prospects LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE prospects ADD COLUMN photo_ref TEXT")
        conn.commit()
        logger.info("Migration: added photo_ref column to prospects")

    conn.close()


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
            except Exception:
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
    except Exception:
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
                except Exception:
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


# ─── Session health monitor (Option D — Telegram alert on session expiry) ───
_LI_SESSION_LAST_OK = True   # debounce
_LI_SESSION_LAST_NOTIFIED = 0.0


async def _telegram_notify(text: str):
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not (tok and chat):
        return
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": chat, "text": text, "disable_web_page_preview": True},
            )
    except Exception as e:
        logger.warning(f"Telegram notify failed: {e}")


# ─── Health (cooldown) monitor loop ──────────────────────────────────────────
_LI_HEALTH_LAST_STATE = None
_LI_HEALTH_NOTIFIED_AT = 0.0


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
                except Exception:
                    cfg = {}

                # Re-check gates one more time before dispatching
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
                    except Exception:
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
                except Exception:
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
                asyncio.create_task(_fire())
        except Exception as e:
            logger.warning(f"linkedin_scheduler_loop error: {e}")
        await asyncio.sleep(30)


async def linkedin_health_monitor_loop():
    """Probe health every 3min. Telegram on state transitions. WS broadcast."""
    global _LI_HEALTH_LAST_STATE, _LI_HEALTH_NOTIFIED_AT
    await asyncio.sleep(30)
    while True:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                # force_refresh sometimes to catch recovery; otherwise cached probe
                fr = "true" if _LI_HEALTH_LAST_STATE not in (None, "ok") else "false"
                r = await client.get(f"{VM_API_URL}/api/linkedin/health",
                                     params={"force_refresh": fr})
                health = r.json() if r.status_code == 200 else {}
            new_state = health.get("state")
        except Exception as e:
            logger.warning(f"health monitor probe failed: {e}")
            await asyncio.sleep(180)
            continue

        if new_state and new_state != _LI_HEALTH_LAST_STATE:
            # Transition detected
            if _LI_HEALTH_LAST_STATE is None:
                # First run — just record state, only alert if not ok
                if new_state != "ok":
                    await _telegram_notify(
                        f"⚠️ Hermes LinkedIn: estado inicial é {new_state.upper()} — "
                        f"motivo: {health.get('reason')} — "
                        f"HTTP {health.get('http_code')}. Não rode campanhas até liberar."
                    )
            elif _LI_HEALTH_LAST_STATE == "ok":
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
            except Exception:
                pass
            _LI_HEALTH_LAST_STATE = new_state
            _LI_HEALTH_NOTIFIED_AT = time.time()

        # Sleep duration adapts to state:
        # - ok: 3min (light polling)
        # - cooldown/challenge: 60s (we want to detect recovery fast)
        # - blocked: 5min
        delay = {"ok": 180, "cooldown": 60, "challenge": 60, "blocked": 300}.get(new_state, 120)
        await asyncio.sleep(delay)


async def linkedin_session_monitor_loop():
    """Every 1h: GET /api/linkedin/status. If session_ok flips False, alert via Telegram.
    Avoids spamming — only notifies on transitions True→False (or every 12h while broken).
    """
    global _LI_SESSION_LAST_OK, _LI_SESSION_LAST_NOTIFIED
    await asyncio.sleep(60)  # let system warm up
    while True:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{VM_API_URL}/api/linkedin/session-check")
                ok = r.status_code == 200 and r.json().get("ok")
        except Exception:
            ok = False

        now = time.time()
        if not ok:
            need_notify = _LI_SESSION_LAST_OK or (now - _LI_SESSION_LAST_NOTIFIED > 43200)
            if need_notify:
                await _telegram_notify(
                    "⚠️ Hermes LinkedIn: sessão caiu (session_ok=false).\n"
                    "Renove o cookie LI_AT no Chrome e o sync rodará no próximo ciclo (03:00), "
                    "ou rode agora manualmente: python scripts/li_at_sync.py"
                )
                _LI_SESSION_LAST_NOTIFIED = now
        elif not _LI_SESSION_LAST_OK:
            # session restored
            await _telegram_notify("✅ Hermes LinkedIn: sessão restaurada.")

        _LI_SESSION_LAST_OK = ok
        await asyncio.sleep(3600)  # 1 hora


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Apply LinkedIn migration if exists
    try:
        sql_path = Path(__file__).parent / "migrations" / "2026_06_linkedin_full.sql"
        if sql_path.exists():
            conn = get_db()
            conn.executescript(sql_path.read_text(encoding="utf-8"))
            conn.commit()
            conn.close()
            logger.info("LinkedIn migration applied")
    except Exception as e:
        logger.warning(f"LinkedIn migration failed: {e}")
    logger.info("Starting server — sync will run in background")
    task = asyncio.create_task(sync_loop())
    li_task = asyncio.create_task(linkedin_sync_loop())
    li_monitor_task = asyncio.create_task(linkedin_session_monitor_loop())
    li_health_task = asyncio.create_task(linkedin_health_monitor_loop())
    li_scheduler_task = asyncio.create_task(linkedin_scheduler_loop())
    yield
    task.cancel()
    li_task.cancel()
    li_monitor_task.cancel()
    li_health_task.cancel()
    li_scheduler_task.cancel()


app = FastAPI(title="Hermes Command Center", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.mount("/dashboard", StaticFiles(directory=str(DASHBOARD_DIR)), name="dashboard-static")


# ============================================================
# WEBSOCKET MANAGER
# ============================================================

class WSManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, event: dict):
        for ws in self.connections[:]:
            try:
                await ws.send_json(event)
            except Exception:
                self.connections.remove(ws)


ws_manager = WSManager()


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
    except Exception:
        ws_manager.disconnect(websocket)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/"):
        token = request.headers.get("X-Hermes-Token", "")
        if not secrets.compare_digest(token, AUTH_TOKEN):
            return JSONResponse(status_code=401, content={"detail": "Token invalido"})
    return await call_next(request)


# --- Models ---

class ProspectCreate(BaseModel):
    name: str
    business_name: Optional[str] = None
    category: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: str = "Cuiaba"
    state: str = "MT"
    website: Optional[str] = None
    google_maps_url: Optional[str] = None
    google_rating: Optional[float] = None
    google_reviews: int = 0
    photo_ref: Optional[str] = None
    source: str = "google_maps"


class ProspectUpdate(BaseModel):
    name: Optional[str] = None
    business_name: Optional[str] = None
    category: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    stage: Optional[str] = None
    score: Optional[int] = None
    notes: Optional[str] = None
    audit_summary: Optional[str] = None
    outreach_message: Optional[str] = None
    outreach_status: Optional[str] = None


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    assigned_to: str = "hermes"
    created_by: str = "claude"


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_to: Optional[str] = None
    result: Optional[str] = None


class ActivityCreate(BaseModel):
    type: str
    title: str
    description: Optional[str] = None
    prospect_id: Optional[int] = None
    metadata: Optional[dict] = None


class ClaudeCommand(BaseModel):
    command: str
    context: Optional[str] = None


class AuditConfig(BaseModel):
    batch_size: int = 50
    stage: str = "discovered"


class ScraperConfig(BaseModel):
    cities: Optional[List[str]] = None
    categories: Optional[List[str]] = None
    only_no_site: bool = False
    rate_limit: float = 1.0


class ScraperPrompt(BaseModel):
    prompt: str


class BulkProspectAction(BaseModel):
    ids: List[int]
    action: str  # "stage_change", "score_update"
    value: str


class PipelineTemplateCreate(BaseModel):
    name: str
    type: str = "custom"
    description: Optional[str] = None
    prompt: Optional[str] = None
    targets_config: Optional[dict] = None
    schedule_config: Optional[dict] = None


class PipelineTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = None
    targets_config: Optional[dict] = None
    schedule_config: Optional[dict] = None
    is_active: Optional[bool] = None


class PipelineExecuteRequest(BaseModel):
    template_id: int
    override_prompt: Optional[str] = None


# --- Serve Dashboard ---

@app.get("/")
async def serve_dashboard():
    return FileResponse(DASHBOARD_DIR / "index.html")


# --- Dashboard API ---

@app.get("/api/dashboard")
async def get_dashboard():
    conn = get_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM prospects").fetchone()[0]
        by_stage = dict(conn.execute(
            "SELECT stage, COUNT(*) FROM prospects GROUP BY stage"
        ).fetchall())
        by_city = dict(conn.execute(
            "SELECT city, COUNT(*) FROM prospects GROUP BY city ORDER BY COUNT(*) DESC LIMIT 20"
        ).fetchall())
        recent_activities = [dict(r) for r in conn.execute(
            "SELECT * FROM activities ORDER BY created_at DESC LIMIT 20"
        ).fetchall()]
        active_tasks = [dict(r) for r in conn.execute(
            "SELECT * FROM tasks WHERE status IN ('pending', 'running') ORDER BY created_at DESC LIMIT 10"
        ).fetchall()]
        top_prospects = [dict(r) for r in conn.execute(
            "SELECT * FROM prospects WHERE score > 0 ORDER BY score DESC LIMIT 10"
        ).fetchall()]
        with_website = conn.execute("SELECT COUNT(*) FROM prospects WHERE has_website = 1").fetchone()[0]
        without_website = conn.execute("SELECT COUNT(*) FROM prospects WHERE has_website = 0").fetchone()[0]

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_stats = conn.execute(
            "SELECT * FROM pipeline_stats WHERE date = ?", (today,)
        ).fetchone()

        total_tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        pending_tasks = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'pending'").fetchone()[0]

        return {
            "total_prospects": total,
            "with_website": with_website,
            "without_website": without_website,
            "by_stage": by_stage,
            "by_city": by_city,
            "recent_activities": recent_activities,
            "active_tasks": active_tasks,
            "top_prospects": top_prospects,
            "today_stats": dict(today_stats) if today_stats else None,
            "total_tasks": total_tasks,
            "pending_tasks": pending_tasks,
            "hermes_status": "online",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        conn.close()


# --- Prospects ---

@app.get("/api/prospects")
async def list_prospects(
    stage: Optional[str] = None,
    city: Optional[str] = None,
    category: Optional[str] = None,
    has_website: Optional[bool] = None,
    search: Optional[str] = None,
    min_score: int = 0,
    limit: int = 50,
    offset: int = 0,
):
    conn = get_db()
    try:
        query = "SELECT * FROM prospects WHERE score >= ?"
        count_query = "SELECT COUNT(*) FROM prospects WHERE score >= ?"
        params: list = [min_score]
        count_params: list = [min_score]
        if stage:
            query += " AND stage = ?"
            count_query += " AND stage = ?"
            params.append(stage)
            count_params.append(stage)
        if city:
            query += " AND city = ?"
            count_query += " AND city = ?"
            params.append(city)
            count_params.append(city)
        if category:
            query += " AND category LIKE ?"
            count_query += " AND category LIKE ?"
            params.append(f"%{category}%")
            count_params.append(f"%{category}%")
        if has_website is not None:
            query += " AND has_website = ?"
            count_query += " AND has_website = ?"
            params.append(1 if has_website else 0)
            count_params.append(1 if has_website else 0)
        if search:
            query += " AND (business_name LIKE ? OR name LIKE ? OR category LIKE ? OR city LIKE ?)"
            count_query += " AND (business_name LIKE ? OR name LIKE ? OR category LIKE ? OR city LIKE ?)"
            s = f"%{search}%"
            params.extend([s, s, s, s])
            count_params.extend([s, s, s, s])

        total = conn.execute(count_query, count_params).fetchone()[0]
        query += " ORDER BY score DESC, created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]
        return {"total": total, "count": len(rows), "prospects": rows}
    finally:
        conn.close()


@app.get("/api/prospects/cities")
async def list_cities():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT city, COUNT(*) as count FROM prospects GROUP BY city ORDER BY count DESC"
        ).fetchall()
        return {"cities": [{"city": r[0], "count": r[1]} for r in rows]}
    finally:
        conn.close()


@app.get("/api/prospects/categories")
async def list_categories():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, COUNT(*) as count FROM prospects GROUP BY category ORDER BY count DESC LIMIT 50"
        ).fetchall()
        return {"categories": [{"category": r[0], "count": r[1]} for r in rows]}
    finally:
        conn.close()


@app.get("/api/prospects/{prospect_id}")
async def get_prospect(prospect_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Prospect not found")
        activities = [dict(r) for r in conn.execute(
            "SELECT * FROM activities WHERE prospect_id = ? ORDER BY created_at DESC",
            (prospect_id,)
        ).fetchall()]
        return {**dict(row), "activities": activities}
    finally:
        conn.close()


@app.post("/api/prospects")
async def create_prospect(p: ProspectCreate):
    conn = get_db()
    try:
        has_website = 1 if p.website else 0
        cur = conn.execute(
            """INSERT INTO prospects (name, business_name, category, phone, email,
               address, city, state, website, has_website, google_maps_url,
               google_rating, google_reviews, photo_ref, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (p.name, p.business_name, p.category, p.phone, p.email,
             p.address, p.city, p.state, p.website, has_website,
             p.google_maps_url, p.google_rating, p.google_reviews, p.photo_ref, p.source)
        )
        conn.commit()
        conn.execute(
            "INSERT INTO activities (type, title, prospect_id) VALUES (?, ?, ?)",
            ("discovery", f"Novo prospect: {p.business_name or p.name}", cur.lastrowid)
        )
        conn.commit()
        return {"id": cur.lastrowid, "status": "created"}
    finally:
        conn.close()


@app.patch("/api/prospects/{prospect_id}")
async def update_prospect(prospect_id: int, update: ProspectUpdate):
    conn = get_db()
    try:
        sets = []
        params = []
        for field, value in update.model_dump(exclude_none=True).items():
            sets.append(f"{field} = ?")
            params.append(value)
        if not sets:
            raise HTTPException(400, "No fields to update")
        sets.append("updated_at = CURRENT_TIMESTAMP")
        params.append(prospect_id)
        conn.execute(f"UPDATE prospects SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
        return {"status": "updated"}
    finally:
        conn.close()


@app.post("/api/prospects/bulk")
async def bulk_prospect_action(action: BulkProspectAction):
    conn = get_db()
    try:
        if action.action == "stage_change":
            placeholders = ",".join("?" for _ in action.ids)
            conn.execute(
                f"UPDATE prospects SET stage = ?, updated_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
                [action.value] + action.ids
            )
        elif action.action == "score_update":
            placeholders = ",".join("?" for _ in action.ids)
            conn.execute(
                f"UPDATE prospects SET score = ?, updated_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
                [int(action.value)] + action.ids
            )
        conn.commit()
        return {"status": "updated", "count": len(action.ids)}
    finally:
        conn.close()


@app.post("/api/prospects/{prospect_id}/strategy")
async def generate_strategy(prospect_id: int):
    """Send prospect to Claude Code for marketing strategy generation."""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Prospect not found")
        p = dict(row)
    finally:
        conn.close()

    has_site = "com website" if p.get("website") else "SEM website"
    prompt = (
        f"Crie uma estrategia de marketing digital completa para prospectar o cliente: "
        f"{p['business_name']} ({p.get('category', 'negocio')}) em {p.get('city', 'Cuiaba')}, MT. "
        f"O negocio {has_site}. "
        f"Google rating: {p.get('google_rating', 'N/A')}/5 ({p.get('google_reviews', 0)} avaliacoes). "
        f"Telefone: {p.get('phone', 'N/A')}. "
        f"Inclua: 1) Analise do potencial digital, 2) Proposta de servicos personalizados, "
        f"3) Mensagem de abordagem para WhatsApp, 4) Mensagem para email, "
        f"5) Estrategia de conteudo sugerida. "
        f"Responda em portugues brasileiro, tom profissional mas acessivel."
    )
    return await execute_claude_command(ClaudeCommand(command=prompt, context=json.dumps(p, default=str)))


# --- Activities ---

@app.get("/api/activities")
async def list_activities(limit: int = 50, type: Optional[str] = None, offset: int = 0, prospect_id: Optional[int] = None):
    conn = get_db()
    try:
        conditions = []
        params = []
        if type:
            conditions.append("type = ?")
            params.append(type)
        if prospect_id:
            conditions.append("prospect_id = ?")
            params.append(prospect_id)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = conn.execute(
            f"SELECT * FROM activities {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset]
        ).fetchall()
        return {"activities": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.post("/api/activities")
async def create_activity(a: ActivityCreate):
    conn = get_db()
    try:
        meta = json.dumps(a.metadata) if a.metadata else None
        conn.execute(
            "INSERT INTO activities (type, title, description, prospect_id, metadata) VALUES (?, ?, ?, ?, ?)",
            (a.type, a.title, a.description, a.prospect_id, meta)
        )
        conn.commit()
        return {"status": "created"}
    finally:
        conn.close()


# --- Tasks ---

@app.get("/api/tasks")
async def list_tasks(status: Optional[str] = None, limit: int = 50, offset: int = 0):
    conn = get_db()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status, limit, offset)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        return {"total": total, "tasks": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.post("/api/tasks")
async def create_task(t: TaskCreate):
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO tasks (title, description, priority, assigned_to, created_by) VALUES (?, ?, ?, ?, ?)",
            (t.title, t.description, t.priority, t.assigned_to, t.created_by)
        )
        conn.commit()
        conn.execute(
            "INSERT INTO activities (type, title, description) VALUES (?, ?, ?)",
            ("task", f"Nova task: {t.title}", f"Atribuida a {t.assigned_to}")
        )
        conn.commit()
        return {"id": cur.lastrowid, "status": "created"}
    finally:
        conn.close()


@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: int, update: TaskUpdate):
    conn = get_db()
    try:
        sets = []
        params = []
        for field, value in update.model_dump(exclude_none=True).items():
            sets.append(f"{field} = ?")
            params.append(value)
        if not sets:
            raise HTTPException(400, "No fields to update")
        if update.status == "completed":
            sets.append("completed_at = ?")
            params.append(datetime.now(timezone.utc).isoformat())
        params.append(task_id)
        conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
        return {"status": "updated"}
    finally:
        conn.close()


@app.post("/api/tasks/{task_id}/send-to-claude")
async def send_task_to_claude(task_id: int):
    """Execute a task via Claude Code CLI."""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Task not found")
        t = dict(row)
    finally:
        conn.close()
    return await execute_claude_command(ClaudeCommand(
        command=f"Execute esta tarefa: {t['title']}\nDetalhes: {t.get('description', 'N/A')}",
        context=t.get("description")
    ))


@app.post("/api/tasks/bulk")
async def bulk_task_action(ids: List[int], action: str, value: str = ""):
    conn = get_db()
    try:
        placeholders = ",".join("?" for _ in ids)
        if action == "status":
            completed = datetime.now(timezone.utc).isoformat() if value == "completed" else None
            conn.execute(
                f"UPDATE tasks SET status = ?, completed_at = ? WHERE id IN ({placeholders})",
                [value, completed] + ids
            )
        elif action == "priority":
            conn.execute(
                f"UPDATE tasks SET priority = ? WHERE id IN ({placeholders})",
                [value] + ids
            )
        conn.commit()
        return {"status": "updated", "count": len(ids)}
    finally:
        conn.close()


# --- AI Integration (Agent Zero + Claude Code fallback) ---

async def call_agent_zero(message: str, context_id: str = "", timeout: float = 300) -> dict:
    """Call Agent Zero API on VM. Returns {"response": str, "context_id": str, "provider": "agent_zero"}."""
    global _agent_zero_context_id
    payload = {"message": message}
    if context_id:
        payload["context_id"] = context_id
    elif _agent_zero_context_id:
        payload["context_id"] = _agent_zero_context_id

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{AGENT_ZERO_URL}/api/api_message",
                json=payload,
                headers={"X-API-KEY": AGENT_ZERO_API_KEY, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("context_id"):
                _agent_zero_context_id = data["context_id"]
            return {
                "response": data.get("response", "(sem resposta)"),
                "context_id": data.get("context_id", ""),
                "provider": "agent_zero",
            }
    except Exception as e:
        logger.warning(f"Agent Zero indisponivel ({e}), tentando Claude CLI...")
        raise


async def call_claude_cli(command: str, timeout: float = 120) -> dict:
    """Fallback: execute via Claude Code CLI (claude -p)."""
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    output = stdout.decode("utf-8", errors="replace").strip()
    error = stderr.decode("utf-8", errors="replace").strip()
    return {
        "response": output or error or "(sem output)",
        "context_id": "",
        "provider": "claude_cli",
    }


async def call_ai(message: str, context_id: str = "", timeout: float = 300) -> dict:
    """Unified AI caller: Agent Zero first, Claude CLI fallback."""
    try:
        return await call_agent_zero(message, context_id, timeout)
    except Exception:
        try:
            return await call_claude_cli(message, min(timeout, 120))
        except Exception as e:
            return {"response": f"Erro: AI indisponivel — {e}", "context_id": "", "provider": "none"}


@app.post("/api/claude/execute")
async def execute_claude_command(cmd: ClaudeCommand):
    """Execute a command via Agent Zero (primary) or Claude Code CLI (fallback)."""
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO tasks (title, description, status, assigned_to, created_by) VALUES (?, ?, 'running', 'agent_zero', 'dashboard')",
            (cmd.command[:200], cmd.context)
        )
        task_id = cur.lastrowid
        conn.execute(
            "INSERT INTO activities (type, title, description) VALUES (?, ?, ?)",
            ("task", f"AI: {cmd.command[:80]}", "Executando via Agent Zero...")
        )
        conn.commit()
    finally:
        conn.close()

    try:
        ai_result = await call_ai(cmd.command, timeout=300)
        result = ai_result["response"]
        provider = ai_result["provider"]

        conn = get_db()
        try:
            conn.execute(
                "UPDATE tasks SET status = 'completed', result = ?, completed_at = ? WHERE id = ?",
                (result[:5000], datetime.now(timezone.utc).isoformat(), task_id)
            )
            conn.execute(
                "INSERT INTO activities (type, title, description) VALUES (?, ?, ?)",
                ("task", f"AI concluiu ({provider}): {cmd.command[:60]}", result[:200])
            )
            conn.commit()
        finally:
            conn.close()

        return {"task_id": task_id, "status": "completed", "result": result[:5000], "provider": provider}

    except Exception as e:
        conn = get_db()
        try:
            conn.execute("UPDATE tasks SET status = 'failed', result = ? WHERE id = ?", (str(e)[:500], task_id))
            conn.commit()
        finally:
            conn.close()
        return {"task_id": task_id, "status": "error", "result": str(e)[:500]}


# --- Agent Zero Direct Endpoints ---

@app.get("/api/agent-zero/status")
async def agent_zero_status():
    """Check Agent Zero availability and info."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{AGENT_ZERO_URL}/api/health")
            online = resp.status_code == 200
    except Exception:
        online = False

    # Check Ollama models
    ollama_models = []
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{AGENT_ZERO_URL.rsplit(':', 1)[0]}:11434/api/tags")
            if resp.status_code == 200:
                ollama_models = [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        pass

    return {
        "online": online,
        "url": AGENT_ZERO_URL,
        "ollama_models": ollama_models,
        "context_id": _agent_zero_context_id,
    }


class AgentZeroChatRequest(BaseModel):
    message: str
    context_id: Optional[str] = None


@app.post("/api/agent-zero/chat")
async def agent_zero_chat(req: AgentZeroChatRequest):
    """Direct chat with Agent Zero."""
    try:
        result = await call_agent_zero(req.message, req.context_id or "", timeout=300)
        return result
    except Exception as e:
        raise HTTPException(503, f"Agent Zero indisponivel: {e}")


# --- Audit ---

@app.post("/api/audit/start")
async def start_audit(config: AuditConfig):
    """Start batch audit on VM."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{VM_API_URL}/api/audit/start?batch_size={config.batch_size}&stage={config.stage}"
            )
            if r.status_code == 200:
                return r.json()
            return {"status": "error", "detail": f"VM returned {r.status_code}"}
    except Exception as e:
        raise HTTPException(502, f"Could not reach VM: {e}")


@app.get("/api/audit/status")
async def audit_status():
    """Get audit batch progress from VM."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{VM_API_URL}/api/audit/status")
            if r.status_code == 200:
                return r.json()
    except Exception:
        pass
    return {"running": False, "total": 0, "done": 0, "results": [], "errors": []}


@app.post("/api/audit/prospect/{prospect_id}")
async def audit_single_prospect(prospect_id: int):
    """Audit a single prospect via VM."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{VM_API_URL}/api/audit/prospect/{prospect_id}")
            if r.status_code == 200:
                return r.json()
            return {"status": "error", "detail": f"VM returned {r.status_code}"}
    except Exception as e:
        raise HTTPException(502, f"Could not reach VM: {e}")


# --- Work Queue ---

@app.get("/api/workqueue")
async def get_work_queue(limit: int = 20):
    """Generate prioritized daily work queue.

    Priority order:
    1. Audited prospects with score >= 70 that have no outreach yet
    2. Discovered prospects without website (ready to audit)
    3. Prospects with outreach ready but not sent
    """
    conn = get_db()
    try:
        queue = []

        # 1. High-score audited — ready for outreach generation
        rows = conn.execute("""
            SELECT * FROM prospects
            WHERE stage = 'audited' AND score >= 70
                AND (outreach_message IS NULL OR outreach_message = '')
            ORDER BY score DESC LIMIT ?
        """, (limit,)).fetchall()
        for r in rows:
            queue.append({**dict(r), "action": "generate_outreach", "action_label": "Gerar Proposta",
                          "priority": "high", "reason": f"Score {r['score']} — pronto para abordagem"})

        # 2. Outreach ready but not sent
        rows2 = conn.execute("""
            SELECT * FROM prospects
            WHERE stage = 'outreach' AND outreach_status = 'ready'
                AND outreach_message IS NOT NULL AND outreach_message != ''
            ORDER BY score DESC LIMIT ?
        """, (limit,)).fetchall()
        for r in rows2:
            queue.append({**dict(r), "action": "send_outreach", "action_label": "Enviar WhatsApp",
                          "priority": "high", "reason": "Proposta pronta — enviar agora"})

        # 3. Top unaudited prospects
        rows3 = conn.execute("""
            SELECT * FROM prospects
            WHERE stage IN ('discovered', 'new')
                AND (audit_summary IS NULL OR audit_summary = '')
                AND has_website = 0
            ORDER BY google_reviews DESC, google_rating DESC LIMIT ?
        """, (limit,)).fetchall()
        for r in rows3:
            rating = r['google_rating'] or 0
            reviews = r['google_reviews'] or 0
            queue.append({**dict(r), "action": "audit", "action_label": "Auditar",
                          "priority": "medium", "reason": f"Sem site — {rating}/5 ({reviews} reviews)"})

        return {"queue": queue[:limit * 2], "total": len(queue)}
    finally:
        conn.close()


@app.post("/api/outreach/generate/{prospect_id}")
async def generate_outreach_for_prospect(prospect_id: int):
    """Generate outreach message for a prospect via VM pipeline."""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Prospect not found")
        p = dict(row)
    finally:
        conn.close()

    # Try to generate via VM
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{VM_API_URL}/api/prospects/{p.get('vm_id', prospect_id)}/outreach")
            if r.status_code == 200:
                data = r.json()
                conn = get_db()
                try:
                    conn.execute("""
                        UPDATE prospects SET
                            outreach_message = ?, outreach_status = 'ready',
                            stage = 'outreach', updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (data.get("whatsapp_message", ""), prospect_id))
                    conn.execute(
                        "INSERT INTO activities (type, title, description, prospect_id) VALUES (?,?,?,?)",
                        ("outreach", f"Proposta gerada: {p.get('business_name', p.get('name', '?'))}",
                         f"Servicos: {', '.join(data.get('recommended_services', [])[:3])}", prospect_id)
                    )
                    conn.commit()
                finally:
                    conn.close()
                return data
    except Exception:
        pass

    # Fallback: generate locally using template
    has_site = bool(p.get("website"))
    name = p.get("business_name") or p.get("name", "")
    city = p.get("city", "Cuiaba")
    category = (p.get("category") or "negocio").lower()
    rating = p.get("google_rating")
    reviews = p.get("google_reviews", 0)

    if not has_site:
        msg = f"Ola! Me chamo Caio Leao, designer e estrategista digital em {city}.\n\n"
        msg += f"Encontrei o(a) *{name}* no Google Maps"
        if rating and rating >= 4.0:
            msg += f" e vi a avaliacao excelente ({rating}/5 com {reviews} avaliacoes)!"
        msg += f".\n\nNotei que voces ainda nao tem site — isso e uma grande oportunidade! "
        msg += f"Posso ajudar o(a) {name} a aparecer no topo do Google e atrair mais clientes.\n\n"
        msg += "Posso enviar exemplos do meu trabalho? Sem compromisso!\n\nCaio Leao\nDesigner & Estrategista Digital"
    else:
        msg = f"Ola! Sou Caio Leao, designer e estrategista digital em {city}.\n\n"
        msg += f"Analisei a presenca digital do(a) *{name}* e identifiquei oportunidades de melhoria.\n\n"
        msg += "Posso compartilhar uma analise gratuita?\n\nCaio Leao\nDesigner & Estrategista Digital"

    conn = get_db()
    try:
        conn.execute("""
            UPDATE prospects SET
                outreach_message = ?, outreach_status = 'ready',
                stage = 'outreach', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (msg, prospect_id))
        conn.execute(
            "INSERT INTO activities (type, title, description, prospect_id) VALUES (?,?,?,?)",
            ("outreach", f"Proposta gerada: {name}", f"Template local — {category}", prospect_id)
        )
        conn.commit()
    finally:
        conn.close()

    return {"whatsapp_message": msg, "prospect_id": prospect_id, "source": "template"}


# --- Photo Proxy with Cache ---

@app.get("/api/photos/{photo_ref:path}")
async def proxy_photo(photo_ref: str, maxHeight: int = 400):
    """Fetch Google Maps photo and cache locally. Supports both gosom direct URLs and Places API refs."""
    cache_key = hashlib.md5(f"{photo_ref}_{maxHeight}".encode()).hexdigest()
    cache_path = PHOTO_CACHE_DIR / f"{cache_key}.jpg"

    if cache_path.exists():
        return FileResponse(cache_path, media_type="image/jpeg")

    # Gosom scraper provides direct Google Photos URLs (lh3.googleusercontent.com)
    if photo_ref.startswith("http"):
        url = photo_ref
        if "=" in url and "googleusercontent.com" in url:
            url = url.rsplit("=", 1)[0] + f"=w{maxHeight}-h{maxHeight}-k-no"
    elif GOOGLE_API_KEY:
        url = f"https://places.googleapis.com/v1/{photo_ref}/media?maxHeightPx={maxHeight}&key={GOOGLE_API_KEY}"
    else:
        raise HTTPException(503, "Photo not available")

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                cache_path.write_bytes(r.content)
                return Response(content=r.content, media_type="image/jpeg")
            else:
                raise HTTPException(r.status_code, "Photo fetch failed")
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Photo proxy error: {e}")


# --- Scraper Status & Control ---

@app.get("/api/scraper/status")
async def scraper_status():
    """Get night scraper status from VM, with cached fallback."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{VM_API_URL}/api/scraper/status")
            if r.status_code == 200:
                data = r.json()
                # Cache for offline access
                conn = get_db()
                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES ('scraper_cache', ?, ?)",
                        (json.dumps(data), datetime.now(timezone.utc).isoformat())
                    )
                    conn.commit()
                finally:
                    conn.close()
                return data
    except Exception:
        pass

    # Fallback: return cached scraper status
    conn = get_db()
    try:
        row = conn.execute("SELECT value FROM sync_state WHERE key = 'scraper_cache'").fetchone()
        if row:
            return json.loads(row[0])
    finally:
        conn.close()

    return {
        "running": False,
        "current_city": None,
        "category_index": 0,
        "total_categories": 0,
        "stats": {
            "total_new": 0, "with_website": 0, "without_website": 0,
            "skipped_dupes": 0, "audit_tasks_created": 0, "outreach_tasks_created": 0,
            "cities_completed": [], "errors": [],
        },
        "log_tail": [],
    }


@app.post("/api/scraper/start")
async def start_scraper(config: ScraperConfig):
    """Start the night scraper on the VM."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{VM_API_URL}/api/scraper/start", json=config.model_dump())
            if r.status_code == 200:
                return r.json()
            return {"status": "error", "detail": f"VM returned {r.status_code}"}
    except Exception as e:
        raise HTTPException(502, f"Could not reach VM: {e}")


@app.post("/api/scraper/stop")
async def stop_scraper():
    """Stop the running scraper on the VM."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{VM_API_URL}/api/scraper/stop")
            if r.status_code == 200:
                return r.json()
            return {"status": "error", "detail": f"VM returned {r.status_code}"}
    except Exception as e:
        raise HTTPException(502, f"Could not reach VM: {e}")


@app.get("/api/scraper/history")
async def scraper_history():
    """Get past scraper run reports from VM."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{VM_API_URL}/api/scraper/history")
            if r.status_code == 200:
                return r.json()
    except Exception:
        pass
    return {"runs": []}


AVAILABLE_CITIES = [
    "Cuiaba", "Varzea Grande", "Rondonopolis", "Sinop", "Tangara da Serra",
    "Caceres", "Sorriso", "Lucas do Rio Verde", "Primavera do Leste",
    "Barra do Garcas", "Nova Mutum", "Campo Verde", "Chapada dos Guimaraes",
    "Pocone", "Nossa Senhora do Livramento", "Santo Antonio de Leverger",
]

NEIGHBOR_CITIES = [
    "Cuiaba", "Varzea Grande", "Chapada dos Guimaraes", "Pocone",
    "Nossa Senhora do Livramento", "Santo Antonio de Leverger", "Campo Verde",
]

PARSE_SYSTEM_PROMPT = """You are a scraper task parser for Hermes, a B2B prospecting tool in Mato Grosso, Brazil.
Given a natural language request in Portuguese, extract a structured scraper configuration.

Available cities: {cities}
Neighbor cities (Cuiaba + nearby): {neighbors}

Respond ONLY with valid JSON, no markdown, no explanation:
{{
  "search_terms": ["term1", "term2", ...],
  "cities": ["City1", "City2", ...] or null for all 16,
  "only_no_site": true/false,
  "explanation": "Brief explanation in Portuguese of what will be searched"
}}

Rules:
- search_terms: Google Places Text Search queries that match the user's intent. Be creative with variations. 5-10 terms.
- cities: Match user intent to city list. "cidades proximas/vizinhanca" = neighbor cities. "todas" = null. Specific city names = list them.
- only_no_site: true if user explicitly wants businesses WITHOUT websites.
- Keep search_terms in Portuguese, as they search Google Maps in Brazil."""


@app.post("/api/scraper/parse-prompt")
async def parse_scraper_prompt(body: ScraperPrompt):
    """Parse a natural language prompt into structured scraper config using AI."""
    system = PARSE_SYSTEM_PROMPT.format(
        cities=", ".join(AVAILABLE_CITIES),
        neighbors=", ".join(NEIGHBOR_CITIES),
    )
    full_prompt = f"{system}\n\nUser request: {body.prompt}"

    try:
        ai_result = await call_ai(full_prompt, timeout=60)
        output = ai_result["response"]

        # Extract JSON from output (handle potential markdown wrapping)
        json_str = output
        if "```" in json_str:
            import re
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", json_str, re.DOTALL)
            if match:
                json_str = match.group(1)

        parsed = json.loads(json_str)

        return {
            "status": "ok",
            "config": {
                "search_terms": parsed.get("search_terms", []),
                "cities": parsed.get("cities"),
                "only_no_site": parsed.get("only_no_site", False),
            },
            "explanation": parsed.get("explanation", ""),
            "original_prompt": body.prompt,
            "provider": ai_result.get("provider", "unknown"),
        }
    except json.JSONDecodeError as e:
        raise HTTPException(422, f"Nao foi possivel parsear resposta AI como JSON: {e}\nRaw: {output[:500]}")
    except Exception as e:
        raise HTTPException(500, f"Erro ao interpretar prompt: {e}")


# --- Pipeline Stats ---

@app.get("/api/stats")
async def get_stats(days: int = 7):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM pipeline_stats ORDER BY date DESC LIMIT ?", (days,)
        ).fetchall()
        return {"stats": [dict(r) for r in rows]}
    finally:
        conn.close()


# --- Pipeline Builder ---

@app.get("/api/pipelines")
async def list_pipelines():
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM pipeline_templates ORDER BY updated_at DESC").fetchall()
        templates = []
        for r in rows:
            t = dict(r)
            t["targets_config"] = json.loads(t["targets_config"]) if t["targets_config"] else {}
            t["schedule_config"] = json.loads(t["schedule_config"]) if t["schedule_config"] else {}
            exec_row = conn.execute(
                "SELECT * FROM pipeline_executions WHERE template_id = ? ORDER BY created_at DESC LIMIT 1",
                (t["id"],)
            ).fetchone()
            t["last_execution"] = dict(exec_row) if exec_row else None
            templates.append(t)
        return {"pipelines": templates}
    finally:
        conn.close()


@app.post("/api/pipelines")
async def create_pipeline(body: PipelineTemplateCreate):
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO pipeline_templates (name, type, description, prompt, targets_config, schedule_config)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (body.name, body.type, body.description, body.prompt,
             json.dumps(body.targets_config) if body.targets_config else None,
             json.dumps(body.schedule_config) if body.schedule_config else None)
        )
        conn.commit()
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        row = conn.execute("SELECT * FROM pipeline_templates WHERE id = ?", (pid,)).fetchone()
        result = dict(row)
        result["targets_config"] = json.loads(result["targets_config"]) if result["targets_config"] else {}
        result["schedule_config"] = json.loads(result["schedule_config"]) if result["schedule_config"] else {}
        return result
    finally:
        conn.close()


@app.get("/api/pipelines/{pipeline_id}")
async def get_pipeline(pipeline_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM pipeline_templates WHERE id = ?", (pipeline_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Pipeline not found")
        t = dict(row)
        t["targets_config"] = json.loads(t["targets_config"]) if t["targets_config"] else {}
        t["schedule_config"] = json.loads(t["schedule_config"]) if t["schedule_config"] else {}
        execs = conn.execute(
            "SELECT * FROM pipeline_executions WHERE template_id = ? ORDER BY created_at DESC LIMIT 10",
            (pipeline_id,)
        ).fetchall()
        t["executions"] = [dict(e) for e in execs]
        return t
    finally:
        conn.close()


@app.patch("/api/pipelines/{pipeline_id}")
async def update_pipeline(pipeline_id: int, body: PipelineTemplateUpdate):
    conn = get_db()
    try:
        existing = conn.execute("SELECT * FROM pipeline_templates WHERE id = ?", (pipeline_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Pipeline not found")
        updates = []
        params = []
        for field in ["name", "description", "prompt", "is_active"]:
            val = getattr(body, field, None)
            if val is not None:
                updates.append(f"{field} = ?")
                params.append(val)
        if body.targets_config is not None:
            updates.append("targets_config = ?")
            params.append(json.dumps(body.targets_config))
        if body.schedule_config is not None:
            updates.append("schedule_config = ?")
            params.append(json.dumps(body.schedule_config))
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(pipeline_id)
            conn.execute(f"UPDATE pipeline_templates SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        row = conn.execute("SELECT * FROM pipeline_templates WHERE id = ?", (pipeline_id,)).fetchone()
        result = dict(row)
        result["targets_config"] = json.loads(result["targets_config"]) if result["targets_config"] else {}
        result["schedule_config"] = json.loads(result["schedule_config"]) if result["schedule_config"] else {}
        return result
    finally:
        conn.close()


@app.delete("/api/pipelines/{pipeline_id}")
async def delete_pipeline(pipeline_id: int):
    conn = get_db()
    try:
        conn.execute("DELETE FROM pipeline_executions WHERE template_id = ?", (pipeline_id,))
        conn.execute("DELETE FROM pipeline_templates WHERE id = ?", (pipeline_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.post("/api/pipelines/{pipeline_id}/execute")
async def execute_pipeline(pipeline_id: int, body: PipelineExecuteRequest = None):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM pipeline_templates WHERE id = ?", (pipeline_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Pipeline not found")
        template = dict(row)
        targets = json.loads(template["targets_config"]) if template["targets_config"] else {}
        prompt = (body.override_prompt if body and body.override_prompt else template["prompt"]) or ""

        conn.execute(
            """INSERT INTO pipeline_executions (template_id, status, started_at)
               VALUES (?, 'running', CURRENT_TIMESTAMP)""",
            (pipeline_id,)
        )
        conn.commit()
        exec_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute(
            "UPDATE pipeline_templates SET last_run_at = CURRENT_TIMESTAMP, total_runs = total_runs + 1 WHERE id = ?",
            (pipeline_id,)
        )
        conn.commit()
    finally:
        conn.close()

    asyncio.create_task(_run_pipeline_async(pipeline_id, exec_id, template, targets, prompt))

    return {"execution_id": exec_id, "status": "running", "pipeline_id": pipeline_id}


async def _run_pipeline_async(pipeline_id: int, exec_id: int, template: dict, targets: dict, prompt: str):
    """Run pipeline in background, updating execution record as it progresses."""
    log_entries = []
    current_phase = {"name": "init", "step": 0, "total_steps": 0}

    def add_log(msg: str, level: str = "info", phase: str = None, step: int = None, total: int = None, detail: dict = None):
        entry = {"ts": datetime.now(timezone.utc).isoformat(), "msg": msg, "level": level}
        if phase:
            current_phase["name"] = phase
            entry["phase"] = phase
        else:
            entry["phase"] = current_phase["name"]
        if step is not None:
            current_phase["step"] = step
            entry["step"] = step
        if total is not None:
            current_phase["total_steps"] = total
            entry["total_steps"] = total
        if detail:
            entry["detail"] = detail
        log_entries.append(entry)
        conn = get_db()
        try:
            progress = 0
            if current_phase["total_steps"] > 0:
                progress = int((current_phase["step"] / current_phase["total_steps"]) * 100)
            conn.execute(
                "UPDATE pipeline_executions SET log = ?, progress = ?, processed_items = ? WHERE id = ?",
                (json.dumps(log_entries), progress, current_phase["step"], exec_id)
            )
            conn.commit()
        finally:
            conn.close()

    try:
        pipeline_type = template.get("type", "custom")
        add_log(f"Pipeline '{template['name']}' iniciado", phase="starting",
                detail={"type": pipeline_type, "template_id": pipeline_id})

        if pipeline_type == "linkedin_viewer":
            await _execute_linkedin_viewer(exec_id, targets, prompt, add_log)
        elif pipeline_type == "scraper":
            add_log("Conectando ao Hermes VM...", phase="connecting")
            add_log("Enviando configuracao de scraping...", phase="dispatching")
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(f"{VM_API_URL}/api/scraper/start", json=targets)
                if r.status_code == 200:
                    add_log("Scraper iniciado com sucesso no Hermes", phase="running", detail={"vm_response": r.status_code})
                else:
                    add_log(f"Falha ao iniciar scraper: HTTP {r.status_code}", level="error", phase="error")
        elif pipeline_type == "audit":
            add_log("Iniciando auditoria em batch...", phase="connecting")
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(f"{VM_API_URL}/api/audit/batch", json=targets)
                add_log(f"Auditoria batch: HTTP {r.status_code}", phase="running")
        elif pipeline_type == "outreach":
            add_log("Gerando mensagens de outreach...", phase="connecting")
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(f"{VM_API_URL}/api/outreach/batch", json=targets)
                add_log(f"Outreach batch: HTTP {r.status_code}", phase="running")
        else:
            add_log("Analisando demanda com Agent Zero...", phase="analyzing")
            add_log(f"Prompt: {prompt[:200]}", level="debug")
            try:
                ai_result = await call_ai(prompt, timeout=300)
                output = ai_result["response"]
                provider = ai_result["provider"]
                add_log(f"AI respondeu ({provider}): {output[:500]}", phase="completed")
            except Exception as e:
                add_log(f"Erro AI: {e}", level="error", phase="error")

        conn = get_db()
        try:
            conn.execute(
                "UPDATE pipeline_executions SET status = 'completed', completed_at = CURRENT_TIMESTAMP, progress = 100, log = ? WHERE id = ?",
                (json.dumps(log_entries), exec_id)
            )
            conn.commit()
        finally:
            conn.close()
        add_log("Pipeline concluido com sucesso", phase="done")

    except Exception as e:
        add_log(f"Pipeline falhou: {e}", level="error", phase="failed")
        conn = get_db()
        try:
            conn.execute(
                "UPDATE pipeline_executions SET status = 'failed', completed_at = CURRENT_TIMESTAMP, log = ? WHERE id = ?",
                (json.dumps(log_entries), exec_id)
            )
            conn.commit()
        finally:
            conn.close()


async def _execute_linkedin_viewer(exec_id: int, targets: dict, prompt: str, add_log):
    """Execute LinkedIn profile viewer pipeline via Hermes VM."""
    import random

    roles = targets.get("roles", ["tech recruiter", "project manager", "SMB owner"])
    max_profiles = targets.get("max_profiles", 500)
    location = targets.get("location", "Brazil")

    add_log("Preparando plano de execucao...", phase="planning",
            detail={"roles": roles, "location": location, "max_profiles": max_profiles})

    conn = get_db()
    try:
        conn.execute(
            "UPDATE pipeline_executions SET total_items = ? WHERE id = ?",
            (max_profiles, exec_id)
        )
        conn.commit()
    finally:
        conn.close()

    add_log(f"Alvos: {', '.join(roles)}", phase="planning", step=1, total=5)
    add_log(f"Regiao: {location} | Limite: {max_profiles} perfis", phase="planning")

    add_log("Conectando ao Hermes VM...", phase="connecting", step=2, total=5)

    # --- Try real LinkedIn viewer (Patchright anti-detection) ---
    result_data = None
    try:
        from linkedin import LinkedInViewer, LinkedInConfig
        li_config = LinkedInConfig(
            account_email=os.environ.get("LINKEDIN_EMAIL", ""),
            account_type=os.environ.get("LINKEDIN_ACCOUNT_TYPE", "free"),
            proxy_server=os.environ.get("LINKEDIN_PROXY", None),
            proxy_username=os.environ.get("LINKEDIN_PROXY_USER", None),
            proxy_password=os.environ.get("LINKEDIN_PROXY_PASS", None),
            headless=True,
        )
        li_config.targets = {"roles": roles, "location": location, "max_profiles": max_profiles}

        viewer = LinkedInViewer(li_config)
        viewer.set_log_callback(lambda msg, **kw: add_log(msg, **kw))

        add_log("LinkedIn Viewer real ativo — Patchright anti-deteccao", phase="authenticating", step=3, total=5)
        result_data = await viewer.start()
        add_log(f"Viewer real concluiu: {result_data.get('profiles_visited', 0)} perfis", phase="monitoring", step=5, total=5)

    except ImportError:
        add_log("LinkedIn module nao instalado — pip install patchright | usando simulacao", level="warn",
                phase="dispatched", step=3, total=5)
    except Exception as e:
        add_log(f"Viewer real falhou: {str(e)[:100]} — fallback simulacao", level="warn",
                phase="dispatched", step=3, total=5)

    # --- Fallback: try VM ---
    if not result_data:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                add_log("Tentando via Hermes VM...", phase="authenticating", step=3, total=5)
                r = await client.post(
                    f"{VM_API_URL}/api/pipeline/execute",
                    json={"type": "linkedin_viewer", "config": {
                        "roles": roles, "max_profiles": max_profiles,
                        "location": location, "prompt": prompt,
                    }}
                )
                if r.status_code == 200:
                    result_data = r.json()
                    add_log("VM executou com sucesso", phase="searching", step=4, total=5)
                else:
                    add_log(f"VM HTTP {r.status_code}", level="warn", phase="dispatched", step=4, total=5)
        except Exception:
            add_log("VM inacessivel — modo simulacao", level="warn", phase="offline", step=4, total=5)

    # --- Fallback: simulation ---
    if not result_data or "profiles" not in result_data:
        add_log("Gerando resultados de demonstracao...", phase="processing")
        first_names = ["Ana", "Bruno", "Carlos", "Diana", "Eduardo", "Fernanda", "Gabriel", "Helena",
                       "Igor", "Julia", "Lucas", "Mariana", "Nicolas", "Olivia", "Pedro", "Rafaela",
                       "Samuel", "Tatiana", "Victor", "Amanda", "Diego", "Camila", "Thiago", "Larissa",
                       "Felipe", "Bianca", "Ricardo", "Patricia", "Matheus", "Vanessa"]
        last_names = ["Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Almeida",
                      "Nascimento", "Lima", "Araujo", "Pereira", "Barbosa", "Ribeiro", "Carvalho",
                      "Gomes", "Martins", "Rocha", "Costa", "Freitas", "Moreira"]
        titles_by_role = {
            "tech recruiter": ["Tech Recruiter", "IT Recruiter Senior", "Talent Acquisition Tech",
                               "Recrutador de TI", "Head of Tech Recruiting", "Tech Sourcer"],
            "project manager": ["Project Manager", "Gerente de Projetos", "PM Senior", "Scrum Master",
                                "Delivery Manager", "Program Manager", "Tech Lead PM"],
            "SMB owner": ["CEO", "Fundador", "Diretor", "Socio-Diretor", "Owner",
                          "Managing Director", "Co-Founder & CTO"],
        }
        companies = ["Nubank", "iFood", "Stone", "TOTVS", "Movile", "Loggi", "QuintoAndar",
                     "Loft", "Creditas", "Gympass", "Wildlife", "PagSeguro", "Locaweb", "VTEX",
                     "RD Station", "Hotmart", "CI&T", "Accenture Brasil", "ThoughtWorks",
                     "Stefanini", "Wipro", "TCS Brasil", "Capgemini", "BairesDev",
                     "Mercado Livre", "Itau", "Bradesco", "XP Inc", "BTG Pactual", "Ambev Tech"]
        cities = ["Sao Paulo", "Rio de Janeiro", "Curitiba", "Belo Horizonte", "Porto Alegre",
                  "Florianopolis", "Brasilia", "Campinas", "Recife", "Salvador"]

        num_profiles = min(random.randint(80, 200), max_profiles)
        profiles = []
        by_role = {}
        for i in range(num_profiles):
            role = random.choice(roles)
            by_role[role] = by_role.get(role, 0) + 1
            fname = random.choice(first_names)
            lname = random.choice(last_names)
            name = f"{fname} {lname}"
            slug = f"{fname.lower()}-{lname.lower()}-{random.randint(1000,9999)}"
            title = random.choice(titles_by_role.get(role, ["Professional"]))
            company = random.choice(companies)
            city = random.choice(cities)
            profiles.append({
                "name": f"[SIM] {name}",
                "title": title,
                "company": company,
                "city": city,
                "role_match": role,
                "url": f"https://linkedin.com/in/{slug}",
                "visited": True,
                "visited_at": datetime.now(timezone.utc).isoformat(),
                "simulated": True,
            })

            if (i + 1) % 25 == 0:
                add_log(f"Visitados {i + 1}/{num_profiles} perfis...", phase="visiting",
                        step=4, total=5)
                conn = get_db()
                try:
                    conn.execute(
                        "UPDATE pipeline_executions SET processed_items = ?, progress = ? WHERE id = ?",
                        (i + 1, int(((i + 1) / num_profiles) * 100), exec_id)
                    )
                    conn.commit()
                finally:
                    conn.close()
                await asyncio.sleep(0.1)

        result_data = {
            "type": "linkedin_viewer",
            "simulated": True,
            "profiles_visited": num_profiles,
            "profiles_found": num_profiles + random.randint(50, 200),
            "by_role": by_role,
            "by_city": {},
            "profiles": profiles,
        }
        for p in profiles:
            c = p["city"]
            result_data["by_city"][c] = result_data["by_city"].get(c, 0) + 1

        add_log(f"Concluido: {num_profiles} perfis visitados", phase="monitoring", step=5, total=5,
                detail={"profiles_visited": num_profiles, "by_role": by_role})

    conn = get_db()
    try:
        conn.execute(
            "UPDATE pipeline_executions SET result = ?, processed_items = ?, progress = 100 WHERE id = ?",
            (json.dumps(result_data), result_data.get("profiles_visited", 0), exec_id)
        )
        conn.commit()
    finally:
        conn.close()

    return result_data


@app.get("/api/linkedin/rate-limits")
async def linkedin_rate_limits():
    """Get current LinkedIn rate limiter stats and warm-up progress."""
    try:
        from linkedin import LinkedInConfig
        from linkedin.limiter import RateLimiter
        config = LinkedInConfig(
            account_email=os.environ.get("LINKEDIN_EMAIL", "default"),
            account_type=os.environ.get("LINKEDIN_ACCOUNT_TYPE", "free"),
        )
        limiter = RateLimiter(config)
        return limiter.get_stats()
    except ImportError:
        return {"error": "LinkedIn module not installed", "warmup_multiplier": 0}


# ─────────────────────────────────────────────────────────────────────────────
# LINKEDIN CAMPAIGN ENDPOINTS  (proxy → VM for execution)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/linkedin/status")
async def linkedin_status():
    """Session health + rate limits — proxied from VM (authoritative source)."""
    # Try VM first — VM has the actual session file + limiter DB
    vm_session = None
    vm_rate = None
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            sess_r, rate_r = await asyncio.gather(
                client.get(f"{VM_API_URL}/api/linkedin/session-check"),
                client.get(f"{VM_API_URL}/api/linkedin/rate-limits"),
                return_exceptions=True,
            )
            if hasattr(sess_r, "json"):
                vm_session = sess_r.json()
            if hasattr(rate_r, "json"):
                vm_rate = rate_r.json()
    except Exception:
        pass

    if vm_session is not None:
        return {
            "session_ok": vm_session.get("ok", False),
            "account_email": vm_session.get("email") or os.environ.get("LINKEDIN_EMAIL", ""),
            "account_type": vm_session.get("account_type") or os.environ.get("LINKEDIN_ACCOUNT_TYPE", "free"),
            "proxy_configured": vm_session.get("proxy_configured", False),
            "proxy_url": vm_session.get("proxy_url"),
            "proxy_alive": vm_session.get("proxy_alive", False),
            "rate_limits": vm_rate or {},
            "source": "vm",
        }

    # VM unreachable — fallback to local guess
    try:
        from linkedin import LinkedInConfig
        from linkedin.limiter import RateLimiter
        config = LinkedInConfig(
            account_email=os.environ.get("LINKEDIN_EMAIL", "default"),
            account_type=os.environ.get("LINKEDIN_ACCOUNT_TYPE", "free"),
        )
        limiter = RateLimiter(config)
        stats = limiter.get_stats()
        return {
            "session_ok": False,
            "account_email": os.environ.get("LINKEDIN_EMAIL", ""),
            "account_type": os.environ.get("LINKEDIN_ACCOUNT_TYPE", "free"),
            "proxy_alive": False,
            "rate_limits": stats,
            "source": "local_fallback",
            "warning": "VM unreachable",
        }
    except Exception as e:
        return {"error": str(e), "session_ok": False, "source": "error"}


@app.post("/api/linkedin/campaigns/{campaign_id}/cancel")
async def linkedin_cancel_scheduled(campaign_id: int):
    """Cancel a scheduled campaign before it fires."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT status FROM linkedin_campaigns WHERE id=?", (campaign_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Campaign not found")
        if row["status"] != "scheduled":
            return {"ok": False, "error": f"Campaign #{campaign_id} is not scheduled (status={row['status']})"}
        conn.execute(
            "UPDATE linkedin_campaigns SET status='cancelled', completed_at=?, "
            "log=COALESCE(log, '[]') WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), campaign_id)
        )
        # Append cancel log entry
        cur = conn.execute("SELECT log FROM linkedin_campaigns WHERE id=?", (campaign_id,)).fetchone()
        logs = json.loads(cur["log"]) if cur and cur["log"] else []
        logs.append({
            "time": datetime.now(timezone.utc).isoformat(),
            "phase": "cancelled",
            "msg": "Agendamento cancelado pelo usuário",
        })
        conn.execute("UPDATE linkedin_campaigns SET log=? WHERE id=?", (json.dumps(logs), campaign_id))
        conn.commit()
    finally:
        conn.close()
    try:
        await ws_manager.broadcast({
            "type": "linkedin_progress",
            "data": {"campaign_id": campaign_id, "status": "cancelled",
                     "msg": "Agendamento cancelado pelo usuário"}
        })
    except Exception:
        pass
    return {"ok": True, "campaign_id": campaign_id, "status": "cancelled"}


@app.post("/api/internal/account_type_set")
async def account_type_set(request: Request):
    """Receive an account_type detected by the browser extension (content script).
    Forwards to VM which updates its cache (~/.hermes/data/linkedin_account_type.json).
    """
    if request.client.host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(403, "internal endpoint")
    body = await request.json()
    account_type = (body.get("account_type") or "").strip()
    if account_type not in ("free", "premium", "sales_navigator"):
        raise HTTPException(400, "invalid account_type")
    token = os.environ.get("HERMES_VM_AUTH_TOKEN", "")
    if not token:
        return {"ok": False, "error": "HERMES_VM_AUTH_TOKEN not set on PC"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{VM_API_URL}/api/internal/account_type_set",
                json={
                    "account_type": account_type,
                    "evidence": body.get("evidence", []),
                    "detected_from": body.get("detected_from", "extension"),
                    "page_url": body.get("page_url"),
                },
                headers={"X-Hermes-Token": token},
            )
            vm_data = r.json() if r.status_code == 200 else {"ok": False}
    except Exception as e:
        return {"ok": False, "error": f"VM forward failed: {e}"}
    if vm_data.get("ok"):
        try:
            await ws_manager.broadcast({"type": "linkedin_account_type_updated", "account_type": account_type})
        except Exception:
            pass
    return vm_data


@app.post("/api/internal/li_at_rotate")
async def rotate_li_at(request: Request):
    """Receive a new li_at cookie from the local sync script and forward to VM.

    The script (scripts/li_at_sync.py) reads Chrome's cookie DB once a day.
    Only accepts 127.0.0.1 (same-host). Also broadcasts a status reload event.
    """
    if request.client.host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(403, "internal endpoint")
    body = await request.json()
    li_at = (body.get("li_at") or "").strip()
    if not li_at or len(li_at) < 30:
        raise HTTPException(400, "li_at missing or too short")
    # Forward to VM with shared-secret header
    token = os.environ.get("HERMES_VM_AUTH_TOKEN", "")
    if not token:
        return {"ok": False, "error": "HERMES_VM_AUTH_TOKEN not set on PC"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{VM_API_URL}/api/internal/li_at_update",
                json={"li_at": li_at},
                headers={"X-Hermes-Token": token},
            )
            vm_ok = r.status_code == 200 and r.json().get("ok")
            if not vm_ok:
                return {"ok": False, "vm_status": r.status_code, "vm_body": r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": f"VM forward failed: {e}"}
    if vm_ok:
        try:
            await ws_manager.broadcast({"type": "linkedin_session_rotated"})
        except Exception:
            pass
    return {"ok": vm_ok}


@app.post("/api/internal/linkedin/event")
async def receive_linkedin_event(request: Request):
    """VM-only callback: VM hermes_api.py pushes progress events here.

    Updates local DB partial_results + broadcasts WS event linkedin_progress.
    Only accepts requests from 127.0.0.1 (SSH tunnel makes VM appear as localhost).
    """
    if request.client.host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(403, "internal endpoint")
    body = await request.json()
    cid = body.get("campaign_id")
    if not cid:
        return {"ok": False}
    # Update DB with partial_results / progress
    try:
        conn = get_db()
        if body.get("partial_results") is not None or body.get("progress") is not None:
            conn.execute("""
                UPDATE linkedin_campaigns
                SET results = COALESCE(?, results),
                    progress = COALESCE(?, progress)
                WHERE id = ?
            """, (
                json.dumps(body["partial_results"]) if body.get("partial_results") else None,
                body.get("progress"),
                cid,
            ))
            conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"internal event DB update failed: {e}")
    # Broadcast
    try:
        await ws_manager.broadcast({"type": "linkedin_progress", "data": body})
    except Exception:
        pass
    return {"ok": True}


@app.post("/api/linkedin/auth")
async def linkedin_trigger_auth():
    """Trigger LinkedIn auth on VM (opens browser for session establishment)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{VM_API_URL}/api/linkedin/auth")
            return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/linkedin/campaigns")
async def list_linkedin_campaigns(limit: int = 20, offset: int = 0):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM linkedin_campaigns ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM linkedin_campaigns").fetchone()[0]
        campaigns = []
        for r in rows:
            c = dict(r)
            c["config"] = json.loads(c["config"]) if c.get("config") else {}
            c["results"] = json.loads(c["results"]) if c.get("results") else None
            c["log"] = json.loads(c["log"]) if c.get("log") else []
            campaigns.append(c)
        return {"campaigns": campaigns, "total": total}
    finally:
        conn.close()


@app.get("/api/linkedin/campaigns/{campaign_id}/log")
async def get_campaign_log(campaign_id: int):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, type, status, progress, total, log, results FROM linkedin_campaigns WHERE id=?",
            (campaign_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Campaign not found")
        c = dict(row)
        c["log"] = json.loads(c["log"]) if c.get("log") else []
        c["results"] = json.loads(c["results"]) if c.get("results") else None
        return c
    finally:
        conn.close()


@app.post("/api/linkedin/campaigns/{campaign_id}/stop")
async def stop_linkedin_campaign(campaign_id: int):
    """Signal VM to stop a running campaign."""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE linkedin_campaigns SET status='stopped', completed_at=? WHERE id=? AND status='running'",
            (datetime.now(timezone.utc).isoformat(), campaign_id)
        )
        conn.commit()
    finally:
        conn.close()

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{VM_API_URL}/api/linkedin/campaigns/{campaign_id}/stop")
            return r.json()
    except Exception:
        return {"ok": True, "note": "VM unreachable but local status updated"}


async def _compute_schedule_state() -> tuple:
    """Probes VM for current gate state and returns (scheduled_for_iso, reasons[]).

    Returns (None, []) if all 3 gates are clear — campaign can dispatch now.
    Otherwise returns the LATEST ISO timestamp among the active gates, plus
    a list of human-readable reasons (PT-BR).
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            hr, rl = await asyncio.gather(
                client.get(f"{VM_API_URL}/api/linkedin/health"),
                client.get(f"{VM_API_URL}/api/linkedin/rate-limits"),
                return_exceptions=True,
            )
            health = hr.json() if hasattr(hr, "json") else {}
            ratel = rl.json() if hasattr(rl, "json") else {}
    except Exception:
        health, ratel = {}, {}

    candidates = []  # list of (datetime, reason_pt_BR)
    now = datetime.now(timezone.utc)

    # Gate 1: working hours
    if ratel.get("working_hours_ok") is False:
        next_win = ratel.get("next_working_window")
        if next_win:
            try:
                dt = datetime.fromisoformat(next_win)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                reason = ratel.get("working_hours_reason") or "fora do horário"
                candidates.append((dt.astimezone(timezone.utc), f"horário comercial ({reason})"))
            except Exception:
                pass

    # Gate 2: mandatory 30min spacing between launches
    next_launch = ratel.get("next_launch_in_seconds", 0) or 0
    if next_launch > 0:
        candidates.append((
            now + timedelta(seconds=next_launch),
            f"cooldown 30min entre launches ({(next_launch + 59)//60}min restantes)",
        ))

    # Gate 3: LinkedIn health (429/challenge/blocked)
    if health.get("state") and health.get("state") != "ok":
        retry = health.get("retry_after_seconds") or 0
        state = health.get("state")
        if retry > 0:
            candidates.append((
                now + timedelta(seconds=retry),
                f"LinkedIn {state} (HTTP {health.get('http_code', '?')})",
            ))
        else:
            # No explicit retry — probe is the source of truth, schedule for 5 min from now
            candidates.append((
                now + timedelta(minutes=5),
                f"LinkedIn {state} ({health.get('reason') or 'verificando recovery'})",
            ))

    if not candidates:
        return None, []

    # Pick LATEST timestamp (must wait until ALL gates are clear)
    latest_dt = max(c[0] for c in candidates)
    reasons = [c[1] for c in candidates]
    return latest_dt.isoformat(), reasons


async def _proxy_linkedin_campaign(campaign_type: str, config_data: dict) -> dict:
    """Create local campaign record and dispatch to VM for execution."""
    conn = get_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO linkedin_campaigns (type, config, status, started_at) VALUES (?,?,?,?)",
            (campaign_type, json.dumps(config_data), "pending", now)
        )
        campaign_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    # Broadcast new campaign so dashboard inserts it without F5
    try:
        await ws_manager.broadcast({
            "type": "linkedin_campaign_created",
            "data": {
                "id": campaign_id,
                "type": campaign_type,
                "status": "pending",
                "progress": 0,
                "total": 0,
                "config": config_data,
                "started_at": now,
                "log": [],
                "results": None,
            }
        })
    except Exception:
        pass

    # Compute scheduled_for if any of the 3 gates blocks immediate dispatch.
    # v6: never reject — always create row. If gated, status='scheduled' and the
    # scheduler loop fires when scheduled_for <= now() AND gates are clear.
    scheduled_for_iso, schedule_reasons = await _compute_schedule_state()
    if scheduled_for_iso:
        msg = " · ".join(schedule_reasons)
        conn_s = get_db()
        try:
            conn_s.execute(
                "UPDATE linkedin_campaigns SET status='scheduled', "
                "scheduled_for=?, schedule_reason=?, log=? WHERE id=?",
                (scheduled_for_iso, msg,
                 json.dumps([{"time": datetime.now(timezone.utc).isoformat(),
                              "phase": "scheduled", "msg": f"Agendada para {scheduled_for_iso} — {msg}"}]),
                 campaign_id)
            )
            conn_s.commit()
        finally:
            conn_s.close()
        try:
            await ws_manager.broadcast({
                "type": "linkedin_progress",
                "data": {"campaign_id": campaign_id, "status": "scheduled",
                         "scheduled_for": scheduled_for_iso,
                         "schedule_reason": msg}
            })
        except Exception:
            pass
        return {
            "ok": True, "campaign_id": campaign_id,
            "status": "scheduled", "scheduled_for": scheduled_for_iso,
            "schedule_reason": msg,
        }

    # Fire dispatch to VM. VM endpoint returns FAST ({ok, campaign_id}) —
    # actual work runs in VM's async task. We do NOT mark "done" from this response.
    # Completion is detected by linkedin_sync_loop() polling VM every 10s OR
    # by the internal event push from VM's _li_log.
    async def _dispatch():
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    f"{VM_API_URL}/api/linkedin/campaigns/{campaign_type}",
                    json={"campaign_id": campaign_id, **config_data},
                )
                ack = r.json() if r.status_code == 200 else {"ok": False}
                if not ack.get("ok"):
                    raise RuntimeError(f"VM rejected dispatch: HTTP {r.status_code} {r.text[:200]}")
                logger.info(f"Campaign {campaign_id} dispatched to VM (ack={ack})")
        except Exception as e:
            logger.error(f"LinkedIn campaign dispatch error: {e}")
            conn3 = get_db()
            try:
                conn3.execute(
                    "UPDATE linkedin_campaigns SET status='error', completed_at=?, "
                    "log=COALESCE(log, '[]') WHERE id=?",
                    (datetime.now(timezone.utc).isoformat(), campaign_id)
                )
                # Append error to log
                row = conn3.execute("SELECT log FROM linkedin_campaigns WHERE id=?", (campaign_id,)).fetchone()
                logs = json.loads(row["log"]) if row and row["log"] else []
                logs.append({
                    "time": datetime.now(timezone.utc).isoformat(),
                    "msg": f"Falha no dispatch: {e}",
                    "phase": "error",
                })
                conn3.execute("UPDATE linkedin_campaigns SET log=? WHERE id=?",
                              (json.dumps(logs), campaign_id))
                conn3.commit()
            finally:
                conn3.close()
            try:
                await ws_manager.broadcast({
                    "type": "linkedin_progress",
                    "data": {"campaign_id": campaign_id, "status": "error", "msg": str(e)}
                })
            except Exception:
                pass

    asyncio.create_task(_dispatch())
    return {"ok": True, "campaign_id": campaign_id, "status": "dispatched"}


@app.post("/api/linkedin/campaigns/view")
async def start_view_campaign(request: Request):
    data = await request.json()
    return await _proxy_linkedin_campaign("view", data)


@app.post("/api/linkedin/campaigns/engage")
async def start_engage_campaign(request: Request):
    data = await request.json()
    return await _proxy_linkedin_campaign("engage", data)


@app.post("/api/linkedin/campaigns/connect")
async def start_connect_campaign(request: Request):
    data = await request.json()
    return await _proxy_linkedin_campaign("connect", data)


@app.post("/api/linkedin/campaigns/discover")
async def start_discover_campaign(request: Request):
    data = await request.json()
    return await _proxy_linkedin_campaign("discover", data)


# ─── Fase 2 — proxy passthroughs to VM ─────────────────────────────────────

async def _vm_passthrough(method: str, path: str, json_body: dict = None,
                          params: dict = None, timeout: float = 30.0):
    """Generic VM passthrough helper."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.request(method, f"{VM_API_URL}{path}",
                                     json=json_body, params=params)
            return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/linkedin/comment/edit")
async def linkedin_comment_edit(request: Request):
    body = await request.json()
    return await _vm_passthrough("POST", "/api/linkedin/comment/edit", json_body=body, timeout=120)


@app.post("/api/linkedin/comment/delete")
async def linkedin_comment_delete(request: Request):
    body = await request.json()
    return await _vm_passthrough("POST", "/api/linkedin/comment/delete", json_body=body, timeout=120)


@app.get("/api/linkedin/visited")
async def linkedin_visited(limit: int = 100, days: int = 30):
    return await _vm_passthrough("GET", "/api/linkedin/visited",
                                  params={"limit": limit, "days": days})


@app.get("/api/linkedin/profiles")
async def linkedin_profile_by_url(url: str):
    return await _vm_passthrough("GET", "/api/linkedin/profiles",
                                  params={"url": url}, timeout=10)


@app.get("/api/linkedin/companies/lookup")
async def linkedin_company_lookup(name: str):
    return await _vm_passthrough("GET", "/api/linkedin/companies/lookup",
                                  params={"name": name})


@app.post("/api/linkedin/detect-account-type")
async def linkedin_detect_account_type():
    return await _vm_passthrough("POST", "/api/linkedin/detect-account-type", timeout=120)


@app.get("/api/linkedin/health")
async def linkedin_health(force_refresh: bool = False):
    """Pass-through to VM health probe. UI calls this to enable/disable launch buttons."""
    return await _vm_passthrough(
        "GET", "/api/linkedin/health",
        params={"force_refresh": str(force_refresh).lower()},
        timeout=20,
    )


@app.post("/api/linkedin/health/clear")
async def linkedin_health_clear():
    return await _vm_passthrough("POST", "/api/linkedin/health/clear", timeout=10)


@app.post("/api/linkedin/connection/refresh")
async def linkedin_connection_refresh(request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    return await _vm_passthrough("POST", "/api/linkedin/connection/refresh",
                                  json_body=body, timeout=600)


@app.get("/api/pipelines/{pipeline_id}/executions")
async def list_executions(pipeline_id: int, limit: int = 20):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM pipeline_executions WHERE template_id = ? ORDER BY created_at DESC LIMIT ?",
            (pipeline_id, limit)
        ).fetchall()
        execs = []
        for r in rows:
            e = dict(r)
            e["log"] = json.loads(e["log"]) if e["log"] else []
            e["result"] = json.loads(e["result"]) if e.get("result") else None
            execs.append(e)
        return {"executions": execs}
    finally:
        conn.close()


@app.get("/api/pipeline-executions/active")
async def get_active_executions():
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT e.*, t.name as pipeline_name, t.type as pipeline_type
               FROM pipeline_executions e
               JOIN pipeline_templates t ON e.template_id = t.id
               WHERE e.status IN ('pending', 'running')
               ORDER BY e.created_at DESC"""
        ).fetchall()
        recent = conn.execute(
            """SELECT e.*, t.name as pipeline_name, t.type as pipeline_type
               FROM pipeline_executions e
               JOIN pipeline_templates t ON e.template_id = t.id
               WHERE e.status IN ('completed', 'failed')
               ORDER BY e.completed_at DESC LIMIT 5"""
        ).fetchall()
        def parse_exec(r):
            e = dict(r)
            e["log"] = json.loads(e["log"]) if e["log"] else []
            e["result"] = json.loads(e["result"]) if e.get("result") else None
            return e
        return {
            "active": [parse_exec(r) for r in rows],
            "recent": [parse_exec(r) for r in recent],
        }
    finally:
        conn.close()


@app.get("/api/pipeline-executions/{exec_id}")
async def get_execution(exec_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM pipeline_executions WHERE id = ?", (exec_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Execution not found")
        e = dict(row)
        e["log"] = json.loads(e["log"]) if e["log"] else []
        e["result"] = json.loads(e["result"]) if e.get("result") else None
        return e
    finally:
        conn.close()


# --- Hermes VM Sync ---

# ─── Server control endpoints (header dot dropdown) ──────────────────────

@app.post("/api/server/restart-local")
async def server_restart_local():
    """Schedule a local server restart. Tauri's health loop or systemd respawns.
    On Windows (no systemd), we exit the process — Tauri's lib.rs health monitor
    detects port 55000 closed and re-launches `python server.py`.
    """
    async def _shutdown():
        await asyncio.sleep(0.5)
        os._exit(0)
    asyncio.create_task(_shutdown())
    return {"ok": True, "note": "processo encerrando — Tauri vai reiniciar em ~10s"}


@app.post("/api/server/shutdown-local")
async def server_shutdown_local():
    """Graceful shutdown of the local server (no auto-restart)."""
    # Mark a flag so Tauri health loop knows NOT to relaunch
    try:
        flag = HERMES_HOME / "data" / "no_relaunch.flag"
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text(datetime.now(timezone.utc).isoformat())
    except Exception:
        pass
    async def _shutdown():
        await asyncio.sleep(0.5)
        os._exit(0)
    asyncio.create_task(_shutdown())
    return {"ok": True, "note": "servidor desligando — fechar Tauri também"}


@app.post("/api/server/restart-vm")
async def server_restart_vm():
    """Restart hermes-api.service on the VM via SSH."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            "hermes-gcp@136.115.74.69",
            "systemctl --user restart hermes-api.service && echo OK",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        out = stdout.decode().strip()
        err = stderr.decode().strip()
        if "OK" in out:
            return {"ok": True, "note": "VM reiniciada"}
        return {"ok": False, "error": err or out or "comando falhou"}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "SSH timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/server/restart-all")
async def server_restart_all():
    """Restart VM first, then local (which auto-respawns via Tauri)."""
    vm_result = await server_restart_vm()
    if not vm_result.get("ok"):
        return {"ok": False, "error": f"VM falhou: {vm_result.get('error')}"}
    async def _shutdown():
        await asyncio.sleep(1.0)
        os._exit(0)
    asyncio.create_task(_shutdown())
    return {"ok": True, "note": "VM reiniciada + local reiniciando"}


@app.get("/api/hermes/status")
async def hermes_status():
    conn = get_db()
    try:
        last_sync = conn.execute("SELECT value FROM sync_state WHERE key = 'last_sync'").fetchone()
        vm_status = conn.execute("SELECT value FROM sync_state WHERE key = 'vm_status'").fetchone()
        total_synced = conn.execute("SELECT value FROM sync_state WHERE key = 'total_synced'").fetchone()
    finally:
        conn.close()

    status = {
        "vm_url": VM_API_URL,
        "vm_reachable": (vm_status[0] == "online") if vm_status else False,
        "last_sync": last_sync[0] if last_sync else None,
        "total_synced": int(total_synced[0]) if total_synced else 0,
        "sync_interval_seconds": SYNC_INTERVAL,
        "agent_zero": {"online": False, "url": AGENT_ZERO_URL},
        "ollama": {"online": False, "models": []},
        "agentmemory": {"online": False},
    }

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{VM_API_URL}/api/dashboard")
            if r.status_code == 200:
                vm_data = r.json()
                status["vm_reachable"] = True
                status["vm_prospects"] = vm_data.get("total_prospects", 0)
                status["vm_stages"] = vm_data.get("by_stage", {})
    except Exception:
        status["vm_reachable"] = False

    # Agent Zero status
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{AGENT_ZERO_URL}/api/health")
            status["agent_zero"]["online"] = r.status_code == 200
    except Exception:
        pass

    # Ollama models
    try:
        vm_ip = AGENT_ZERO_URL.rsplit(":", 1)[0]
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{vm_ip}:11434/api/tags")
            if r.status_code == 200:
                status["ollama"]["online"] = True
                status["ollama"]["models"] = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass

    # AgentMemory status (local) — iii MCP transport on port 3141.
    # iii doesn't expose /livez or /health; any HTTP response (even 404)
    # means the process is alive and listening.
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get("http://localhost:3141/")
            # Anything < 500 means iii is up (404 is normal for root path)
            status["agentmemory"]["online"] = r.status_code < 500
    except Exception:
        # Fallback: raw TCP probe in case iii blocks HTTP root entirely
        try:
            import socket
            with socket.create_connection(("127.0.0.1", 3141), timeout=2):
                status["agentmemory"]["online"] = True
        except Exception:
            status["agentmemory"]["online"] = False

    return status


@app.post("/api/hermes/sync")
async def trigger_sync():
    """Manually trigger a sync from VM."""
    result = await sync_from_vm()
    return result


# ============================================================
# SKILLS (proxy to VM API)
# ============================================================

@app.get("/api/hermes/skills")
async def get_skills():
    """List all Hermes Agent skills from VM."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{VM_API_URL}/api/hermes/skills")
            if r.status_code == 200:
                return r.json()
    except Exception:
        pass
    return []


@app.patch("/api/hermes/skills/{name}")
async def toggle_skill(name: str, body: dict):
    """Toggle skill active state on VM."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.patch(f"{VM_API_URL}/api/hermes/skills/{name}", json=body)
            if r.status_code == 200:
                return r.json()
            return {"error": "VM returned " + str(r.status_code)}
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# MEMORY (proxy to AgentMemory or VM)
# ============================================================

MEMORY_API_URL = os.environ.get("AGENTMEMORY_URL", "http://localhost:3111")


@app.get("/api/hermes/memory")
async def get_memory():
    """Get memory items from AgentMemory service."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{MEMORY_API_URL}/api/memory", params={"limit": 50})
            if r.status_code == 200:
                items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
                facts = [i for i in items if i.get("type") in ("fact", "bug", "workflow", "architecture")]
                prefs = [i for i in items if i.get("type") == "preference"]
                patterns = [i for i in items if i.get("type") == "pattern"]
                return {"facts": facts, "preferences": prefs, "patterns": patterns}
    except Exception:
        pass
    return {"facts": [], "preferences": [], "patterns": []}


@app.post("/api/hermes/memory")
async def create_memory(body: dict):
    """Create a new memory item."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{MEMORY_API_URL}/api/memory", json={
                "type": body.get("type", "fact"),
                "content": body.get("content", ""),
                "concepts": body.get("concepts", []),
            })
            if r.status_code in (200, 201):
                return r.json()
    except Exception as e:
        return {"error": str(e)}
    return {"error": "Failed to create memory item"}


@app.delete("/api/hermes/memory/{item_id}")
async def delete_memory(item_id: str):
    """Delete a memory item."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.delete(f"{MEMORY_API_URL}/api/memory/{item_id}")
            if r.status_code in (200, 204):
                return {"ok": True}
    except Exception as e:
        return {"error": str(e)}
    return {"error": "Failed to delete memory item"}


# ─── Daemon API ───────────────────────────────────────────────────

@app.get("/api/daemon/state")
async def get_daemon_state():
    """Get current daemon state, energy, channels, stats."""
    conn = get_db()
    row = conn.execute("SELECT * FROM daemon_state WHERE id = 1").fetchone()
    conn.close()
    if not row:
        return {"state": "offline", "energy": 0, "stats_today": {}, "channels": {}}
    return {
        "state": row["state"],
        "current_task_type": row["current_task_type"],
        "current_task_detail": row["current_task_detail"],
        "energy": row["energy"],
        "last_heartbeat": row["last_heartbeat"],
        "stats_today": json.loads(row["stats_today"]) if row["stats_today"] else {},
        "stats_week": json.loads(row["stats_week"]) if row["stats_week"] else {},
    }


@app.post("/api/daemon/pause")
async def pause_daemon(minutes: int = Query(default=60)):
    """Pause daemon for N minutes."""
    # Signal daemon via flag in DB
    conn = get_db()
    conn.execute("UPDATE daemon_state SET state = 'paused' WHERE id = 1")
    conn.commit()
    conn.close()
    await ws_manager.broadcast({"type": "daemon_state", "state": "paused", "detail": f"Paused for {minutes}m"})
    return {"ok": True, "paused_for": minutes}


@app.post("/api/daemon/resume")
async def resume_daemon():
    """Resume daemon from pause."""
    conn = get_db()
    conn.execute("UPDATE daemon_state SET state = 'idle' WHERE id = 1")
    conn.commit()
    conn.close()
    await ws_manager.broadcast({"type": "daemon_state", "state": "idle", "detail": "Resumed"})
    return {"ok": True}


@app.get("/api/daemon/log")
async def get_daemon_log(limit: int = Query(default=50), category: Optional[str] = None):
    """Get daemon activity log for live feed."""
    conn = get_db()
    if category:
        rows = conn.execute(
            "SELECT * FROM daemon_log WHERE category = ? ORDER BY timestamp DESC LIMIT ?",
            (category, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM daemon_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "timestamp": r["timestamp"],
            "level": r["level"],
            "category": r["category"],
            "message": r["message"],
            "metadata": json.loads(r["metadata"]) if r["metadata"] else None,
            "visual_event": json.loads(r["visual_event"]) if r["visual_event"] else None,
        }
        for r in rows
    ]


@app.get("/api/daemon/decisions")
async def get_daemon_decisions(limit: int = Query(default=20)):
    """Get recent AI decisions with reasoning."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM daemon_decisions ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "timestamp": r["timestamp"],
            "action": r["action"],
            "reason": r["reason"],
            "context": json.loads(r["context"]) if r["context"] else None,
        }
        for r in rows
    ]


@app.get("/api/daemon/channels")
async def get_daemon_channels():
    """Get channel states for health cards."""
    # Read from daemon_state or return defaults
    conn = get_db()
    row = conn.execute("SELECT stats_today FROM daemon_state WHERE id = 1").fetchone()
    conn.close()
    # Default channel states (daemon updates these when running)
    return {
        "linkedin": {"daily_used": 0, "daily_limit": 70, "health": 1.0, "warmup_day": 14, "warmup_complete": True, "is_active": True},
        "email": {"daily_used": 0, "daily_limit": 75, "health": 1.0, "warmup_day": 0, "warmup_complete": False, "is_active": True},
        "whatsapp": {"daily_used": 0, "daily_limit": 25, "health": 1.0, "warmup_day": 0, "warmup_complete": False, "is_active": False},
        "instagram": {"daily_used": 0, "daily_limit": 50, "health": 1.0, "warmup_day": 0, "warmup_complete": False, "is_active": False},
    }


@app.get("/api/daemon/timeline")
async def get_daemon_timeline():
    """Get 24h activity timeline for visual bar."""
    conn = get_db()
    rows = conn.execute("""
        SELECT
            strftime('%H', timestamp) as hour,
            category,
            COUNT(*) as count
        FROM daemon_log
        WHERE date(timestamp) = date('now')
        GROUP BY hour, category
        ORDER BY hour
    """).fetchall()
    conn.close()

    # Build 24h timeline
    timeline = {}
    for h in range(24):
        timeline[str(h).zfill(2)] = {"categories": {}, "total": 0}
    for r in rows:
        h = r["hour"]
        if h in timeline:
            timeline[h]["categories"][r["category"]] = r["count"]
            timeline[h]["total"] += r["count"]

    return timeline


@app.post("/api/daemon/broadcast")
async def daemon_broadcast(request: Request):
    """Internal endpoint for daemon to broadcast events to connected WebSocket clients."""
    body = await request.json()
    await ws_manager.broadcast(body)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    print("\n  Hermes Command Center v2")
    print(f"  Dashboard:  http://localhost:55000")
    print(f"  VM API:     {VM_API_URL}")
    print(f"  Sync every: {SYNC_INTERVAL}s")
    print(f"  API Docs:   http://localhost:55000/docs\n")
    uvicorn.run(app, host="0.0.0.0", port=55000, log_level="info")
