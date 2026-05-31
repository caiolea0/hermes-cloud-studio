"""Hermes Command Center v2 — VM API Bridge.

FastAPI server on the VM that serves prospect data, activity logs,
pipeline status, scraper control, and photo references to the dashboard.
"""
import json
import os
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv()
HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
VM_AUTH_TOKEN = os.environ.get("HERMES_VM_AUTH_TOKEN", "")
DB_PATH = HERMES_HOME / "data" / "command_center.db"
DATA_DIR = HERMES_HOME / "data"


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
    yield


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
    if not VM_AUTH_TOKEN:
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        token = request.headers.get("X-Hermes-Token", "")
        if token != VM_AUTH_TOKEN:
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
        except Exception:
            pass

    # Try active checkpoint first
    checkpoint = {}
    if checkpoint_file.exists():
        try:
            checkpoint = json.loads(checkpoint_file.read_text(encoding="utf-8"))
        except Exception:
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
        except Exception:
            pass

    # If no active checkpoint, try last run (gosom first, then legacy)
    last_run = {}
    if not checkpoint:
        for lr_file in [gosom_last_run, last_run_file]:
            if lr_file.exists():
                try:
                    last_run = json.loads(lr_file.read_text(encoding="utf-8"))
                    break
                except Exception:
                    pass

    log_tail = []
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    log_file = log_dir / f"night_scraper_{today}.log"
    if log_file.exists():
        try:
            lines = log_file.read_text(encoding="utf-8").strip().split("\n")
            log_tail = lines[-10:]
        except Exception:
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
        except Exception:
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
        except Exception:
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
    except Exception:
        pass

    cron_jobs = []
    jobs_file = HERMES_HOME / "cron" / "jobs.json"
    if jobs_file.exists():
        try:
            cron_jobs = json.loads(jobs_file.read_text())
        except Exception:
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8420, log_level="info")
