"""Hermes Cloud Studio — Shared state, helpers and singletons.

Extraido de server.py durante MERGED-011 (split monolitos).

Conteudo:
- Constantes derivadas de settings (paths, tokens, URLs)
- spawn() + _background_tasks (MERGED-015)
- get_db() + init_db() + helpers de runtime_state (MERGED-004)
- WSManager + ws_manager singleton
- _check_internal (MERGED-003) + _telegram_notify
- _local_error_until_ack (MERGED-016) + _persist_local_errors
- Loop globals expostos como atributos de modulo (read/write via state.XYZ)

Loops e routers importam daqui:
    from core.state import get_db, ws_manager, spawn, AUTH_TOKEN, settings, ...
    import core.state as state          # quando precisa mutar globals
    state._LI_HEALTH_LAST_STATE = "ok"
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import HTTPException, Request
from starlette.websockets import WebSocket

from config import settings

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
DB_PATH = PROJECT_ROOT / "hermes_local.db"
PHOTO_CACHE_DIR = PROJECT_ROOT / "photo_cache"
PHOTO_CACHE_DIR.mkdir(exist_ok=True)

VM_API_URL = settings.vm_api_url_resolved
AGENT_ZERO_URL = settings.agent_zero_url
AGENT_ZERO_API_KEY = settings.agent_zero_api_key
GOOGLE_API_KEY = settings.google_places_api_key
SYNC_INTERVAL = settings.sync_interval

AUTH_TOKEN = settings.auth_token.strip()
if not AUTH_TOKEN:
    raise RuntimeError(
        "HERMES_AUTH_TOKEN obrigatório. Setar em .env ou env var antes de subir o server. "
        "Gerar via: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
    )

INTERNAL_TOKEN = settings.internal_token.strip()
if not INTERNAL_TOKEN:
    raise RuntimeError(
        "HERMES_INTERNAL_TOKEN obrigatório. Setar em .env ou env var antes de subir o server. "
        "Gerar via: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
    )

logger = logging.getLogger("hermes")

# ---------------------------------------------------------------------------
# Background-task registry (MERGED-015)
# ---------------------------------------------------------------------------

_background_tasks: set = set()


def spawn(coro) -> asyncio.Task:
    """Cria asyncio.Task com referência forte para evitar coleta pelo GC (MERGED-015)."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


# ---------------------------------------------------------------------------
# Persistent runtime state — survive restart (MERGED-004 / MERGED-016)
# ---------------------------------------------------------------------------

# Erros locais de dispatch preservados até ack do owner.
_local_error_until_ack: dict = {}

# Persistent Agent Zero context for Hermes conversations
_agent_zero_context_id: Optional[str] = None

# Session / health monitor globals (read/write em loops)
_LI_SESSION_LAST_OK = True
_LI_SESSION_LAST_NOTIFIED = 0.0
# MERGED-018 — contador de falhas consecutivas pra evitar spam por flake de rede
_LI_SESSION_FAIL_STREAK = 0
_LI_HEALTH_LAST_STATE: Optional[str] = None
_LI_HEALTH_NOTIFIED_AT = 0.0


def _persist_local_errors() -> None:
    set_runtime_state("local_error_until_ack", _local_error_until_ack)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def set_runtime_state(key: str, value: Any) -> None:
    """Persiste estado runtime (JSON-serializável) em hermes_local.db (MERGED-004)."""
    db = get_db()
    try:
        db.execute(
            "INSERT INTO runtime_state (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, json.dumps(value), time.time()),
        )
        db.commit()
    except Exception:
        logger.exception("set_runtime_state(%s) falhou", key)
    finally:
        db.close()


