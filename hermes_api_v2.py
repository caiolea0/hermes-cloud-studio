"""Hermes Command Center v2 — VM API Bridge.

FastAPI server on the VM that serves prospect data, activity logs,
pipeline status, scraper control, and photo references to the dashboard.
"""
import asyncio
import json
import logging
import os
import secrets
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List

from dotenv import load_dotenv

logger = logging.getLogger("hermes_api_v2")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv()
HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
VM_AUTH_TOKEN = os.environ.get("HERMES_VM_AUTH_TOKEN", "").strip()
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


def get_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


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


def init_db():
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

    # Migration: add photo_ref if missing
    try:
        conn.execute("SELECT photo_ref FROM prospects LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE prospects ADD COLUMN photo_ref TEXT")
        conn.commit()

    conn.close()


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
    import time as _t
    return {"ok": True, "ts": _t.time(), "service": "hermes_api_v2"}


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


class ActivityCreate(BaseModel):
    type: str
    title: str
    description: Optional[str] = None
    prospect_id: Optional[int] = None
    metadata: Optional[dict] = None


class ScraperConfig(BaseModel):
    cities: Optional[List[str]] = None
    categories: Optional[List[str]] = None
    only_no_site: bool = False
    rate_limit: float = 1.0


# --- Dashboard ---

