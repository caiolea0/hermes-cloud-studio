"""Hermes Cloud Studio — VM-side shared state, helpers, singletons (MERGED-011).

Extraido de hermes_api_v2.py. Routers vm_api/* importam daqui.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import sys
import threading
import time
import uuid
from contextlib import suppress
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger("hermes_api_v2")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

load_dotenv()

# MERGED-013 — Settings central pydantic-settings
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import settings  # noqa: E402

HERMES_HOME = settings.hermes_home
VM_AUTH_TOKEN = settings.vm_auth_token.strip()
if not VM_AUTH_TOKEN:
    raise RuntimeError(
        "HERMES_VM_AUTH_TOKEN obrigatório. Setar em ~/.hermes/.env antes de subir o server. "
        "Gerar via: python3 -c \"import secrets; print(secrets.token_urlsafe(32))\""
    )
DB_PATH = HERMES_HOME / "data" / "command_center.db"
DATA_DIR = HERMES_HOME / "data"

# Background task registry — previne GC de tasks "soltas" (MERGED-015)
_background_tasks: set = set()


def spawn(coro) -> asyncio.Task:
    """Cria asyncio.Task com referência forte para evitar coleta pelo GC."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


# Subprocess registry (MERGED-017) — Popen tracked pra terminate em lifespan shutdown.
# Guarda (pid, create_time) — create_time distingue PID reciclado pelo SO.
_tracked_subprocs: set = set()


def register_subproc(pid: int) -> None:
    """Registra subprocesso pra ser terminado no shutdown. Captura create_time via psutil."""
    try:
        import psutil
        ct = psutil.Process(pid).create_time()
        _tracked_subprocs.add((pid, ct))
    except Exception:
        logger.exception("register_subproc: falha capturar create_time pid=%s", pid)


def terminate_tracked_subprocs(grace: float = 5.0) -> None:
    """Terminate (SIGTERM) seguido de kill (SIGKILL) se nao morreu em grace s.
    Skip se PID nao existe mais ou create_time mudou (recycled)."""
    try:
        import psutil
    except Exception:
        logger.exception("terminate_tracked_subprocs: psutil indisponivel")
        return
    for pid, ct in list(_tracked_subprocs):
        try:
            p = psutil.Process(pid)
            if p.create_time() != ct:
                continue  # PID reciclado, nao eh nosso
            p.terminate()
            try:
                p.wait(timeout=grace)
            except psutil.TimeoutExpired:
                logger.warning("terminate_tracked_subprocs: SIGKILL pid=%s (no SIGTERM response)", pid)
                p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        except Exception:
            logger.exception("terminate_tracked_subprocs: falha pid=%s", pid)
    _tracked_subprocs.clear()


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


# ---------------------------------------------------------------------------
# Campaign runs lifecycle (MERGED-004)
# ---------------------------------------------------------------------------

def _record_campaign_run(campaign_id: int, campaign_type: str) -> str:
    """Registra início de uma campaign run em campaign_runs. Retorna run_id."""
    run_id = uuid.uuid4().hex
    db = get_db()
    try:
        db.execute(
            "INSERT INTO campaign_runs (run_id, campaign_id, status, started_at, last_heartbeat, pid, metadata_json) "
            "VALUES (?, ?, 'running', ?, ?, ?, ?)",
            (run_id, campaign_id, time.time(), time.time(), os.getpid(), json.dumps({"type": campaign_type})),
        )
        db.commit()
    finally:
        db.close()
    return run_id


def _touch_campaign_run(run_id: str) -> None:
    db = get_db()
    try:
        db.execute("UPDATE campaign_runs SET last_heartbeat=? WHERE run_id=?", (time.time(), run_id))
        db.commit()
    finally:
        db.close()


def _finalize_campaign_run(run_id: str, status: str) -> None:
    db = get_db()
    try:
        db.execute(
            "UPDATE campaign_runs SET status=?, last_heartbeat=? WHERE run_id=?",
            (status, time.time(), run_id),
        )
        db.commit()
    finally:
        db.close()


async def _track_run_lifecycle(run_id: str, campaign_id: int, coro):
    """Wrapper que finaliza campaign_runs baseado no resultado real do coro.

    Os coros de campanha NÃO relançam exceções (capturadas internamente),
    então o estado final vem de linkedin_campaigns.status — consistente
    com a fonte de verdade que o sync_loop já consome.
    """
    try:
        await coro
    except asyncio.CancelledError:
        _finalize_campaign_run(run_id, "cancelled")
        raise
    except Exception:
        logger.exception("campaign run %s falhou inesperadamente", run_id)
        _finalize_campaign_run(run_id, "error")
        return
    final = "interrupted"
    db = _get_li_db()
    try:
        row = db.execute(
            "SELECT status FROM linkedin_campaigns WHERE id=?", (campaign_id,)
        ).fetchone()
        if row and row["status"] in ("done", "error", "stopped"):
            final = row["status"]
    except Exception:
        logger.exception("track_run_lifecycle: lookup linkedin_campaigns falhou")
    finally:
        with suppress(Exception):
            db.close()
    _finalize_campaign_run(run_id, final)


def _get_li_db() -> sqlite3.Connection:
    """Helper para LinkedIn rate-limiter DB (mesma conn que get_db, alias compat)."""
    return get_db()


def init_db() -> None:
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS prospects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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

        CREATE INDEX IF NOT EXISTS idx_prospects_stage ON prospects(stage);
        CREATE INDEX IF NOT EXISTS idx_prospects_city ON prospects(city);
        CREATE INDEX IF NOT EXISTS idx_prospects_score ON prospects(score DESC);
        CREATE INDEX IF NOT EXISTS idx_activities_type ON activities(type);
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

        CREATE TABLE IF NOT EXISTS campaign_runs (
            run_id TEXT PRIMARY KEY,
            campaign_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            started_at REAL NOT NULL,
            last_heartbeat REAL,
            pid INTEGER,
            metadata_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_campaign_runs_status ON campaign_runs(status);
        CREATE INDEX IF NOT EXISTS idx_campaign_runs_campaign ON campaign_runs(campaign_id);
    """)
    conn.commit()

    try:
        conn.execute("SELECT photo_ref FROM prospects LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE prospects ADD COLUMN photo_ref TEXT")
        conn.commit()

    # MERGED-006 — Sync versioning. updated_at ja existe (TIMESTAMP).
    try:
        conn.execute("SELECT version FROM prospects LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE prospects ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
        conn.commit()
        logger.info("Migration: added version column to prospects (MERGED-006)")

    conn.close()


# ---------------------------------------------------------------------------
# Audit state (in-memory + lock)
# ---------------------------------------------------------------------------

_audit_state = {
    "running": False,
    "total": 0,
    "done": 0,
    "results": [],
    "started_at": None,
    "finished_at": None,
    "errors": [],
}
_audit_lock = threading.Lock()