def get_runtime_state(key: str, default: Any = None) -> Any:
    db = get_db()
    try:
        row = db.execute("SELECT value FROM runtime_state WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        return json.loads(row["value"])
    except Exception:
        logger.exception("get_runtime_state(%s) falhou", key)
        return default
    finally:
        db.close()


def is_subsystem_paused(name: str) -> bool:
    """F.2.1+F.2.2 — True se subsistema 'name' tem pause ativo (until_ts > now).

    Lê runtime_state.subsystem_pauses (JSON map name -> until_ts unix).
    Usado por loops maduros (sync, linkedin_sync, linkedin_scheduler) e
    channels/email/sender pra skip iteration sem matar o processo inteiro.
    """
    raw = get_runtime_state("subsystem_pauses", {}) or {}
    if not isinstance(raw, dict):
        return False
    until_ts = raw.get(name)
    if not isinstance(until_ts, (int, float)):
        return False
    return float(until_ts) > time.time()


def init_db() -> None:
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

        CREATE TABLE IF NOT EXISTS lab_runs (
            id TEXT PRIMARY KEY,
            run_id TEXT UNIQUE NOT NULL,
            flow TEXT NOT NULL,
            started_at REAL NOT NULL,
            completed_at REAL,
            status TEXT NOT NULL DEFAULT 'running',
            compliance_score INTEGER,
            fingerprint_hash TEXT,
            artifacts_path TEXT,
            error_message TEXT,
            duration_ms INTEGER,
            pinned INTEGER DEFAULT 0,
            created_at REAL DEFAULT (strftime('%s', 'now'))
        );

        CREATE INDEX IF NOT EXISTS idx_lab_runs_started ON lab_runs (started_at DESC);
        CREATE INDEX IF NOT EXISTS idx_lab_runs_status ON lab_runs (status);

        INSERT OR IGNORE INTO daemon_state (id, state, started_at, last_heartbeat)
        VALUES (1, 'idle', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

        CREATE TABLE IF NOT EXISTS runtime_state (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at REAL
        );
    """)
    conn.commit()

    try:
        conn.execute("SELECT photo_ref FROM prospects LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE prospects ADD COLUMN photo_ref TEXT")
        conn.commit()
        logger.info("Migration: added photo_ref column to prospects")

    # H1 B7: idempotent migration — events_jsonl_path column
    try:
        conn.execute("SELECT events_jsonl_path FROM lab_runs LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE lab_runs ADD COLUMN events_jsonl_path TEXT NULL")
        conn.commit()
        logger.info("Migration: added events_jsonl_path to lab_runs (H1 B7)")

    # MERGED-006 — Sync versioning + conflict detection
    try:
        conn.execute("SELECT version FROM prospects LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE prospects ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
        conn.execute("ALTER TABLE prospects ADD COLUMN last_synced_version INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE prospects ADD COLUMN conflict_at REAL")
        conn.commit()
        logger.info("Migration: added version/last_synced_version/conflict_at to prospects (MERGED-006)")

    # H6 B15 — caller_chapter traceability column (idempotent; mcp_calls may not exist yet)
    try:
        conn.execute("SELECT caller_chapter FROM mcp_calls LIMIT 1")
    except sqlite3.OperationalError as _exc:
        _msg = str(_exc)
        if "no such table" in _msg:
            pass  # mcp_calls absent — gateway F.5.3 migration not yet applied, skip
        else:
            # "no such column: caller_chapter" → add it
            try:
                conn.execute("ALTER TABLE mcp_calls ADD COLUMN caller_chapter TEXT NULL")
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mcp_calls_caller_chapter"
                    " ON mcp_calls(caller_chapter)"
                )
                conn.commit()
                logger.info("Migration: added caller_chapter to mcp_calls (H6 B15)")
            except sqlite3.OperationalError:
                pass  # concurrent startup already added it — safe to ignore

    conn.close()


# ---------------------------------------------------------------------------
# Lab runs helpers (F.3.1 — Lab Cockpit backend)
# ---------------------------------------------------------------------------

def lab_run_create(
    run_id: str,
    flow: str,
    started_at: float,
    artifacts_path: Optional[str] = None,
) -> str:
    """Insere row 'running' em lab_runs. Retorna id (UUID)."""
    import uuid
    row_id = uuid.uuid4().hex
    db = get_db()
    try:
        db.execute(
            "INSERT INTO lab_runs (id, run_id, flow, started_at, status, artifacts_path) "
            "VALUES (?, ?, ?, ?, 'running', ?)",
            (row_id, run_id, flow, started_at, artifacts_path),
        )
        db.commit()
        return row_id
    finally:
        db.close()


def lab_run_update(
    run_id: str,
    *,
    status: Optional[str] = None,
    completed_at: Optional[float] = None,
    compliance_score: Optional[int] = None,
    fingerprint_hash: Optional[str] = None,
    error_message: Optional[str] = None,
    duration_ms: Optional[int] = None,
    pinned: Optional[bool] = None,
) -> None:
    """Update parcial por run_id. Apenas campos não-None aplicados."""
    fields: list[str] = []
    values: list[Any] = []
    if status is not None:
        fields.append("status=?"); values.append(status)
    if completed_at is not None:
        fields.append("completed_at=?"); values.append(completed_at)
    if compliance_score is not None:
        fields.append("compliance_score=?"); values.append(int(compliance_score))
    if fingerprint_hash is not None:
        fields.append("fingerprint_hash=?"); values.append(fingerprint_hash)
    if error_message is not None:
        fields.append("error_message=?"); values.append(error_message)
    if duration_ms is not None:
        fields.append("duration_ms=?"); values.append(int(duration_ms))
    if pinned is not None:
        fields.append("pinned=?"); values.append(1 if pinned else 0)
    if not fields:
        return
    values.append(run_id)
    db = get_db()
    try:
        db.execute(f"UPDATE lab_runs SET {', '.join(fields)} WHERE run_id=?", values)
        db.commit()
    finally:
        db.close()


def lab_run_get(run_id: str) -> Optional[dict]:
    """Retorna dict da row ou None se run_id inexistente."""
    db = get_db()
    try:
        row = db.execute(
            "SELECT id, run_id, flow, started_at, completed_at, status, compliance_score, "
            "fingerprint_hash, artifacts_path, error_message, duration_ms, pinned, created_at "
            "FROM lab_runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        db.close()


def lab_runs_list(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
) -> list[dict]:
    """Lista paginada DESC by started_at. status='all'|None devolve tudo."""
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    db = get_db()
    try:
        if status and status != "all":
            rows = db.execute(
                "SELECT id, run_id, flow, started_at, completed_at, status, compliance_score, "
                "fingerprint_hash, artifacts_path, error_message, duration_ms, pinned, created_at "
                "FROM lab_runs WHERE status=? ORDER BY started_at DESC LIMIT ? OFFSET ?",
                (status, limit, offset),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT id, run_id, flow, started_at, completed_at, status, compliance_score, "
                "fingerprint_hash, artifacts_path, error_message, duration_ms, pinned, created_at "
                "FROM lab_runs ORDER BY started_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def lab_run_is_running() -> bool:
    """True se há ao menos 1 run com status='running' (gate concurrent)."""
    db = get_db()
    try:
        row = db.execute("SELECT 1 FROM lab_runs WHERE status='running' LIMIT 1").fetchone()
        return bool(row)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# WebSocket manager (singleton)
# ---------------------------------------------------------------------------

class WSManager:
    def __init__(self) -> None:
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, event: dict) -> None:
        for ws in self.connections[:]:
            try:
                await ws.send_json(event)
            except Exception:  # noqa: silenciado intencional — WS/broadcast opcional
                self.connections.remove(ws)


ws_manager = WSManager()


# ---------------------------------------------------------------------------
# Auth / notify helpers
# ---------------------------------------------------------------------------

def _check_internal(request: Request) -> None:
    """Valida requisições de endpoints internos: loopback + token dedicado (MERGED-003)."""
    if request.client.host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(403, "loopback only")
    token = request.headers.get("X-Internal-Token", "")
    if not secrets.compare_digest(token, INTERNAL_TOKEN):
        raise HTTPException(401, "internal token invalid")


async def _telegram_notify(text: str) -> None:
    tok = settings.telegram_bot_token.strip()
    chat = settings.telegram_chat_id.strip()
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