@app.get("/api/dashboard")
async def get_dashboard():
    conn = get_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM prospects").fetchone()[0]
        by_stage = dict(conn.execute(
            "SELECT stage, COUNT(*) FROM prospects GROUP BY stage"
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

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_stats = conn.execute(
            "SELECT * FROM pipeline_stats WHERE date = ?", (today,)
        ).fetchone()

        return {
            "total_prospects": total,
            "by_stage": by_stage,
            "recent_activities": recent_activities,
            "active_tasks": active_tasks,
            "top_prospects": top_prospects,
            "today_stats": dict(today_stats) if today_stats else None,
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
    min_score: int = 0,
    limit: int = 50,
    offset: int = 0,
):
    conn = get_db()
    try:
        query = "SELECT * FROM prospects WHERE score >= ?"
        params = [min_score]
        if stage:
            query += " AND stage = ?"
            params.append(stage)
        if city:
            query += " AND city = ?"
            params.append(city)
        query += " ORDER BY score DESC, created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]
        return {"count": len(rows), "prospects": rows}
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
        data = update.dict(exclude_none=True) if hasattr(update, 'dict') else update.model_dump(exclude_none=True)
        sets = []
        params = []
        for field, value in data.items():
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


# --- Activities ---

@app.get("/api/activities")
async def list_activities(limit: int = 50, type: Optional[str] = None, offset: int = 0):
    conn = get_db()
    try:
        if type:
            rows = conn.execute(
                "SELECT * FROM activities WHERE type = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (type, limit, offset)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM activities ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
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
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
        return {"tasks": [dict(r) for r in rows]}
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
async def update_task(task_id: int, status: str, result: Optional[str] = None):
    conn = get_db()
    try:
        completed = datetime.now(timezone.utc).isoformat() if status == "completed" else None
        conn.execute(
            "UPDATE tasks SET status = ?, result = ?, completed_at = ? WHERE id = ?",
            (status, result, completed, task_id)
        )
        conn.commit()
        return {"status": "updated"}
    finally:
        conn.close()


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


# --- Scraper Status & Control ---

@app.get("/api/scraper/status")
async def scraper_status():
    """Get scraper real-time status, with last-run fallback."""
    gosom_checkpoint = HERMES_HOME / "data" / "gosom_checkpoint.json"
    gosom_last_run = HERMES_HOME / "data" / "gosom_last_run.json"
    checkpoint_file = HERMES_HOME / "data" / "night_scraper_checkpoint.json"
    last_run_file = HERMES_HOME / "data" / "night_scraper_last_run.json"
    pid_file = HERMES_HOME / "data" / "night_scraper.pid"
    log_dir = HERMES_HOME / "logs"

    running = False
    pid = None

    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            result = subprocess.run(["kill", "-0", str(pid)], capture_output=True)
            running = result.returncode == 0
        except Exception:  # noqa: silenciado intencional — fallback seguro
            pass

    # Try active checkpoint first
    checkpoint = {}
    if checkpoint_file.exists():
        try:
            checkpoint = json.loads(checkpoint_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: silenciado intencional — fallback seguro
            pass

    # Check gosom checkpoint (active scrape)
    if not checkpoint and gosom_checkpoint.exists():
        try:
            gcp = json.loads(gosom_checkpoint.read_text(encoding="utf-8"))
            cities_done = gcp.get("stats", {}).get("cities_completed", [])
            checkpoint = {
                "city": cities_done[-1] if cities_done else "scraping...",
                "category_idx": gcp.get("cat_idx", 0),
                "stats": gcp.get("stats", {}),
                "timestamp": gcp.get("timestamp"),
            }
            running = True
        except Exception:  # noqa: silenciado intencional — fallback seguro
            pass

    # If no active checkpoint, try last run (gosom first, then legacy)
    last_run = {}
    if not checkpoint:
        for lr_file in [gosom_last_run, last_run_file]:
            if lr_file.exists():
                try:
                    last_run = json.loads(lr_file.read_text(encoding="utf-8"))
                    break
                except Exception:  # noqa: silenciado intencional — fallback seguro
                    pass

    log_tail = []
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    log_file = log_dir / f"night_scraper_{today}.log"
    if log_file.exists():
        try:
            lines = log_file.read_text(encoding="utf-8").strip().split("\n")
            log_tail = lines[-10:]
        except Exception:  # noqa: silenciado intencional — fallback seguro
            pass

    if checkpoint:
        stats = checkpoint.get("stats", {})
        return {
            "running": running,
            "pid": pid,
            "current_city": checkpoint.get("city"),
            "category_index": checkpoint.get("category_idx", 0),
            "total_categories": 111,
            "stats": stats,
            "log_tail": log_tail,
            "checkpoint_time": checkpoint.get("timestamp"),
        }
    elif last_run:
        return {
            "running": False,
            "pid": None,
            "current_city": None,
            "category_index": 0,
            "total_categories": 111,
            "stats": last_run.get("stats", {}),
            "log_tail": log_tail,
            "completed_at": last_run.get("completed_at"),
            "last_run": True,
        }
    else:
        return {
            "running": False,
            "pid": None,
            "current_city": None,
            "category_index": 0,
            "total_categories": 0,
            "stats": {
                "total_new": 0, "with_website": 0, "without_website": 0,
                "skipped_dupes": 0, "audit_tasks_created": 0, "outreach_tasks_created": 0,
                "cities_completed": [], "errors": [],
            },
            "log_tail": log_tail,
        }


@app.post("/api/scraper/start")
async def start_scraper(config: ScraperConfig):
    """Start the night scraper as a background process."""
    pid_file = HERMES_HOME / "data" / "night_scraper.pid"

    # Check if already running
    if pid_file.exists():
        try:
            existing_pid = int(pid_file.read_text().strip())
            result = subprocess.run(["kill", "-0", str(existing_pid)], capture_output=True)
            if result.returncode == 0:
                return {"status": "already_running", "pid": existing_pid}
        except Exception:  # noqa: silenciado intencional — fallback seguro
            pass

    # Build command — use gosom scraper (free, Docker-based)
    script = str(HERMES_HOME / "scripts" / "gosom_scraper.py")
    cmd_args = ["python3", script]

    if config.cities:
        cmd_args.extend(["--cities", ",".join(config.cities)])

    if config.categories:
        cmd_args.extend(["--categories", ",".join(config.categories)])

    if config.only_no_site:
        cmd_args.append("--only-no-site")

    # Load env and start
    env = os.environ.copy()
    env_file = HERMES_HOME / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()

    log_file = HERMES_HOME / "logs" / f"night_scraper_{datetime.now(timezone.utc).strftime('%Y%m%d')}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    with open(log_file, "a") as lf:
        proc = subprocess.Popen(
            cmd_args,
            stdout=lf,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )

    pid_file.write_text(str(proc.pid))
    return {"status": "started", "pid": proc.pid}


@app.post("/api/scraper/stop")
async def stop_scraper():
    """Stop the running scraper gracefully."""
    pid_file = HERMES_HOME / "data" / "night_scraper.pid"

    if not pid_file.exists():
        return {"status": "not_running"}

    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        pid_file.unlink(missing_ok=True)
        return {"status": "stopped", "pid": pid}
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        return {"status": "not_running"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/api/scraper/history")
async def scraper_history():
    """List past scraper run reports."""
    log_dir = HERMES_HOME / "logs"
    runs = []
    discovery_dir = HERMES_HOME / "data" / "discovery"
    report_files = list(log_dir.glob("night_scraper_report_*.json"))
    if discovery_dir.exists():
        report_files += list(discovery_dir.glob("gosom_report_*.json"))
    for f in sorted(report_files, key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["filename"] = f.name
            runs.append(data)
        except Exception:  # noqa: silenciado intencional — fallback seguro
            pass
    return {"runs": runs[:20]}


# --- Audit Endpoints ---

def _import_web_audit():
    sys.path.insert(0, str(HERMES_HOME / "scripts"))
    from web_audit import audit_prospect
    return audit_prospect


def _import_outreach():
    sys.path.insert(0, str(HERMES_HOME / "scripts"))
    from outreach_generator import generate_outreach
    return generate_outreach


@app.post("/api/audit/start")
async def start_audit(batch_size: int = 50, stage: str = "discovered"):
    global _audit_state
    with _audit_lock:
        if _audit_state["running"]:
            return {"status": "already_running", "done": _audit_state["done"], "total": _audit_state["total"]}

    db = get_db()
    try:
        rows = db.execute(
            "SELECT * FROM prospects WHERE stage = ? AND (audit_summary IS NULL OR audit_summary = '') ORDER BY score DESC LIMIT ?",
            (stage, batch_size)
        ).fetchall()
        prospects = [dict(r) for r in rows]
    finally:
        db.close()

    if not prospects:
        return {"status": "nothing_to_audit", "total": 0}

    with _audit_lock:
        _audit_state = {
            "running": True,
            "total": len(prospects),
            "done": 0,
            "results": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "errors": [],
        }

    def run_audit_batch(prospect_list):
        global _audit_state
        try:
            audit_fn = _import_web_audit()
        except Exception as e:
            with _audit_lock:
                _audit_state["errors"].append(f"Import error: {e}")
                _audit_state["running"] = False
            return

        for p in prospect_list:
            try:
                result = audit_fn(p)
                new_stage = "qualified" if result["score"] >= 50 else "discovered"
                if result["score"] >= 70:
                    new_stage = "audited"

                db2 = get_db()
                try:
                    db2.execute(
                        "UPDATE prospects SET score=?, stage=?, audit_summary=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (result["score"], new_stage, result["audit_summary"], p["id"])
                    )
                    db2.execute(
                        "INSERT INTO activities (type, title, description, prospect_id) VALUES (?,?,?,?)",
                        ("audit", f"Auditoria: {p.get('business_name', p.get('name', '?'))}",
                         f"Score: {result['score']} | Stage: {new_stage}", p["id"])
                    )
                    db2.commit()
                finally:
                    db2.close()

                with _audit_lock:
                    _audit_state["done"] += 1
                    _audit_state["results"].append({
                        "id": p["id"],
                        "name": p.get("business_name", p.get("name")),
                        "score": result["score"],
                        "stage": new_stage,
                    })

                time.sleep(0.3)

            except Exception as e:
                with _audit_lock:
                    _audit_state["done"] += 1
                    _audit_state["errors"].append(f"{p.get('business_name', '?')}: {e}")

        with _audit_lock:
            _audit_state["running"] = False
            _audit_state["finished_at"] = datetime.now(timezone.utc).isoformat()

    t = threading.Thread(target=run_audit_batch, args=(prospects,), daemon=True)
    t.start()

    return {"status": "started", "total": len(prospects)}


@app.get("/api/audit/status")
async def audit_status():
    with _audit_lock:
        return dict(_audit_state)


@app.post("/api/audit/prospect/{prospect_id}")
async def audit_single(prospect_id: int):
    db = get_db()
    try:
        row = db.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Prospect not found")
        p = dict(row)
    finally:
        db.close()

    audit_fn = _import_web_audit()
    result = audit_fn(p)

    new_stage = "qualified" if result["score"] >= 50 else "discovered"
    if result["score"] >= 70:
        new_stage = "audited"

    db = get_db()
    try:
        db.execute(
            "UPDATE prospects SET score=?, stage=?, audit_summary=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (result["score"], new_stage, result["audit_summary"], prospect_id)
        )
        db.execute(
            "INSERT INTO activities (type, title, description, prospect_id) VALUES (?,?,?,?)",
            ("audit", f"Auditoria: {p.get('business_name', p.get('name', '?'))}",
             f"Score: {result['score']} | Stage: {new_stage}", prospect_id)
        )
        db.commit()
    finally:
        db.close()

    result["new_stage"] = new_stage
    return result


class AuditBatchRequest(BaseModel):
    ids: Optional[List[int]] = None
    batch_size: int = 50
    stage: str = "discovered"


@app.post("/api/audit/batch")
async def audit_batch(body: AuditBatchRequest):
    if body.ids:
        db = get_db()
        try:
            placeholders = ",".join("?" for _ in body.ids)
            rows = db.execute(f"SELECT * FROM prospects WHERE id IN ({placeholders})", body.ids).fetchall()
            prospects = [dict(r) for r in rows]
        finally:
            db.close()
    else:
        db = get_db()
        try:
            rows = db.execute(
                "SELECT * FROM prospects WHERE stage = ? AND (audit_summary IS NULL OR audit_summary = '') ORDER BY score DESC LIMIT ?",
                (body.stage, body.batch_size)
            ).fetchall()
            prospects = [dict(r) for r in rows]
        finally:
            db.close()

    if not prospects:
        return {"status": "nothing_to_audit", "total": 0}

    with _audit_lock:
        _audit_state.update({
            "running": True, "total": len(prospects), "done": 0,
            "results": [], "errors": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
        })

    return await start_audit(batch_size=len(prospects), stage=body.stage)


# --- Outreach Endpoints ---

@app.post("/api/prospects/{prospect_id}/outreach")
async def generate_prospect_outreach(prospect_id: int):
    db = get_db()
    try:
        row = db.execute("SELECT * FROM prospects WHERE id = ?", (prospect_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Prospect not found")
        p = dict(row)
    finally:
        db.close()

    generate_fn = _import_outreach()
    result = generate_fn(p)

    db = get_db()
    try:
        db.execute(
            "UPDATE prospects SET outreach_message=?, outreach_status='ready', stage='outreach', updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (result.get("whatsapp_message", ""), prospect_id)
        )
        db.execute(
            "INSERT INTO activities (type, title, description, prospect_id) VALUES (?,?,?,?)",
            ("outreach", f"Proposta gerada: {p.get('business_name', p.get('name', '?'))}",
             f"Servicos: {', '.join(result.get('recommended_services', [])[:3])}", prospect_id)
        )
        db.commit()
    finally:
        db.close()

    return result


class OutreachBatchRequest(BaseModel):
    ids: Optional[List[int]] = None
    batch_size: int = 50
    stage: str = "audited"
    min_score: int = 60


@app.post("/api/outreach/batch")
async def outreach_batch(body: OutreachBatchRequest):
    db = get_db()
    try:
        if body.ids:
            placeholders = ",".join("?" for _ in body.ids)
            rows = db.execute(f"SELECT * FROM prospects WHERE id IN ({placeholders})", body.ids).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM prospects WHERE stage = ? AND score >= ? AND (outreach_message IS NULL OR outreach_message = '') LIMIT ?",
                (body.stage, body.min_score, body.batch_size)
            ).fetchall()
        prospects = [dict(r) for r in rows]
    finally:
        db.close()

    if not prospects:
        return {"status": "nothing_to_generate", "total": 0}

    generate_fn = _import_outreach()
    results = []
    for p in prospects:
        try:
            result = generate_fn(p)
            db = get_db()
            try:
                db.execute(
                    "UPDATE prospects SET outreach_message=?, outreach_status='ready', stage='outreach', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (result.get("whatsapp_message", ""), p["id"])
                )
                db.commit()
            finally:
                db.close()
            results.append({"id": p["id"], "name": p.get("business_name", p.get("name")), "status": "ok"})
        except Exception as e:
            results.append({"id": p["id"], "name": p.get("business_name", p.get("name")), "status": "error", "error": str(e)})

    return {"status": "completed", "total": len(prospects), "results": results}


# --- Pipeline Executor ---

class PipelineExecuteRequest(BaseModel):
    type: str
    config: Optional[dict] = None


@app.post("/api/pipeline/execute")
async def execute_pipeline(body: PipelineExecuteRequest):
    if body.type == "audit":
        cfg = body.config or {}
        return await start_audit(batch_size=cfg.get("batch_size", 50), stage=cfg.get("stage", "discovered"))
    elif body.type == "outreach":
        cfg = body.config or {}
        return await outreach_batch(OutreachBatchRequest(**cfg))
    elif body.type == "linkedin_viewer":
        return {"status": "not_implemented", "message": "LinkedIn viewer runs on PC, not VM"}
    elif body.type == "full":
        audit_result = await start_audit(batch_size=100)
        return {"status": "started", "pipeline": "full", "audit": audit_result}
    else:
        return {"status": "error", "message": f"Unknown pipeline type: {body.type}"}


# --- Skills Management ---

@app.get("/api/hermes/skills")
async def list_skills():
    skills_dir = HERMES_HOME / "skills"
    skills = []
    if skills_dir.exists():
        for f in sorted(skills_dir.glob("*.yaml")) + sorted(skills_dir.glob("*.yml")):
            try:
                import yaml
                data = yaml.safe_load(f.read_text(encoding="utf-8"))
                skills.append({
                    "filename": f.name,
                    "name": data.get("name", f.stem),
                    "description": data.get("description", ""),
                    "model": data.get("model", "default"),
                    "active": data.get("active", True),
                })
            except Exception:
                skills.append({"filename": f.name, "name": f.stem, "description": "parse error", "active": False})
    return {"skills": skills, "total": len(skills)}


@app.patch("/api/hermes/skills/{skill_name}")
async def toggle_skill(skill_name: str, active: bool = True):
    skills_dir = HERMES_HOME / "skills"
    skill_file = skills_dir / f"{skill_name}.yaml"
    if not skill_file.exists():
        skill_file = skills_dir / f"{skill_name}.yml"
    if not skill_file.exists():
        raise HTTPException(404, f"Skill '{skill_name}' not found")

    try:
        import yaml
        data = yaml.safe_load(skill_file.read_text(encoding="utf-8"))
        data["active"] = active
        skill_file.write_text(yaml.dump(data, allow_unicode=True, default_flow_style=False), encoding="utf-8")
        return {"status": "updated", "skill": skill_name, "active": active}
    except Exception as e:
        raise HTTPException(500, f"Failed to update skill: {e}")


# --- Hermes Status ---

@app.get("/api/hermes/status")
async def hermes_status():
    gateway_pid = None
    try:
        pid_file = HERMES_HOME / "gateway.pid"
        if pid_file.exists():
            gateway_pid = int(pid_file.read_text().strip())
    except Exception:  # noqa: silenciado intencional — fallback seguro
        pass

    cron_jobs = []
    jobs_file = HERMES_HOME / "cron" / "jobs.json"
    if jobs_file.exists():
        try:
            cron_jobs = json.loads(jobs_file.read_text())
        except Exception:  # noqa: silenciado intencional — fallback seguro
            pass

    return {
        "gateway_running": gateway_pid is not None,
        "gateway_pid": gateway_pid,
        "cron_jobs": len(cron_jobs) if isinstance(cron_jobs, list) else 0,
        "models_available": _get_ollama_models(),
        "disk_usage": _get_disk_usage(),
    }


def _get_ollama_models():
    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
        lines = r.stdout.strip().split("\n")[1:]
        return [l.split()[0] for l in lines if l.strip()]
    except Exception:
        return []


def _get_disk_usage():
    try:
        import shutil
        usage = shutil.disk_usage("/")
        return {
            "total_gb": round(usage.total / 1e9, 1),
            "used_gb": round(usage.used / 1e9, 1),
            "free_gb": round(usage.free / 1e9, 1),
        }
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# LINKEDIN CAMPAIGN EXECUTION ENDPOINTS  (real Patchright execution on VM)
# ─────────────────────────────────────────────────────────────────────────────

# In-memory tracker for running campaigns (campaign_id → asyncio.Task)
_running_linkedin_campaigns: dict = {}


def _build_li_config():
    """Build LinkedInConfig — account_type prefers DOM-detected cache over env."""
    from linkedin import LinkedInConfig
    # Prefer detected type over env value (env is the seed; cache is the truth)
    account_type = os.environ.get("LINKEDIN_ACCOUNT_TYPE", "free")
    try:
        from linkedin.account_detector import read_cached
        cached = read_cached()
        if cached and cached.get("account_type"):
            account_type = cached["account_type"]
    except Exception:  # noqa: silenciado intencional — fallback seguro
        pass
    return LinkedInConfig(
        account_email=os.environ.get("LINKEDIN_EMAIL", ""),
        account_type=account_type,
        proxy_server=os.environ.get("LINKEDIN_PROXY"),
        proxy_username=os.environ.get("LINKEDIN_PROXY_USER"),
        proxy_password=os.environ.get("LINKEDIN_PROXY_PASS"),
        headless=True,
        use_system_chrome=False,
    )


def _get_li_db() -> sqlite3.Connection:
    """Get DB connection, ensure linkedin_campaigns table exists."""
    conn = get_db()
    conn.execute("""
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
        )
    """)
    conn.commit()
    return conn


def _ensure_campaign_row(campaign_id: int, campaign_type: str, data: dict, conn) -> None:
    """Ensure a campaign row exists in VM DB for this PC-owned id. Always sets status=running."""
    existing = conn.execute(
        "SELECT id FROM linkedin_campaigns WHERE id=?", (campaign_id,)
    ).fetchone()
    now = datetime.now(timezone.utc).isoformat()
    if existing:
        conn.execute(
            "UPDATE linkedin_campaigns SET status='running', started_at=?, "
            "type=?, config=? WHERE id=?",
            (now, campaign_type, json.dumps(data), campaign_id)
        )
    else:
        conn.execute(
            "INSERT INTO linkedin_campaigns (id, type, config, status, started_at) "
            "VALUES (?, ?, ?, 'running', ?)",
            (campaign_id, campaign_type, json.dumps(data), now)
        )
    conn.commit()


def _li_log(campaign_id: int, msg: str, phase: str = "info"):
    """Append log entry to linkedin_campaigns.log."""
    conn = _get_li_db()
    try:
        row = conn.execute("SELECT log FROM linkedin_campaigns WHERE id=?", (campaign_id,)).fetchone()
        logs = json.loads(row["log"]) if row and row["log"] else []
        logs.append({"time": datetime.now(timezone.utc).isoformat(), "msg": msg, "phase": phase})
        conn.execute(
            "UPDATE linkedin_campaigns SET log=? WHERE id=?",
            (json.dumps(logs[-200:]), campaign_id)  # keep last 200 entries
        )
        conn.commit()
    finally:
        conn.close()


@app.post("/api/linkedin/auth")
async def vm_linkedin_auth():
    """Trigger LinkedIn session establishment (headless + manual verification window)."""
    try:
        config = _build_li_config()
        from linkedin.stealth import launch_stealth_browser, save_session
        # run auth attempt in background thread to avoid blocking
        import asyncio
        loop = asyncio.get_event_loop()

        async def _auth():
            browser, context, page = await launch_stealth_browser(config)
            await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
            import asyncio as aio
            await aio.sleep(3)
            if "/feed" in page.url:
                await save_session(context, config)
                return {"ok": True, "session": "already_active"}
            # if login needed, save context and return — human resolves manually
            await save_session(context, config)
            return {"ok": False, "note": "Login page shown — resolve manually or re-check session"}

        result = await _auth()
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/linkedin/campaigns/view")
async def vm_run_view_campaign(request: Request):
    data = await request.json()
    campaign_id = data.pop("campaign_id", None)

    conn = _get_li_db()
    try:
        if not campaign_id:
            cur = conn.execute(
                "INSERT INTO linkedin_campaigns (type, config, status, started_at) VALUES (?,?,?,?)",
                ("view", json.dumps(data), "running", datetime.now(timezone.utc).isoformat())
            )
            campaign_id = cur.lastrowid
            conn.commit()
        else:
            _ensure_campaign_row(campaign_id, "view", data, conn)
    finally:
        conn.close()

    run_id = _record_campaign_run(campaign_id, "view")

    async def _run():
        try:
            from linkedin import LinkedInViewer
            config = _build_li_config()
            config._targets = data
            viewer = LinkedInViewer(config)
            viewer.set_log_callback(lambda msg, phase="info", **kw: (_li_log(campaign_id, msg, phase), _touch_campaign_run(run_id)))
            result = await viewer.start()
            conn2 = _get_li_db()
            try:
                conn2.execute(
                    "UPDATE linkedin_campaigns SET status='done', progress=100, results=?, completed_at=? WHERE id=?",
                    (json.dumps(result), datetime.now(timezone.utc).isoformat(), campaign_id)
                )
                conn2.commit()
            finally:
                conn2.close()
        except Exception as e:
            conn3 = _get_li_db()
            try:
                conn3.execute(
                    "UPDATE linkedin_campaigns SET status='error', completed_at=? WHERE id=?",
                    (datetime.now(timezone.utc).isoformat(), campaign_id)
                )
                conn3.commit()
            finally:
                conn3.close()
            _li_log(campaign_id, f"Erro: {str(e)}", "error")

    task = spawn(_track_run_lifecycle(run_id, campaign_id, _run()))
    _running_linkedin_campaigns[campaign_id] = task
    return {"ok": True, "campaign_id": campaign_id}


@app.post("/api/linkedin/campaigns/engage")
async def vm_run_engage_campaign(request: Request):
    data = await request.json()
    campaign_id = data.pop("campaign_id", None)

    conn = _get_li_db()
    try:
        if not campaign_id:
            cur = conn.execute(
                "INSERT INTO linkedin_campaigns (type, config, status, started_at) VALUES (?,?,?,?)",
                ("engage", json.dumps(data), "running", datetime.now(timezone.utc).isoformat())
            )
            campaign_id = cur.lastrowid
            conn.commit()
        else:
            _ensure_campaign_row(campaign_id, "engage", data, conn)
    finally:
        conn.close()

    run_id = _record_campaign_run(campaign_id, "engage")

    async def _run():
        try:
            from linkedin import LinkedInEngager
            config = _build_li_config()
            engager = LinkedInEngager(config)
            engager.set_log_callback(lambda msg, phase="info", **kw: (_li_log(campaign_id, msg, phase), _touch_campaign_run(run_id)))
            result = await engager.start(data)
            conn2 = _get_li_db()
            try:
                conn2.execute(
                    "UPDATE linkedin_campaigns SET status='done', progress=100, results=?, completed_at=? WHERE id=?",
                    (json.dumps(result), datetime.now(timezone.utc).isoformat(), campaign_id)
                )
                conn2.commit()
            finally:
                conn2.close()
        except Exception as e:
            conn3 = _get_li_db()
            try:
                conn3.execute(
                    "UPDATE linkedin_campaigns SET status='error', completed_at=? WHERE id=?",
                    (datetime.now(timezone.utc).isoformat(), campaign_id)
                )
                conn3.commit()
            finally:
                conn3.close()
            _li_log(campaign_id, f"Erro: {str(e)}", "error")

    task = spawn(_track_run_lifecycle(run_id, campaign_id, _run()))
    _running_linkedin_campaigns[campaign_id] = task
    return {"ok": True, "campaign_id": campaign_id}


@app.post("/api/linkedin/campaigns/connect")
async def vm_run_connect_campaign(request: Request):
    data = await request.json()
    campaign_id = data.pop("campaign_id", None)

    conn = _get_li_db()
    try:
        if not campaign_id:
            cur = conn.execute(
                "INSERT INTO linkedin_campaigns (type, config, status, started_at) VALUES (?,?,?,?)",
                ("connect", json.dumps(data), "running", datetime.now(timezone.utc).isoformat())
            )
            campaign_id = cur.lastrowid
            conn.commit()
        else:
            _ensure_campaign_row(campaign_id, "connect", data, conn)
    finally:
        conn.close()

    run_id = _record_campaign_run(campaign_id, "connect")

    async def _run():
        try:
            from linkedin import LinkedInConnector
            config = _build_li_config()
            connector = LinkedInConnector(config)
            connector.set_campaign_id(campaign_id)
            connector.set_log_callback(lambda msg, phase="info", **kw: (_li_log(campaign_id, msg, phase), _touch_campaign_run(run_id)))
            result = await connector.start(data)
            conn2 = _get_li_db()
            try:
                conn2.execute(
                    "UPDATE linkedin_campaigns SET status='done', progress=100, results=?, completed_at=? WHERE id=?",
                    (json.dumps(result), datetime.now(timezone.utc).isoformat(), campaign_id)
                )
                conn2.commit()
            finally:
                conn2.close()
        except Exception as e:
            conn3 = _get_li_db()
            try:
                conn3.execute(
                    "UPDATE linkedin_campaigns SET status='error', completed_at=? WHERE id=?",
                    (datetime.now(timezone.utc).isoformat(), campaign_id)
                )
                conn3.commit()
            finally:
                conn3.close()
            _li_log(campaign_id, f"Erro: {str(e)}", "error")

    task = spawn(_track_run_lifecycle(run_id, campaign_id, _run()))
    _running_linkedin_campaigns[campaign_id] = task
    return {"ok": True, "campaign_id": campaign_id}


@app.post("/api/linkedin/campaigns/discover")
async def vm_run_discover_campaign(request: Request):
    data = await request.json()
    campaign_id = data.pop("campaign_id", None)

    conn = _get_li_db()
    try:
        if not campaign_id:
            cur = conn.execute(
                "INSERT INTO linkedin_campaigns (type, config, status, started_at) VALUES (?,?,?,?)",
                ("discover", json.dumps(data), "running", datetime.now(timezone.utc).isoformat())
            )
            campaign_id = cur.lastrowid
            conn.commit()
        else:
            _ensure_campaign_row(campaign_id, "discover", data, conn)
    finally:
        conn.close()

    run_id = _record_campaign_run(campaign_id, "discover")

    async def _run():
        try:
            from linkedin import CompanyFinder
            config = _build_li_config()
            finder = CompanyFinder(config)
            finder.set_log_callback(lambda msg, phase="info", **kw: (_li_log(campaign_id, msg, phase), _touch_campaign_run(run_id)))
            result = await finder.start(data)
            conn2 = _get_li_db()
            try:
                conn2.execute(
                    "UPDATE linkedin_campaigns SET status='done', progress=100, results=?, completed_at=? WHERE id=?",
                    (json.dumps(result), datetime.now(timezone.utc).isoformat(), campaign_id)
                )
                conn2.commit()
            finally:
                conn2.close()
        except Exception as e:
            conn3 = _get_li_db()
            try:
                conn3.execute(
                    "UPDATE linkedin_campaigns SET status='error', completed_at=? WHERE id=?",
                    (datetime.now(timezone.utc).isoformat(), campaign_id)
                )
                conn3.commit()
            finally:
                conn3.close()
            _li_log(campaign_id, f"Erro: {str(e)}", "error")

    task = spawn(_track_run_lifecycle(run_id, campaign_id, _run()))
    _running_linkedin_campaigns[campaign_id] = task
    return {"ok": True, "campaign_id": campaign_id}


@app.post("/api/linkedin/campaigns/{campaign_id}/stop")
async def vm_stop_campaign(campaign_id: int):
    task = _running_linkedin_campaigns.get(campaign_id)
    if task and not task.done():
        task.cancel()
        del _running_linkedin_campaigns[campaign_id]

    conn = _get_li_db()
    try:
        conn.execute(
            "UPDATE linkedin_campaigns SET status='stopped', completed_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), campaign_id)
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "campaign_id": campaign_id}


@app.get("/api/linkedin/campaigns")
async def vm_list_linkedin_campaigns(limit: int = 50, offset: int = 0, status: Optional[str] = None):
    """List LinkedIn campaigns from VM DB. Used by PC's sync_linkedin_campaigns loop."""
    conn = _get_li_db()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM linkedin_campaigns WHERE status=? "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (status, limit, offset)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM linkedin_campaigns ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
        campaigns = []
        for r in rows:
            c = dict(r)
            try:
                c["config"] = json.loads(c["config"]) if c.get("config") else {}
            except Exception:  # noqa: silenciado intencional — fallback seguro
                pass
            try:
                c["results"] = json.loads(c["results"]) if c.get("results") else None
            except Exception:  # noqa: silenciado intencional — fallback seguro
                pass
            try:
                c["log"] = json.loads(c["log"]) if c.get("log") else []
            except Exception:
                c["log"] = []
            campaigns.append(c)
        total = conn.execute("SELECT COUNT(*) FROM linkedin_campaigns").fetchone()[0]
        return {"campaigns": campaigns, "total": total}
    finally:
        conn.close()


@app.get("/api/linkedin/campaigns/{campaign_id}/log")
async def vm_get_campaign_log(campaign_id: int):
    conn = _get_li_db()
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


# ─── LinkedIn Fase 2: extra endpoints ────────────────────────────────────────

def _apply_linkedin_migration():
    """Apply 2026_06_linkedin_full.sql to the local DB if tables are missing."""
    sql_path = Path(__file__).parent / "migrations" / "2026_06_linkedin_full.sql"
    if not sql_path.exists():
        # Try VM path
        sql_path = Path.home() / ".hermes" / "scripts" / "migrations" / "2026_06_linkedin_full.sql"
    if not sql_path.exists():
        return
    try:
        conn = get_db()
        conn.executescript(sql_path.read_text(encoding="utf-8"))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[migration] LinkedIn migration error: {e}")

# Apply at startup
_apply_linkedin_migration()


@app.get("/api/linkedin/rate-limits")
async def vm_linkedin_rate_limits():
    """Return real rate limiter stats from LinkedInLimiter."""
    try:
        from linkedin.limiter import RateLimiter
        from linkedin import LinkedInConfig
        config = _build_li_config()
        limiter = RateLimiter(config)
        return limiter.get_stats()
    except Exception as e:
        return {"error": str(e), "warmup_complete": False}


@app.get("/api/linkedin/session-check")
async def vm_linkedin_session_check():
    """Check session validity + proxy state + auto-detect account type from LinkedIn DOM.

    Uses cached account_type if fresh (<24h); triggers background re-detection if stale.
    """
    try:
        from linkedin import LinkedInConfig
        from linkedin.account_detector import read_cached, detect_and_cache
        config = _build_li_config()
        session_file = Path(config.session_file)
        li_at = os.environ.get("LI_AT", "").strip()
        proxy_url = os.environ.get("LINKEDIN_PROXY", "").strip()
        proxy_configured = bool(proxy_url)
        # Proxy liveness check
        proxy_alive = False
        if proxy_configured:
            try:
                from urllib.parse import urlparse
                p = urlparse(proxy_url)
                import socket
                with socket.create_connection((p.hostname, p.port), timeout=2):
                    proxy_alive = True
            except Exception:
                proxy_alive = False
        else:
            proxy_alive = True

        session_ok = session_file.exists() or bool(li_at)

        # Account type: prefer cached detection over env config
        cached = read_cached()
        account_type = (cached or {}).get("account_type") or config.account_type or "free"
        account_type_source = "cache" if cached else "env"

        # If no cache or stale and session_ok, trigger async re-detect (fire-and-forget)
        if session_ok and not cached:
            async def _bg():
                try:
                    await detect_and_cache(config)
                except Exception as e:
                    pass
            try:
                spawn(_bg())
            except RuntimeError:
                pass

        return {
            "ok": session_ok,
            "email": config.account_email,
            "account_type": account_type,
            "account_type_source": account_type_source,
            "account_type_evidence": (cached or {}).get("evidence", []),
            "account_type_detected_at": (cached or {}).get("detected_at"),
            "proxy_configured": proxy_configured,
            "proxy_url": proxy_url if proxy_configured else None,
            "proxy_alive": proxy_alive,
            "session_file_exists": session_file.exists(),
            "has_li_at_env": bool(li_at),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/internal/account_type_set")
async def vm_account_type_set(request: Request):
    """Receive account_type detected by the browser extension (no Patchright needed).
    Writes directly to the cache file used by read_cached().
    Auth: X-Hermes-Token header.
    """
    expected = os.environ.get("HERMES_VM_AUTH_TOKEN", "")
    presented = request.headers.get("X-Hermes-Token", "")
    if not expected or presented != expected:
        raise HTTPException(403, "invalid token")
    body = await request.json()
    account_type = (body.get("account_type") or "").strip()
    if account_type not in ("free", "premium", "sales_navigator"):
        raise HTTPException(400, "invalid account_type")
    try:
        from linkedin.account_detector import write_cache
        evidence = body.get("evidence", []) + [f"src:{body.get('detected_from', 'extension')}"]
        if body.get("page_url"):
            evidence.append(f"page:{body['page_url'][:80]}")
        write_cache(account_type, evidence)
        return {"ok": True, "account_type": account_type, "updated_at": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/linkedin/detect-account-type")
async def vm_linkedin_detect_account_type():
    """Force a fresh auto-detection of account type (premium/free/sales_navigator)."""
    try:
        from linkedin.account_detector import detect_and_cache
        from linkedin import LinkedInConfig
        config = _build_li_config()
        result = await detect_and_cache(config)
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/linkedin/health")
async def vm_linkedin_health(force_refresh: bool = Query(False)):
    """Probe LinkedIn /feed/ via SOCKS5 + LI_AT and return cached health.
    Used by PC's pre-dispatch precheck so a user can't launch a campaign
    while LinkedIn is throttling — saves quota and avoids deepening the cooldown.
    """
    try:
        from linkedin.cooldown import check_health
        result = await check_health(force_refresh=force_refresh)
        return result
    except Exception as e:
        return {"state": "blocked", "reason": f"probe_exception:{e}"}


@app.post("/api/linkedin/health/clear")
async def vm_linkedin_health_clear():
    """Manually clear the cooldown cache (admin / debugging)."""
    try:
        from linkedin.cooldown import CACHE_FILE
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
        return {"ok": True, "note": "cache cleared — next request will probe live"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/linkedin/visited")
async def vm_linkedin_visited(limit: int = Query(100, ge=1, le=500),
                              days: int = Query(30, ge=1, le=180)):
    """List recently visited profile URLs (from linkedin_profiles cache)."""
    conn = get_db()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT profile_url, name, current_role, current_company, photo, last_seen_at, visit_count
            FROM linkedin_profiles
            WHERE last_seen_at >= ?
            ORDER BY last_seen_at DESC
            LIMIT ?
        """, (cutoff, limit)).fetchall()
        return {"profiles": [dict(r) for r in rows]}
    except Exception as e:
        return {"profiles": [], "error": str(e)}
    finally:
        conn.close()


@app.get("/api/linkedin/profiles")
async def vm_linkedin_profile_by_url(url: str = Query(...)):
    """Return cached profile by URL. If missing, trigger async hydration and return 202."""
    canonical = url.split("?")[0].rstrip("/")
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM linkedin_profiles WHERE profile_url=?",
            (canonical,)
        ).fetchone()
        if row:
            r = dict(row)
            if r.get("top_skills"):
                try:
                    r["top_skills"] = json.loads(r["top_skills"])
                except Exception:
                    r["top_skills"] = []
            r["_cache_hit"] = True
            return r
    finally:
        conn.close()

    # Cache miss — schedule async hydration
    async def _hydrate():
        try:
            from linkedin.company_finder import hydrate_profile
            await hydrate_profile(canonical, _build_li_config())
        except Exception as e:
            print(f"[profile hydrate] failed: {e}")

    spawn(_hydrate())
    return JSONResponse(
        status_code=202,
        content={"_cache_hit": False, "status": "hydrating", "profile_url": canonical}
    )


@app.get("/api/linkedin/companies/lookup")
async def vm_linkedin_company_lookup(name: str = Query(...)):
    """Aggregate profiles in cache by current_company to help lookup slug."""
    conn = get_db()
    try:
        # Fuzzy match on current_company
        rows = conn.execute("""
            SELECT current_company, current_role, COUNT(*) as n,
                   MAX(company_domain) as company_domain
            FROM linkedin_profiles
            WHERE LOWER(current_company) LIKE '%' || LOWER(?) || '%'
            GROUP BY current_company
            ORDER BY n DESC
            LIMIT 10
        """, (name,)).fetchall()
        return {"matches": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.post("/api/linkedin/comment/edit")
async def vm_linkedin_comment_edit(request: Request):
    body = await request.json()
    post_url = body.get("post_url")
    comment_id = body.get("comment_id")
    new_text = body.get("new_text", "")
    if not (post_url and comment_id and new_text):
        raise HTTPException(400, "post_url, comment_id, new_text required")
    try:
        from linkedin import LinkedInEngager
        engager = LinkedInEngager(_build_li_config())
        result = await engager.edit_comment(post_url, comment_id, new_text)
        # Update DB
        if result.get("ok"):
            conn = get_db()
            try:
                conn.execute("""
                    UPDATE linkedin_engagements
                    SET comment_text=?, edited_at=?
                    WHERE comment_id=?
                """, (new_text, result.get("edited_at"), comment_id))
                conn.commit()
            finally:
                conn.close()
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/linkedin/comment/delete")
async def vm_linkedin_comment_delete(request: Request):
    body = await request.json()
    post_url = body.get("post_url")
    comment_id = body.get("comment_id")
    if not (post_url and comment_id):
        raise HTTPException(400, "post_url, comment_id required")
    try:
        from linkedin import LinkedInEngager
        engager = LinkedInEngager(_build_li_config())
        result = await engager.delete_comment(post_url, comment_id)
        if result.get("ok"):
            conn = get_db()
            try:
                conn.execute("""
                    UPDATE linkedin_engagements
                    SET deleted_at=?
                    WHERE comment_id=?
                """, (result.get("deleted_at"), comment_id))
                conn.commit()
            finally:
                conn.close()
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/internal/li_at_update")
async def vm_li_at_update(request: Request):
    """Receive a new li_at cookie from the PC (forwarded by server.py).
    Writes to ~/.hermes/.env so next browser launch picks it up via
    `os.environ.get("LI_AT")` in stealth.py.
    Auth: X-Hermes-Token header must match HERMES_VM_AUTH_TOKEN env.
    """
    expected = os.environ.get("HERMES_VM_AUTH_TOKEN", "")
    presented = request.headers.get("X-Hermes-Token", "")
    if not expected or presented != expected:
        raise HTTPException(403, "invalid token")
    body = await request.json()
    li_at = (body.get("li_at") or "").strip()
    if not li_at or len(li_at) < 30:
        raise HTTPException(400, "li_at missing or too short")
    env_path = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / ".env"
    try:
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()
        else:
            lines = []
        seen = False
        new_lines = []
        for ln in lines:
            if ln.startswith("LI_AT="):
                new_lines.append(f"LI_AT={li_at}")
                seen = True
            else:
                new_lines.append(ln)
        if not seen:
            new_lines.append(f"LI_AT={li_at}")
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        # Update current process env so the very next browser launch sees it
        os.environ["LI_AT"] = li_at
        # Also delete any stored session file (forces re-create with new cookie)
        try:
            sess = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / "data" / "sessions"
            for f in sess.glob("*.json"):
                f.unlink()
        except Exception:  # noqa: silenciado intencional — fallback seguro
            pass
        return {"ok": True, "updated_at": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/linkedin/connection/refresh")
async def vm_linkedin_connection_refresh(request: Request):
    """Trigger refresh of pending connection statuses (visit each profile)."""
    body = {}
    try:
        body = await request.json()
    except Exception:  # noqa: silenciado intencional — fallback seguro
        pass
    max_per_run = int(body.get("max", 30))
    try:
        from linkedin.connector import refresh_connection_statuses
        result = await refresh_connection_statuses(_build_li_config(), max_per_run=max_per_run)
        return result
    except Exception as e:
        return {"checked": 0, "updated": 0, "error": str(e)}


# ─── Push progress events to PC (real-time) ──────────────────────────────────

PC_EVENT_URL = os.environ.get("HERMES_PC_EVENT_URL", "http://127.0.0.1:55000/api/internal/linkedin/event")

async def _push_event_to_pc(campaign_id: int, msg: str, phase: str = "info",
                            progress: Optional[int] = None,
                            partial_results: Optional[dict] = None):
    """Fire-and-forget HTTP POST to PC's internal event endpoint."""
    try:
        import httpx
        payload = {
            "campaign_id": campaign_id,
            "msg": msg,
            "phase": phase,
            "progress": progress,
            "partial_results": partial_results,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(PC_EVENT_URL, json=payload)
    except Exception:
        # Silent — push is best-effort
        pass


# Monkey-patch _li_log to also push to PC
_original_li_log = _li_log

def _li_log_with_push(campaign_id: int, msg: str, phase: str = "info"):
    _original_li_log(campaign_id, msg, phase)
    # Read partial results to send progress
    try:
        conn = _get_li_db()
        row = conn.execute(
            "SELECT progress, results FROM linkedin_campaigns WHERE id=?",
            (campaign_id,)
        ).fetchone()
        conn.close()
        progress = row["progress"] if row else None
        partial = json.loads(row["results"]) if row and row["results"] else None
    except Exception:
        progress = None
        partial = None
    # Fire-and-forget
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_push_event_to_pc(campaign_id, msg, phase, progress, partial))
    except RuntimeError:
        # Not in a running loop — skip push
        pass


_li_log = _li_log_with_push


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8420, log_level="info")
