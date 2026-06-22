"""Hermes Daemon — 24/7 Autonomous Orchestrator.

Runs continuously on VM. Decides what to do, when to do it,
and adapts based on rate limits, errors, and time of day.

Broadcasts all state changes via WebSocket for visual dashboard.
"""
import asyncio
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, field

import httpx
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

load_dotenv(_ROOT / ".env")

from core.pipeline import PipelineRunner
from core.state import is_subsystem_paused
from config import settings
from linkedin.ollama_router import router as ollama_router, OllamaUnavailable

logger = logging.getLogger("hermes.daemon")

# --- Configuration ---
VM_API_URL = os.environ.get("HERMES_VM_API", "http://localhost:8420")
LOCAL_API_URL = os.environ.get("HERMES_LOCAL_API", "http://localhost:55000")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
DB_PATH = Path(__file__).parent.parent / "hermes_local.db"

# Rate limit safety margins (stop at 80% of limit)
RATE_LIMIT_BUFFER = 0.80

# Discovery cooldown: mínimo de horas entre runs OSM para a mesma área/cidade.
# Evita loop infinito quando _pipeline_needs_fuel() < 50 e prospects não migram
# para hermes_local.db entre ciclos (daemon container ↔ hermes-api são DBs distintos).
DISCOVERY_COOLDOWN_HOURS: float = float(os.environ.get("HERMES_DISCOVERY_COOLDOWN_H", "6"))

# Error circuit breaker
MAX_CONSECUTIVE_ERRORS = 5
ERROR_PAUSE_SECONDS = 600  # 10 minutes

# Brazilian holidays 2026 (outreach pauses)
BR_HOLIDAYS = [
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-04-03",
    "2026-04-21", "2026-05-01", "2026-06-04", "2026-09-07",
    "2026-10-12", "2026-11-02", "2026-11-15", "2026-12-25",
]


class DaemonState(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    PAUSED = "paused"
    COOLDOWN = "cooldown"
    ERROR = "error"
    SLEEPING = "sleeping"


class TaskCategory(str, Enum):
    DISCOVERY = "discovery"
    ENRICHMENT = "enrichment"
    OUTREACH = "outreach"
    REPLY = "reply"
    AUDIT = "audit"
    SCORING = "scoring"
    REPORTING = "reporting"
    SYSTEM = "system"
    COBAIA = "cobaia"  # F.7 C2 — P0 absolute override


@dataclass
class Task:
    type: str
    category: TaskCategory
    data: Any = None
    priority: int = 5  # 1=highest, 10=lowest
    description: str = ""


@dataclass
class ChannelState:
    name: str
    daily_used: int = 0
    daily_limit: int = 50
    health: float = 1.0  # 0.0-1.0 (bounce/spam rate inverse)
    warmup_day: int = 0
    warmup_complete: bool = False
    last_action_at: Optional[datetime] = None
    errors_today: int = 0
    is_active: bool = True

    @property
    def usage_ratio(self) -> float:
        return self.daily_used / max(self.daily_limit, 1)

    @property
    def can_send(self) -> bool:
        return (
            self.is_active
            and self.usage_ratio < RATE_LIMIT_BUFFER
            and self.health > 0.3
            and self.errors_today < 10
        )


@dataclass
class DaemonStats:
    discovered: int = 0
    enriched: int = 0
    contacted: int = 0
    replied: int = 0
    meetings: int = 0
    errors: int = 0
    decisions: int = 0


class HermesDaemon:
    """24/7 autonomous orchestrator. Decides and executes tasks based on time, state, and priorities."""

    def __init__(self):
        self.state = DaemonState.IDLE
        self.current_task: Optional[Task] = None
        self.energy = 1.0  # Decays with rate limit proximity, resets at midnight
        self.stats_today = DaemonStats()
        self.stats_week = DaemonStats()
        self.consecutive_errors = 0
        self.started_at = datetime.now(timezone.utc)
        self.last_heartbeat = datetime.now(timezone.utc)
        self.paused_until: Optional[datetime] = None
        self._running = False

        # Discovery cooldown: evita re-run dentro de DISCOVERY_COOLDOWN_HOURS
        # (in-memory; reset no restart — intencional, 1 run por boot é OK)
        self._last_discovery_at: Optional[datetime] = None

        # Channel states
        self.channels: dict[str, ChannelState] = {
            "linkedin": ChannelState(name="linkedin", daily_limit=70, warmup_day=14, warmup_complete=True),
            "email": ChannelState(name="email", daily_limit=75, warmup_day=0, warmup_complete=False),
            "whatsapp": ChannelState(name="whatsapp", daily_limit=25, is_active=False),
            "instagram": ChannelState(name="instagram", daily_limit=50, is_active=False),
        }

        # Decision log (last 100 decisions for dashboard)
        self.decision_log: list[dict] = []

        # Pipeline runner compartilhado (core/pipeline.py) — usado em P3/P4/P5.
        # Em container usa VM_API_URL (hermes-api:8420); fora do container usa LOCAL_API_URL.
        _pipeline_api = VM_API_URL if os.environ.get("HERMES_LOCAL_API") else LOCAL_API_URL
        self.pipeline = PipelineRunner(
            api_url=_pipeline_api,
            auth_token=os.environ.get("HERMES_VM_AUTH_TOKEN", os.environ.get("HERMES_AUTH_TOKEN", "")),
        )

        self._init_db()

    def _init_db(self):
        """Create daemon-specific tables."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.executescript("""
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
                level TEXT NOT NULL,
                category TEXT NOT NULL,
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

            CREATE TABLE IF NOT EXISTS inbox_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prospect_id INTEGER NOT NULL,
                channel TEXT NOT NULL DEFAULT 'unknown',
                body TEXT NOT NULL DEFAULT '',
                received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                handled INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS sequence_enrollments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prospect_id INTEGER NOT NULL,
                sequence_id TEXT NOT NULL DEFAULT 'default',
                current_step INTEGER NOT NULL DEFAULT 0,
                next_action_at TIMESTAMP NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (prospect_id, sequence_id)
            );

            CREATE TABLE IF NOT EXISTS telegram_stop_signals (
                prospect_id INTEGER NOT NULL,
                channel TEXT NOT NULL DEFAULT 'all',
                received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (prospect_id, channel)
            );

            CREATE TABLE IF NOT EXISTS sequence_nodes (
                id TEXT PRIMARY KEY,
                sequence_id INTEGER NOT NULL,
                node_type TEXT NOT NULL,
                channel TEXT,
                action_type TEXT,
                position_x REAL NOT NULL DEFAULT 0,
                position_y REAL NOT NULL DEFAULT 0,
                config_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS sequence_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence_id INTEGER NOT NULL,
                from_node TEXT NOT NULL,
                to_node TEXT NOT NULL,
                edge_type TEXT NOT NULL DEFAULT 'default'
            );

            CREATE INDEX IF NOT EXISTS idx_daemon_log_ts ON daemon_log(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_daemon_log_cat ON daemon_log(category);
            CREATE INDEX IF NOT EXISTS idx_daemon_decisions_ts ON daemon_decisions(timestamp DESC);
            -- also defined in migrations/2026_06_daemon_sequence_inbox.sql (idempotent — safe dup)
            CREATE INDEX IF NOT EXISTS idx_inbox_replies_handled ON inbox_replies(handled, received_at);
            CREATE INDEX IF NOT EXISTS idx_seq_enrollments_due ON sequence_enrollments(completed, next_action_at);

            INSERT OR IGNORE INTO daemon_state (id, state, started_at, last_heartbeat)
            VALUES (1, 'idle', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
        """)
        conn.close()

    # --- State Management ---

    async def set_state(self, new_state: DaemonState, task: Optional[Task] = None):
        """Update state and broadcast via WebSocket."""
        self.state = new_state
        self.current_task = task
        self.last_heartbeat = datetime.now(timezone.utc)

        # Persist to DB
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            UPDATE daemon_state SET
                state = ?, current_task_type = ?, current_task_detail = ?,
                energy = ?, last_heartbeat = ?, stats_today = ?, stats_week = ?
            WHERE id = 1
        """, (
            new_state.value,
            task.type if task else None,
            task.description if task else None,
            self.energy,
            self.last_heartbeat.isoformat(),
            json.dumps(self.stats_today.__dict__),
            json.dumps(self.stats_week.__dict__),
        ))
        conn.commit()
        conn.close()

        # Broadcast state change
        await self._broadcast({
            "type": "daemon_state",
            "state": new_state.value,
            "task": task.type if task else None,
            "detail": task.description if task else None,
            "energy": round(self.energy, 2),
            "stats": self.stats_today.__dict__,
        })

    async def log_event(self, level: str, category: str, message: str,
                        metadata: dict = None, visual_event: dict = None):
        """Log event to DB and broadcast for live feed."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO daemon_log (level, category, message, metadata, visual_event) VALUES (?, ?, ?, ?, ?)",
            (level, category, message, json.dumps(metadata) if metadata else None,
             json.dumps(visual_event) if visual_event else None)
        )
        conn.commit()
        conn.close()

        # Broadcast for live feed (legacy 'activity' + F.2.3 canonical 'daemon.log_event')
        ts = datetime.now(timezone.utc).isoformat()
        await self._broadcast({
            "type": "activity",
            "category": category,
            "action": message,
            "level": level,
            "metadata": metadata or {},
            "visual_event": visual_event,
            "timestamp": ts,
        })
        await self._broadcast({
            "type": "daemon.log_event",
            "category": category,
            "message": message,
            "level": level,
            "metadata": metadata or {},
            "visual_event": visual_event,
            "timestamp": ts,
        })

    async def log_decision(self, action: str, reason: str, context: dict = None):
        """Log AI decision for transparency."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO daemon_decisions (action, reason, context) VALUES (?, ?, ?)",
            (action, reason, json.dumps(context) if context else None)
        )
        conn.commit()
        conn.close()

        self.decision_log.append({
            "action": action, "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        if len(self.decision_log) > 100:
            self.decision_log = self.decision_log[-100:]

        self.stats_today.decisions += 1

        # Legacy 'decision' + F.2.3 canonical 'daemon.decision' (decision_event tag pro grep_present harness)
        ts = datetime.now(timezone.utc).isoformat()
        await self._broadcast({
            "type": "decision",
            "action": action,
            "reason": reason,
        })
        await self._broadcast({
            "type": "daemon.decision",
            "event": "decision_event",
            "action": action,
            "reason": reason,
            "context": context or {},
            "timestamp": ts,
        })

    # --- Core Loop ---

    async def run_forever(self):
        """Main daemon loop. Runs until stopped."""
        self._running = True
        logger.info("Hermes Daemon starting 24/7 operation")
        await self.set_state(DaemonState.IDLE)

        while self._running:
            try:
                # Check if paused
                if self.paused_until and datetime.now(timezone.utc) < self.paused_until:
                    await self.set_state(DaemonState.PAUSED)
                    await asyncio.sleep(30)
                    continue

                # Check if in error cooldown
                if self.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    await self._enter_error_cooldown()
                    continue

                # Check time-based sleeping
                if self._should_sleep():
                    await self.set_state(DaemonState.SLEEPING)
                    await asyncio.sleep(60)
                    continue

                # Midnight reset
                self._check_daily_reset()

                # Decide next action
                task = await self.decide_next_action()

                if task:
                    await self.set_state(DaemonState.WORKING, task)
                    await self.log_decision(
                        action=task.type,
                        reason=task.description,
                        context={"category": task.category.value, "priority": task.priority}
                    )

                    success = await self.execute_task(task)

                    if success:
                        self.consecutive_errors = 0
                    else:
                        self.consecutive_errors += 1
                        self.stats_today.errors += 1

                    await self.set_state(DaemonState.IDLE)
                    # Brief pause between tasks
                    await asyncio.sleep(5)
                else:
                    await self.set_state(DaemonState.IDLE)
                    await asyncio.sleep(30)

            except Exception as e:
                logger.exception(f"Daemon loop error: {e}")
                self.consecutive_errors += 1
                await self.log_event("error", "system", f"Daemon error: {str(e)[:200]}")
                await asyncio.sleep(10)

    async def stop(self):
        """Graceful shutdown."""
        self._running = False
        await self.set_state(DaemonState.IDLE)
        logger.info("Hermes Daemon stopped")

    # --- Decision Engine ---

    async def decide_next_action(self) -> Optional[Task]:
        """AI-powered decision engine. Prioritizes based on time, state, and urgency."""
        now = datetime.now()
        hour = now.hour
        weekday = now.weekday()  # 0=Monday

        # Holiday check (no outreach on BR holidays)
        today_str = now.strftime("%Y-%m-%d")
        is_holiday = today_str in BR_HOLIDAYS
        is_weekend = weekday >= 5

        # PRIORITY 0 (F.7 C2 D8): Cobaia warmup absolute override — runs BEFORE P1-P7.
        # Skipped gracefully if cobaia module unavailable or warmup inactive/paused.
        cobaia_task = await self._get_cobaia_action()
        if cobaia_task is not None:
            return cobaia_task

        # PRIORITY 1: Pending replies (always highest priority during business hours)
        if 7 <= hour <= 20 and not is_holiday:
            pending_replies = await self._get_pending_replies()
            if pending_replies:
                return Task(
                    type="handle_reply",
                    category=TaskCategory.REPLY,
                    data=pending_replies[0],
                    priority=1,
                    description=f"Reply from {pending_replies[0].get('prospect_name', 'unknown')}"
                )

        # PRIORITY 2: Sequence steps due (business hours only)
        # Hermes 2.0: congelado quando FEATURE_LINKEDIN=off (vira handoff push em F6)
        if settings.feature_linkedin and 8 <= hour <= 18 and not is_holiday and not is_weekend:
            due_steps = await self._get_due_sequence_steps()
            if due_steps:
                return Task(
                    type="execute_sequence_step",
                    category=TaskCategory.OUTREACH,
                    data=due_steps[0],
                    priority=2,
                    description=f"Sequence step: {due_steps[0].get('channel', '?')} → {due_steps[0].get('prospect_name', '?')}"
                )

        # PRIORITY 3: Enrichment (continuous, rate-limited)
        if 6 <= hour <= 22:
            unenriched = await self._get_unenriched_prospects(limit=5)
            if unenriched:
                return Task(
                    type="enrich_batch",
                    category=TaskCategory.ENRICHMENT,
                    data=unenriched,
                    priority=3,
                    description=f"Enrich {len(unenriched)} prospects (waterfall)"
                )

        # PRIORITY 4: Discovery (off-peak: 0-6, or anytime if pipeline empty)
        # Cooldown guard: impede re-run dentro de DISCOVERY_COOLDOWN_HOURS mesmo
        # que _pipeline_needs_fuel() retorne True (daemon DB ≠ hermes-api DB no container).
        if not is_subsystem_paused("scraper"):
            cooldown_ok = (
                self._last_discovery_at is None
                or (datetime.now(timezone.utc) - self._last_discovery_at).total_seconds()
                >= DISCOVERY_COOLDOWN_HOURS * 3600
            )
            if cooldown_ok and (0 <= hour <= 6 or await self._pipeline_needs_fuel()):
                if self._should_scrape_today(weekday):
                    config = self._get_scraper_config(weekday)
                    return Task(
                        type="discovery_scrape",
                        category=TaskCategory.DISCOVERY,
                        data=config,
                        priority=4,
                        description=f"Discovery: {config.get('category', 'mixed')} in {config.get('city', 'Cuiabá')}"
                    )

        # PRIORITY 5: Batch audit (off-peak)
        if not is_subsystem_paused("audit"):
            if 0 <= hour <= 7 or 20 <= hour <= 23:
                unaudited = await self._get_unaudited_prospects(limit=20)
                if unaudited:
                    return Task(
                        type="batch_audit",
                        category=TaskCategory.AUDIT,
                        data=unaudited,
                        priority=5,
                        description=f"Audit {len(unaudited)} prospects' websites"
                    )

        # PRIORITY 6: Score recalculation (nightly)
        if 22 <= hour <= 23 and not self._scored_today():
            return Task(
                type="recalculate_scores",
                category=TaskCategory.SCORING,
                priority=6,
                description="Recalculate predictive scores with new data"
            )

        # PRIORITY 7: Weekly report (Sunday evening)
        if weekday == 6 and 19 <= hour <= 21 and not self._reported_this_week():
            return Task(
                type="weekly_report",
                category=TaskCategory.REPORTING,
                priority=7,
                description="Generate weekly performance report"
            )

        return None  # Nothing to do

    # --- Task Execution ---

    async def execute_task(self, task: Task) -> bool:
        """Execute a task and return success status."""
        try:
            handlers = {
                "handle_reply": self._exec_handle_reply,
                "execute_sequence_step": self._exec_sequence_step,
                "enrich_batch": self._exec_enrich_batch,
                "discovery_scrape": self._exec_discovery,
                "batch_audit": self._exec_batch_audit,
                "recalculate_scores": self._exec_recalculate_scores,
                "weekly_report": self._exec_weekly_report,
                "cobaia_warmup_action": self._exec_cobaia_warmup,  # F.7 C2
            }

            handler = handlers.get(task.type)
            if handler:
                result = await handler(task.data)
                await self.log_event(
                    "info", task.category.value,
                    f"Completed: {task.description}",
                    metadata={"result": str(result)[:500]},
                    visual_event={"type": "task_complete", "category": task.category.value}
                )
                return True
            else:
                logger.warning(f"No handler for task type: {task.type}")
                return False

        except Exception as e:
            await self.log_event(
                "error", task.category.value,
                f"Failed: {task.description} — {str(e)[:200]}",
                visual_event={"type": "task_error", "category": task.category.value}
            )
            return False

    # --- Task Handlers ---

    async def _exec_handle_reply(self, data: dict) -> dict:
        """Handle an incoming reply from a prospect."""
        prospect_id = data.get("prospect_id")
        message = data.get("message", "")
        channel = data.get("channel", "email")

        # Classify intent using local LLM
        intent = await self._classify_reply_intent(message, data)

        await self.log_event(
            "info", "reply",
            f"Reply classified: {intent} from {data.get('prospect_name', '?')}",
            metadata={"prospect_id": prospect_id, "intent": intent, "channel": channel},
            visual_event={
                "type": "reply_received",
                "channel": channel,
                "prospect_name": data.get("prospect_name", ""),
                "intent": intent,
            }
        )

        self.stats_today.replied += 1

        # Auto-respond based on intent
        if intent in ("interested", "meeting_request"):
            # Notify human via Telegram, wait 5 min, then auto-send
            await self._notify_telegram(
                f"🔥 Reply from {data.get('prospect_name')}: \"{message[:100]}\"\n"
                f"Intent: {intent}\nChannel: {channel}\n"
                f"Auto-responding in 5min unless you reply STOP"
            )
            await asyncio.sleep(300)  # 5 min human window
            if await self._check_human_stop(prospect_id, channel):
                return
            await self._send_auto_response(prospect_id, intent, channel)
        elif intent == "questions":
            await self._send_auto_response(prospect_id, intent, channel)
        elif intent == "not_interested":
            await self._opt_out_prospect(prospect_id)
        elif intent == "not_now":
            await self._schedule_followup(prospect_id, days=30)

        return {"intent": intent, "action_taken": True}

    async def _exec_sequence_step(self, data: dict) -> dict:
        """Execute a single sequence step (send message via channel)."""
        channel = data.get("channel", "email")
        prospect_id = data.get("prospect_id")
        template = data.get("template", "")
        prospect_name = data.get("prospect_name", "")

        # Check channel can send
        ch = self.channels.get(channel)
        if not ch or not ch.can_send:
            await self.log_event("warning", "outreach",
                                 f"Channel {channel} cannot send (limit/health)")
            return {"sent": False, "reason": "channel_limit"}

        # Send via channel adapter
        success = await self._send_via_channel(channel, prospect_id, template, data)

        if success:
            ch.daily_used += 1
            ch.last_action_at = datetime.now(timezone.utc)
            self.stats_today.contacted += 1
            self._update_energy()

            await self.log_event(
                "info", "outreach",
                f"Sent {channel} to {prospect_name}",
                metadata={"prospect_id": prospect_id, "channel": channel},
                visual_event={
                    "type": "message_sent",
                    "channel": channel,
                    "prospect_name": prospect_name,
                    "prospect_id": prospect_id,
                }
            )

            # Broadcast channel update
            await self._broadcast({
                "type": "channel_update",
                "channel": channel,
                "daily_used": ch.daily_used,
                "daily_limit": ch.daily_limit,
                "health": ch.health,
                "warmup_day": ch.warmup_day,
            })

        return {"sent": success, "channel": channel}

    async def _exec_enrich_batch(self, data: list) -> dict:
        """Enrich a batch of prospects via waterfall."""
        enriched_count = 0
        for prospect in data:
            try:
                result = await self._enrich_single(prospect)
                if result.get("fields_filled", 0) > 0:
                    enriched_count += 1
                    await self.log_event(
                        "info", "enrichment",
                        f"Enriched {prospect.get('business_name', '?')}: +{result['fields_filled']} fields",
                        visual_event={
                            "type": "prospect_enriched",
                            "prospect_name": prospect.get("business_name", ""),
                            "fields": result.get("fields_filled", 0),
                        }
                    )
                # Rate limit between enrichment calls
                await asyncio.sleep(2)
            except Exception as e:
                logger.warning(f"Enrich failed for {prospect.get('id')}: {e}")

        self.stats_today.enriched += enriched_count
        return {"enriched": enriched_count, "total": len(data)}

    async def _exec_discovery(self, config: dict) -> dict:
        """Discovery multi-source: Overpass (OSM) primário, scraper API como fallback."""
        overpass_url = os.environ.get("OVERPASS_URL", "http://localhost:12345")
        await self.log_event(
            "info", "discovery",
            f"Discovery OSM (Overpass): {overpass_url}",
            visual_event={"type": "discovery_started", "source": "osm"}
        )

        # Fonte primária: Overpass self-hosted (H2-F1+)
        try:
            result = await self.pipeline.discovery_osm(overpass_url=overpass_url)
            found = result.get("new", 0)
            if found > 0 or result.get("total_found", 0) > 0:
                self.stats_today.discovered += found
                self._last_discovery_at = datetime.now(timezone.utc)
                await self.log_event(
                    "info", "discovery",
                    f"OSM: {found} novos prospects de {result.get('total_found', 0)} POIs — próximo run em {DISCOVERY_COOLDOWN_HOURS}h",
                )
                return {"found": found, "source": "osm", "total_osm": result.get("total_found", 0)}
        except Exception as exc:
            logger.warning("_exec_discovery OSM falhou: %s — tentando scraper fallback", exc)

        # Fallback: scraper API (gosom/Google Maps — legado)
        # Usa HERMES_VM_AUTH_TOKEN pois VM_API_URL aponta pra hermes-api no container.
        await self.log_event("info", "discovery", "Fallback: scraper API (legado)")
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{VM_API_URL}/api/scraper/start",
                json=config,
                headers=self._auth_headers()
            )
            if resp.status_code == 200:
                result = resp.json()
                found = result.get("found", 0)
                self.stats_today.discovered += found
                self._last_discovery_at = datetime.now(timezone.utc)
                return {"found": found, "source": "scraper_fallback"}
            else:
                raise Exception(f"Scraper start failed: {resp.status_code}")

    async def _exec_batch_audit(self, data: list) -> dict:
        """Run website audit batch via PipelineRunner (shared core/pipeline.py)."""
        return await self.pipeline.audit_pending(limit=len(data) if data else None)

    async def _exec_recalculate_scores(self, _) -> dict:
        """Trigger ML score recalculation for all prospects."""
        # intelligence/scoring.py not implemented (F.future)
        await self.log_event("info", "scoring", "Score recalculation deferred — intelligence/scoring not implemented")
        return {"status": "not_implemented", "code": 501}

    async def _exec_weekly_report(self, _) -> dict:
        """Generate and send weekly performance report (Markdown via Telegram; PDF F.future)."""
        await self._notify_telegram(
            f"📊 Weekly Report\n"
            f"Discovered: {self.stats_week.discovered}\n"
            f"Enriched: {self.stats_week.enriched}\n"
            f"Contacted: {self.stats_week.contacted}\n"
            f"Replied: {self.stats_week.replied}\n"
            f"Meetings: {self.stats_week.meetings}\n"
            f"Errors: {self.stats_week.errors}\n"
            f"Decisions: {self.stats_week.decisions}"
        )
        return {"sent": True}

    # --- F.7 C2 Cobaia Warmup Methods ---

    async def _get_cobaia_action(self) -> Optional[Task]:
        """P0 absolute override: return cobaia Task if warmup active + within hours.

        Returns None (fallback to P1-P7) if:
          - cobaia_warmup module unavailable
          - no warmup state exists
          - state is paused
          - outside working hours (07h-22h Cuiaba, no weekends)
          - today's caps already reached
        """
        if not settings.feature_linkedin:
            return None  # Hermes 2.0: LinkedIn congelado (FEATURE_LINKEDIN=off)
        try:
            from linkedin.cobaia_warmup import CobaiaWarmupManager
            from linkedin.config import CobaiaConfig
            mgr = CobaiaWarmupManager(cfg=CobaiaConfig())
            status = mgr.get_status()
            if not status.get("exists"):
                return None
            if status.get("phase") == "paused":
                return None
            if not status.get("within_working_hours"):
                return None
            # Check if any caps remain today
            caps = status.get("caps_today", {})
            metrics = status.get("today_metrics", {})
            connects_remain = max(0, caps.get("connects", 0) - metrics.get("connects_sent", 0))
            engagements_remain = max(0, caps.get("engagements", 0) - metrics.get("engagements_count", 0))
            views_remain = max(0, caps.get("views", 0) - metrics.get("views_count", 0))
            if connects_remain == 0 and engagements_remain == 0 and views_remain == 0:
                return None
            return Task(
                type="cobaia_warmup_action",
                category=TaskCategory.COBAIA,
                data=status,
                priority=0,
                description=f"Cobaia warmup day={status.get('current_day')} phase={status.get('phase')}",
            )
        except Exception as exc:
            logger.debug("cobaia P0 check skipped: %s", exc)
            return None

    async def _exec_cobaia_warmup(self, data: dict) -> dict:
        """Execute cobaia warmup action via Brain.decide (F.7 C2).

        data: warmup status dict from _get_cobaia_action().
        LinkedIn calls are STUBBED in C1/C2 — real wiring in C6.
        """
        from linkedin.cobaia_warmup import CobaiaWarmupManager
        from linkedin.config import CobaiaConfig
        from core.cobaia_metrics import update_cobaia_daily_metric

        account_handle = data.get("account_handle", "caio-leao-cobaia")
        phase = data.get("phase", "lurking")
        current_day = data.get("current_day", 0)
        caps = data.get("caps_today", {})
        metrics = data.get("today_metrics", {})

        # Brain.decide() for observability + action selection
        try:
            from brain.decide import Brain
            brain = Brain()
            brain_result = await brain.decide(
                intent="cobaia_warmup_next_action",
                context={
                    "current_day": current_day,
                    "phase": phase,
                    "caps_today": caps,
                    "today_metrics": metrics,
                    "errors_24h": data.get("consecutive_errors", 0),
                },
                requester="brain-f7-cobaia",
            )
            action_data = brain_result.get("result", {}).get("final_answer") or {}
            if not action_data:
                # fallback: extract from direct result
                action_data = brain_result.get("final_answer") or {}
        except Exception as exc:
            logger.warning("cobaia Brain.decide failed, using fallback: %s", exc)
            from brain.cobaia_intent import decide_cobaia_warmup_action
            action_data = decide_cobaia_warmup_action({
                "current_day": current_day,
                "phase": phase,
                "caps_today": caps,
                "today_metrics": metrics,
            })

        action = action_data.get("action")
        skill_name = action_data.get("skill_name")

        if not action:
            await self.log_event("info", "cobaia", f"cobaia no action: {action_data.get('status')}")
            return {"skipped": True, "reason": action_data.get("status")}

        # Real VM dispatch via F.7 C6 path (UX-RM-F1-A: stub removed)
        from daemon.cobaia_warmup_scheduler import _dispatch_cobaia_session_to_vm
        dispatch_result = _dispatch_cobaia_session_to_vm(phase, caps, account_handle)

        # Runtime guard: refuse if stub path somehow reached in production
        if dispatch_result.get("stub") or dispatch_result.get("result") == "mock_success":
            raise RuntimeError(
                f"F1-A: stub path reached in production cobaia warmup — refusing. result={dispatch_result!r}"
            )

        # Update daily metrics based on action type
        metric_map = {
            "engagement_like_post": "engagements_count",
            "engagement_comment_post": "engagements_count",
            "connection_request": "connects_sent",
            "profile_view": "views_count",
        }
        metric_name = metric_map.get(action, "engagements_count")
        try:
            update_cobaia_daily_metric(account_handle, metric_name)
        except Exception as exc:
            logger.warning("cobaia metric update failed: %s", exc)

        # Reset consecutive errors only when VM dispatch succeeded
        mgr = CobaiaWarmupManager(cfg=CobaiaConfig())
        if not dispatch_result.get("error"):
            try:
                mgr.reset_errors(account_handle)
            except Exception:
                pass

        if dispatch_result.get("error"):
            await self.log_event(
                "warning", "cobaia",
                f"cobaia {phase} day={current_day}: {action} via {skill_name} — VM dispatch error",
                metadata={"action": action, "phase": phase, "day": current_day, "error": dispatch_result["error"]},
            )
            return {"action": action, "skill": skill_name, "error": dispatch_result["error"], "metric_updated": metric_name}

        await self.log_event(
            "info", "cobaia",
            f"cobaia {phase} day={current_day}: {action} via {skill_name} — real dispatch",
            metadata={"action": action, "phase": phase, "day": current_day, "session_id": dispatch_result.get("session_id")},
        )
        return {"action": action, "skill": skill_name, "dispatched": True, "metric_updated": metric_name, "session_id": dispatch_result.get("session_id")}

    # --- Helper Methods ---

    def _should_sleep(self) -> bool:
        """Determine if daemon should sleep (low-activity hours with nothing to do)."""
        hour = datetime.now().hour
        # Only truly sleep 6-7 AM (transition period, nothing scheduled)
        return 6 <= hour < 7

    def _check_daily_reset(self):
        """Reset daily counters at midnight."""
        now = datetime.now()
        if now.hour == 0 and now.minute < 2:
            self.stats_today = DaemonStats()
            self.energy = 1.0
            for ch in self.channels.values():
                ch.daily_used = 0
                ch.errors_today = 0
            logger.info("Daily counters reset")

    def _update_energy(self):
        """Recalculate energy based on rate limit proximity across channels."""
        if not self.channels:
            return
        active_channels = [ch for ch in self.channels.values() if ch.is_active]
        if not active_channels:
            return
        avg_usage = sum(ch.usage_ratio for ch in active_channels) / len(active_channels)
        self.energy = max(0.0, 1.0 - avg_usage)

    async def _enter_error_cooldown(self):
        """Enter cooldown after too many consecutive errors."""
        await self.set_state(DaemonState.ERROR)
        await self.log_event(
            "error", "system",
            f"Error circuit breaker: {self.consecutive_errors} consecutive errors. Pausing {ERROR_PAUSE_SECONDS}s.",
            visual_event={"type": "circuit_breaker", "pause_seconds": ERROR_PAUSE_SECONDS}
        )
        await self._notify_telegram(
            f"⚠️ Hermes paused: {self.consecutive_errors} consecutive errors.\n"
            f"Resuming in {ERROR_PAUSE_SECONDS // 60} minutes."
        )
        await asyncio.sleep(ERROR_PAUSE_SECONDS)
        self.consecutive_errors = 0
        await self.set_state(DaemonState.IDLE)

    def _should_scrape_today(self, weekday: int) -> bool:
        """Scrape every day except Sunday (low value for B2B)."""
        return weekday < 6

    def _get_scraper_config(self, weekday: int) -> dict:
        """Rotate categories across days of the week."""
        # 111 categories / 7 days ≈ 16 categories per day
        category_groups = [
            ["restaurante", "lanchonete", "pizzaria", "hamburgueria", "cafeteria"],
            ["clinica", "consultorio", "farmacia", "otica", "laboratorio"],
            ["salao", "barbearia", "estetica", "spa", "academia"],
            ["loja_roupa", "calcados", "joalheria", "relojoaria", "cosmeticos"],
            ["oficina", "auto_pecas", "funilaria", "borracharia", "lava_jato"],
            ["escritorio_contabilidade", "advocacia", "imobiliaria", "arquitetura", "engenharia"],
            ["pet_shop", "veterinaria", "hotel_pet", "escola", "curso"],
        ]
        group_idx = weekday % len(category_groups)
        cities = ["Cuiaba", "Varzea Grande", "Sinop", "Rondonopolis", "Tangara da Serra"]
        city_idx = weekday % len(cities)

        return {
            "categories": category_groups[group_idx],
            "category": category_groups[group_idx][0],
            "city": cities[city_idx],
            "max_results": 50,
        }

    def _scored_today(self) -> bool:
        """Check if scoring already ran today."""
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute(
            "SELECT COUNT(*) FROM daemon_log WHERE category = 'scoring' AND date(timestamp) = date('now')"
        ).fetchone()
        conn.close()
        return row[0] > 0

    def _reported_this_week(self) -> bool:
        """Check if weekly report already generated this week."""
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute(
            "SELECT COUNT(*) FROM daemon_log WHERE category = 'reporting' AND timestamp > datetime('now', '-7 days')"
        ).fetchone()
        conn.close()
        return row[0] > 0

    async def _pipeline_needs_fuel(self) -> bool:
        """Check if pipeline is running low on prospects to process."""
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute(
            "SELECT COUNT(*) FROM prospects WHERE stage = 'discovered' AND score = 0"
        ).fetchone()
        conn.close()
        return row[0] < 50  # Less than 50 unprocessed → need more discovery

    # --- Data Fetchers ---

    async def _check_human_stop(self, prospect_id: int, channel: str) -> bool:
        """Return True if human sent STOP signal via Telegram for this prospect/channel."""
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute(
            "SELECT 1 FROM telegram_stop_signals "
            "WHERE prospect_id = ? AND channel IN (?, 'all') LIMIT 1",
            (prospect_id, channel),
        ).fetchone()
        conn.close()
        if row:
            logger.info(
                "[stop_signal] human STOP for prospect=%s channel=%s — auto_response skipped",
                prospect_id, channel,
            )
            return True
        return False

    async def _get_pending_replies(self) -> list:
        """Get unhandled replies from all channels (inbox_replies table)."""
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute(
            "SELECT id, prospect_id, channel, body, received_at "
            "FROM inbox_replies WHERE handled = 0 ORDER BY received_at ASC LIMIT 50"
        ).fetchall()
        conn.close()
        return [
            {"id": r[0], "prospect_id": r[1], "channel": r[2], "body": r[3], "received_at": r[4]}
            for r in rows
        ]

    async def _get_due_sequence_steps(self) -> list:
        """Get sequence steps due for execution — JOIN sequence_nodes for action details."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT e.id, e.prospect_id, e.sequence_id, e.current_step, "
            "n.node_type, n.channel, n.action_type, n.config_json "
            "FROM sequence_enrollments e "
            "LEFT JOIN sequence_nodes n ON CAST(e.current_step AS TEXT) = n.id "
            "WHERE e.next_action_at <= datetime('now') AND e.completed = 0 "
            "LIMIT 50"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    async def _advance_enrollment(self, enrollment_id: int, sequence_id: str,
                                  executed_node_id: str) -> None:
        """After executing a node, advance enrollment to the next node via edges.

        If no next node or next node is 'end', marks enrollment completed=1.
        Computes next_action_at respecting business hours via send_scheduler.
        """
        try:
            from core.send_scheduler import compute_delay_dt
        except ImportError:
            from datetime import timedelta
            def compute_delay_dt(days, base=None):  # type: ignore[misc]
                from datetime import datetime
                b = base or datetime.utcnow()
                return b + timedelta(days=max(days, 0))

        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        try:
            # Find next node via edges (if_true preferred over default)
            next_edge = conn.execute(
                "SELECT to_node FROM sequence_edges "
                "WHERE sequence_id=? AND from_node=? "
                "ORDER BY CASE edge_type WHEN 'if_true' THEN 0 ELSE 1 END LIMIT 1",
                (sequence_id, executed_node_id),
            ).fetchone()

            if not next_edge:
                conn.execute("UPDATE sequence_enrollments SET completed=1 WHERE id=?", (enrollment_id,))
                conn.commit()
                return

            next_node = conn.execute(
                "SELECT * FROM sequence_nodes WHERE id=?", (next_edge["to_node"],)
            ).fetchone()

            if not next_node or next_node["node_type"] in ("end", "stop"):
                conn.execute("UPDATE sequence_enrollments SET completed=1 WHERE id=?", (enrollment_id,))
                conn.commit()
                return

            # Compute delay
            delay_days = 0
            if next_node["node_type"] == "delay":
                cfg = json.loads(next_node["config_json"] or "{}")
                delay_days = int(cfg.get("delay_days", 0))

            next_at = compute_delay_dt(delay_days)
            next_at_str = next_at.strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "UPDATE sequence_enrollments SET current_step=?, next_action_at=? WHERE id=?",
                (next_node["id"], next_at_str, enrollment_id),
            )
            conn.commit()
            logger.debug("[advance_enrollment] id=%s → node=%s at %s", enrollment_id, next_node["id"], next_at_str)
            # PA-F2 ITEM 2B — real-time cobaia queue refresh after step advance
            await self._broadcast({"event_type": "cobaia.queue_updated", "reason": "advance", "enrollment_id": enrollment_id})
        finally:
            conn.close()

    async def _get_unenriched_prospects(self, limit: int = 5) -> list:
        """Get prospects missing CNPJ data via VM API (primary) ou local DB (fallback)."""
        # Primary: query VM API — funciona em container e standalone
        try:
            res = await self.pipeline._request("GET", f"/api/prospects?limit={limit * 3}&stage=discovered")
            all_p = res.get("prospects", [])
            # Filtra os sem CNPJ (API não tem filtro nativo ainda)
            unenriched = [p for p in all_p if not p.get("cnpj")][:limit]
            if unenriched or not all_p:
                return unenriched
        except Exception as exc:
            logger.debug("_get_unenriched_prospects API failed: %s", exc)

        # Fallback: DB local (útil quando rodando fora do container)
        try:
            conn = sqlite3.connect(str(DB_PATH))
            try:
                rows = conn.execute("""
                    SELECT id, business_name, name, phone, website, city, category, address
                    FROM prospects
                    WHERE cnpj IS NULL
                      AND stage IN ('discovered', 'qualified')
                    ORDER BY score DESC
                    LIMIT ?
                """, (limit,)).fetchall()
                return [dict(r) for r in rows]
            except sqlite3.OperationalError:
                # Coluna cnpj ainda não existe (pré-migração) — retorna vazio graciosamente
                return []
            finally:
                conn.close()
        except Exception as exc:
            logger.debug("_get_unenriched_prospects local DB failed: %s", exc)
            return []

    async def _get_unaudited_prospects(self, limit: int = 20) -> list:
        """Get prospects with website but no audit."""
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute("""
            SELECT id, business_name, website
            FROM prospects
            WHERE has_website = 1
            AND (audit_summary IS NULL OR audit_summary = '')
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # --- Channel Adapters ---

    async def _send_via_channel(self, channel: str, prospect_id: int,
                                template: str, context: dict) -> bool:
        """Send a message via the specified channel.

        Dry-run when HERMES_CHANNEL_SEND_ENABLED != '1' (default safe).
        LinkedIn: GatewayDispatcher → hermes-linkedin MCP send_message.
        Email/WhatsApp: 501 stub (F.future SMTP / Z-API integration).
        """
        send_enabled = os.environ.get("HERMES_CHANNEL_SEND_ENABLED", "0") == "1"
        if not send_enabled:
            logger.info("[%s] DRY-RUN prospect=%s: %s", channel, prospect_id, template[:50])
            return True

        if channel == "linkedin":
            try:
                from brain.dispatch import GatewayDispatcher
                _bearer = (
                    os.getenv("HERMES_GATEWAY_BEARER_BRAIN_CORE")
                    or os.getenv("HERMES_GATEWAY_OAUTH_SECRET", "")
                )
                dispatcher = GatewayDispatcher(bearer=_bearer)
                result = await dispatcher.invoke_tool(
                    "hermes-linkedin", "send_message",
                    {"prospect_id": prospect_id, "template": template},
                    requester="daemon",
                    caller_chapter="UX-RM-F1-B",
                )
                return bool(result.get("ok", False))
            except Exception as exc:
                logger.warning("[linkedin] send_via_channel failed: %s", exc)
                return False

        if channel == "email":
            logger.info("[email] send_via_channel 501 — SMTP integration F.future")
            return False

        if channel == "whatsapp":
            logger.info("[whatsapp] send_via_channel 501 — Z-API integration F.future")
            return False

        logger.warning("[%s] unknown channel, skipping send", channel)
        return False

    async def _enrich_single(self, prospect: dict) -> dict:
        """Enrich a single prospect via waterfall providers.

        Stage 1: CNPJ lookup via hermes-postgres trigram (H2-F2).
        Stage 2 (F.3+): website scrape.
        """
        # Stage 1: CNPJ authority (hermes-postgres)
        try:
            from scripts.enrich_cnpj import enrich_prospect_cnpj
            result = await asyncio.to_thread(enrich_prospect_cnpj, prospect)
            fields_filled = result.get("fields_filled", 0)
            if result.get("cnpj"):
                patch = {k: v for k, v in result.items()
                         if k in ("cnpj", "razao_social", "cnae",
                                  "situacao_cadastral", "cnpj_match_confidence")
                         and v is not None}
                if patch:
                    await self.pipeline._request(
                        "PATCH", f"/api/prospects/{prospect['id']}", json=patch
                    )
                logger.debug(
                    "enrich_single cnpj=%s confidence=%s fields=%d",
                    result.get("cnpj"), result.get("cnpj_match_confidence"), fields_filled,
                )
            return {"fields_filled": fields_filled, "code": 200}
        except Exception as exc:
            # hermes-postgres indisponível ou outro erro — falha graciosa, não trava daemon
            logger.info("enrich_single cnpj skip (prospect %s): %s", prospect.get("id"), exc)
            return {"fields_filled": 0, "code": 503, "reason": str(exc)}

    # --- Intelligence ---

    async def _classify_reply_intent(self, message: str, context: dict) -> str:
        """Classify reply intent using local LLM via ollama_router (MERGED-014)."""
        prompt = (
            f"Classify this reply from a B2B prospect in Brazil.\n"
            f"Original outreach was about: {context.get('outreach_topic', 'design services')}\n"
            f"Reply: \"{message}\"\n"
            f"Categories: interested, questions, not_now, not_interested, meeting_request, spam, unclear\n"
            f"Return ONLY the category name, nothing else."
        )
        try:
            raw = await ollama_router.route(
                "classify", prompt,
                options={"temperature": 0.1, "num_predict": 20},
            )
            result = raw.strip().lower()
            valid = {"interested", "questions", "not_now", "not_interested",
                     "meeting_request", "spam", "unclear"}
            return result if result in valid else "unclear"
        except OllamaUnavailable as e:
            logger.warning("Intent classification skipped (ollama unavailable): %s", e)
        except Exception as e:
            logger.exception("Intent classification failed: %s", e)
        return "unclear"

    async def _send_auto_response(self, prospect_id: int, intent: str, channel: str):
        """Send automated response based on classified intent via LLM + channel."""
        prompt = (
            f"Gere uma resposta curta e natural para um prospect B2B no Brasil.\n"
            f"Intent detectado: {intent}\n"
            f"Prospect ID: {prospect_id}. Canal: {channel}.\n"
            f"Resposta max 200 chars, tom consultivo, nunca vendedor.\n"
            f"Retorne APENAS o texto da resposta, nada mais."
        )
        try:
            response_text = await ollama_router.route(
                "generate_auto_response", prompt,
                options={"temperature": 0.7, "num_predict": 100},
            )
            response_text = response_text.strip()
            if len(response_text) >= 20:
                logger.info(
                    "[auto_response] prospect=%s intent=%s → sending via %s",
                    prospect_id, intent, channel,
                )
                await self._send_via_channel(channel, prospect_id, response_text, {"intent": intent})
            else:
                logger.info(
                    "[auto_response] low_confidence_skip prospect=%s (response too short: %d chars)",
                    prospect_id, len(response_text),
                )
        except OllamaUnavailable as exc:
            logger.warning("[auto_response] ollama unavailable: %s — skipping", exc)
        except Exception as exc:
            logger.exception("[auto_response] failed for prospect=%s: %s", prospect_id, exc)

    async def _opt_out_prospect(self, prospect_id: int):
        """Mark prospect as opted-out, remove from all sequences."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "UPDATE prospects SET stage = 'opted_out', outreach_status = 'opted_out' WHERE id = ?",
            (prospect_id,)
        )
        conn.commit()
        conn.close()

    async def _schedule_followup(
        self, prospect_id: int, days: int = 30, sequence_id: str = "default"
    ):
        """Schedule a follow-up touchpoint in N days via sequence_enrollments table."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT OR IGNORE INTO sequence_enrollments "
            "(prospect_id, sequence_id, current_step, next_action_at) "
            "VALUES (?, ?, 0, datetime('now', ? || ' days'))",
            (prospect_id, sequence_id, f"+{days}"),
        )
        conn.commit()
        conn.close()
        logger.info(
            "[followup] scheduled prospect=%s in %d days (sequence=%s)",
            prospect_id, days, sequence_id,
        )

    # --- Communication ---

    async def _broadcast(self, event: dict):
        """Broadcast event to dashboard via WebSocket (through local server)."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{LOCAL_API_URL}/api/daemon/broadcast",
                    json=event,
                    headers=self._auth_headers()
                )
        except Exception:
            pass  # noqa: silenciado intencional — dashboard offline é OK

    async def _notify_telegram(self, message: str):
        """Send notification to user via Telegram."""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            return
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(url, json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": message,
                    "parse_mode": "HTML",
                })
        except Exception as e:
            logger.warning(f"Telegram notification failed: {e}")

    def _auth_headers(self) -> dict:
        """Auth headers para VM API. Prefere HERMES_VM_AUTH_TOKEN (daemon roda no mesmo host que a API)."""
        token = os.environ.get("HERMES_VM_AUTH_TOKEN") or os.environ.get("HERMES_AUTH_TOKEN", "")
        return {"X-Hermes-Token": token} if token else {}

    # --- Public Control API ---

    async def pause(self, duration_minutes: int = 60):
        """Pause daemon for N minutes."""
        self.paused_until = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
        await self.set_state(DaemonState.PAUSED)
        await self.log_event("warning", "system", f"Daemon paused for {duration_minutes} minutes")

    async def resume(self):
        """Resume daemon from pause."""
        self.paused_until = None
        await self.set_state(DaemonState.IDLE)
        await self.log_event("info", "system", "Daemon resumed")

    def get_state_snapshot(self) -> dict:
        """Get current state for API response."""
        return {
            "state": self.state.value,
            "current_task": {
                "type": self.current_task.type,
                "category": self.current_task.category.value,
                "description": self.current_task.description,
            } if self.current_task else None,
            "energy": round(self.energy, 2),
            "stats_today": self.stats_today.__dict__,
            "stats_week": self.stats_week.__dict__,
            "channels": {
                name: {
                    "daily_used": ch.daily_used,
                    "daily_limit": ch.daily_limit,
                    "health": ch.health,
                    "warmup_day": ch.warmup_day,
                    "warmup_complete": ch.warmup_complete,
                    "can_send": ch.can_send,
                    "usage_ratio": round(ch.usage_ratio, 2),
                    "is_active": ch.is_active,
                }
                for name, ch in self.channels.items()
            },
            "consecutive_errors": self.consecutive_errors,
            "uptime_hours": round((datetime.now(timezone.utc) - self.started_at).total_seconds() / 3600, 1),
            "recent_decisions": self.decision_log[-10:],
        }


# --- Entry Point ---

async def main():
    """Start the Hermes Daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("daemon.log", encoding="utf-8"),
        ]
    )

    # Garante as tabelas do core.state (runtime_state etc) no DB do daemon.
    # No PC isso era feito pelo server.py; no container/VM o daemon roda sem ele.
    try:
        import core.state as _cs
        _cs.init_db()
    except Exception:
        logger.exception("core.state.init_db() no boot do daemon falhou")

    daemon = HermesDaemon()

    try:
        await daemon.run_forever()
    except KeyboardInterrupt:
        await daemon.stop()


if __name__ == "__main__":
    asyncio.run(main())
