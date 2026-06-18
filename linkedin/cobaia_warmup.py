"""F.7 C1 — Cobaia warmup state machine.

Manages the 14-day warmup lifecycle for the cobaia LinkedIn account:
  - Phase: lurking (d0-6) → ramp (d7-13) → normal (d14+)
  - Caps per phase (views/connects/engagements)
  - Working hours gate: 07h-22h Cuiaba, weekdays only (D2.2/D2.3)
  - Auto-pause after N consecutive errors (D4)
  - Persistence: cobaia_warmup_state + cobaia_daily_metrics tables

All LinkedIn calls are STUBBED (MOCK-DRIVEN) — real execution wired in C6.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore[assignment]

from .config import CobaiaConfig

# DB path matches hermes_local.db (PC) or command_center.db (VM) per runtime
_DEFAULT_DB = Path(__file__).parent.parent / "hermes_local.db"


def _get_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or _DEFAULT_DB
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


# --- Phase helpers ---

def _compute_phase(current_day: int, cfg: CobaiaConfig) -> str:
    if current_day < cfg.lurking_days:
        return "lurking"
    if current_day < cfg.warmup_days:
        return "ramp"
    return "normal"


def _compute_caps(phase: str, current_day: int, cfg: CobaiaConfig) -> Dict[str, int]:
    """Daily action caps per phase.

    lurking: views=5, connects=0, engagements=3 (engagement skill only)
    ramp:    linear scale from lurking→normal over cfg.warmup_days - cfg.lurking_days
    normal:  views=70, connects=10, engagements=15 (free tier safe limits)
    """
    if phase == "lurking":
        return {"views": 5, "connects": 0, "engagements": 3}
    if phase == "normal":
        return {"views": 70, "connects": 10, "engagements": 15}
    # ramp: linear interpolation
    span = max(1, cfg.warmup_days - cfg.lurking_days)
    progress = (current_day - cfg.lurking_days) / span
    return {
        "views": int(5 + (70 - 5) * progress),
        "connects": int(0 + (10 - 0) * progress),
        "engagements": int(3 + (15 - 3) * progress),
    }


def _is_within_working_hours(cfg: CobaiaConfig) -> Tuple[bool, str]:
    """Returns (allowed, reason). 07h-22h Cuiaba, weekdays only."""
    tz = ZoneInfo(cfg.timezone) if ZoneInfo else None
    now = datetime.now(tz) if tz else datetime.now()
    if not cfg.weekends_enabled and now.weekday() >= 5:
        return False, f"fim_de_semana weekday={now.weekday()}"
    start_h, start_m = map(int, cfg.working_hours_start.split(":"))
    end_h, end_m = map(int, cfg.working_hours_end.split(":"))
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m
    current_minutes = now.hour * 60 + now.minute
    if current_minutes < start_minutes or current_minutes >= end_minutes:
        return False, f"fora_horario hour={now.hour}:{now.minute:02d}"
    return True, "ok"


class CobaiaWarmupManager:
    """Manages cobaia warmup state in SQLite.

    All LinkedIn execution calls are stubbed — returns mock success data.
    Real execution is wired in F.7 C6 after warmup completes.
    """

    def __init__(self, cfg: Optional[CobaiaConfig] = None, db_path: Optional[Path] = None):
        self.cfg = cfg or CobaiaConfig()
        self.db_path = db_path

    def _db(self) -> sqlite3.Connection:
        return _get_db(self.db_path)

    def _ensure_tables(self):
        conn = self._db()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS cobaia_warmup_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_handle TEXT NOT NULL UNIQUE,
                    started_at TEXT NOT NULL,
                    current_day INTEGER NOT NULL DEFAULT 0,
                    phase TEXT NOT NULL DEFAULT 'lurking',
                    paused_at TEXT,
                    pause_reason TEXT,
                    last_check_at TEXT,
                    consecutive_errors INTEGER NOT NULL DEFAULT 0,
                    config_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS cobaia_daily_metrics (
                    date TEXT NOT NULL,
                    account_handle TEXT NOT NULL,
                    views_count INTEGER DEFAULT 0,
                    connects_sent INTEGER DEFAULT 0,
                    connects_accepted INTEGER DEFAULT 0,
                    replies_received INTEGER DEFAULT 0,
                    engagements_count INTEGER DEFAULT 0,
                    errors_count INTEGER DEFAULT 0,
                    PRIMARY KEY (date, account_handle)
                );
                CREATE INDEX IF NOT EXISTS idx_cobaia_daily_metrics_account
                    ON cobaia_daily_metrics(account_handle, date DESC);
            """)
            conn.commit()
        finally:
            conn.close()

    def start_warmup(self, account_handle: Optional[str] = None) -> Dict[str, Any]:
        """Insert new warmup state. Raises ValueError if already exists."""
        self._ensure_tables()
        handle = account_handle or self.cfg.account_handle
        now = datetime.now(timezone.utc).isoformat()
        config_json = json.dumps({
            "working_hours_start": self.cfg.working_hours_start,
            "working_hours_end": self.cfg.working_hours_end,
            "weekends_enabled": self.cfg.weekends_enabled,
            "warmup_days": self.cfg.warmup_days,
            "lurking_days": self.cfg.lurking_days,
            "auto_pause_consecutive_errors": self.cfg.auto_pause_consecutive_errors,
        })
        conn = self._db()
        try:
            existing = conn.execute(
                "SELECT id FROM cobaia_warmup_state WHERE account_handle = ?",
                (handle,)
            ).fetchone()
            if existing:
                raise ValueError(f"warmup_already_exists account_handle={handle}")
            conn.execute(
                """INSERT INTO cobaia_warmup_state
                   (account_handle, started_at, current_day, phase, config_json)
                   VALUES (?, ?, 0, 'lurking', ?)""",
                (handle, now, config_json)
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_status(handle)

    def pause(self, account_handle: Optional[str] = None, reason: str = "") -> Dict[str, Any]:
        self._ensure_tables()
        handle = account_handle or self.cfg.account_handle
        now = datetime.now(timezone.utc).isoformat()
        conn = self._db()
        try:
            conn.execute(
                """UPDATE cobaia_warmup_state
                   SET phase = 'paused', paused_at = ?, pause_reason = ?
                   WHERE account_handle = ?""",
                (now, reason or "manual_pause", handle)
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_status(handle)

    def resume(self, account_handle: Optional[str] = None) -> Dict[str, Any]:
        self._ensure_tables()
        handle = account_handle or self.cfg.account_handle
        conn = self._db()
        try:
            row = conn.execute(
                "SELECT current_day FROM cobaia_warmup_state WHERE account_handle = ?",
                (handle,)
            ).fetchone()
            if not row:
                raise ValueError(f"no_warmup_state account_handle={handle}")
            phase = _compute_phase(row["current_day"], self.cfg)
            conn.execute(
                """UPDATE cobaia_warmup_state
                   SET phase = ?, paused_at = NULL, pause_reason = NULL
                   WHERE account_handle = ?""",
                (phase, handle)
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_status(handle)

    def get_status(self, account_handle: Optional[str] = None) -> Dict[str, Any]:
        self._ensure_tables()
        handle = account_handle or self.cfg.account_handle
        conn = self._db()
        try:
            row = conn.execute(
                "SELECT * FROM cobaia_warmup_state WHERE account_handle = ?",
                (handle,)
            ).fetchone()
            if not row:
                return {"exists": False, "account_handle": handle}
            today = date.today().isoformat()
            metrics_row = conn.execute(
                "SELECT * FROM cobaia_daily_metrics WHERE date = ? AND account_handle = ?",
                (today, handle)
            ).fetchone()
            caps = _compute_caps(row["phase"], row["current_day"], self.cfg)
            today_metrics = dict(metrics_row) if metrics_row else {
                "views_count": 0, "connects_sent": 0, "connects_accepted": 0,
                "replies_received": 0, "engagements_count": 0, "errors_count": 0,
            }
            within_hours, hours_reason = _is_within_working_hours(self.cfg)
            return {
                "exists": True,
                "account_handle": handle,
                "started_at": row["started_at"],
                "current_day": row["current_day"],
                "phase": row["phase"],
                "paused_at": row["paused_at"],
                "pause_reason": row["pause_reason"],
                "last_check_at": row["last_check_at"],
                "consecutive_errors": row["consecutive_errors"],
                "caps_today": caps,
                "today_metrics": today_metrics,
                "within_working_hours": within_hours,
                "hours_reason": hours_reason,
            }
        finally:
            conn.close()

    def daily_check(self, account_handle: Optional[str] = None) -> Dict[str, Any]:
        """Idempotent daily advance: increment current_day, compute phase, check auto-pause.

        All LinkedIn execution is STUBBED — returns mock success.
        Returns dict with phase, caps, action taken.
        """
        self._ensure_tables()
        handle = account_handle or self.cfg.account_handle
        conn = self._db()
        try:
            row = conn.execute(
                "SELECT * FROM cobaia_warmup_state WHERE account_handle = ?",
                (handle,)
            ).fetchone()
            if not row:
                return {"skipped": True, "reason": "no_state"}
            if row["phase"] == "paused":
                return {"skipped": True, "reason": "paused"}
            today = date.today().isoformat()
            # idempotent: if last_check_at is today, skip increment
            last_check = row["last_check_at"]
            if last_check and last_check[:10] == today:
                return {
                    "skipped": True,
                    "reason": "already_checked_today",
                    "phase": row["phase"],
                    "current_day": row["current_day"],
                }
            # weekend gate
            if not self.cfg.weekends_enabled:
                from datetime import date as _date
                wd = _date.today().weekday()
                if wd >= 5:
                    return {"skipped": True, "reason": f"weekend weekday={wd}"}
            # increment day
            new_day = row["current_day"] + 1
            new_phase = _compute_phase(new_day, self.cfg)
            # check auto-pause
            errors = row["consecutive_errors"]
            if errors >= self.cfg.auto_pause_consecutive_errors:
                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    """UPDATE cobaia_warmup_state
                       SET phase = 'paused', paused_at = ?, pause_reason = 'auto_pause_errors',
                           current_day = ?, last_check_at = ?
                       WHERE account_handle = ?""",
                    (now, new_day, today, handle)
                )
                conn.commit()
                return {
                    "skipped": False,
                    "auto_paused": True,
                    "reason": f"consecutive_errors={errors}",
                    "phase": "paused",
                    "current_day": new_day,
                }
            conn.execute(
                """UPDATE cobaia_warmup_state
                   SET current_day = ?, phase = ?, last_check_at = ?
                   WHERE account_handle = ?""",
                (new_day, new_phase, today, handle)
            )
            conn.commit()
        finally:
            conn.close()
        caps = _compute_caps(new_phase, new_day, self.cfg)
        return {
            "skipped": False,
            "phase": new_phase,
            "current_day": new_day,
            "caps": caps,
        }

    def record_error(self, account_handle: Optional[str] = None) -> int:
        """Increment consecutive_errors counter. Returns new count."""
        self._ensure_tables()
        handle = account_handle or self.cfg.account_handle
        conn = self._db()
        try:
            conn.execute(
                """UPDATE cobaia_warmup_state
                   SET consecutive_errors = consecutive_errors + 1
                   WHERE account_handle = ?""",
                (handle,)
            )
            conn.commit()
            row = conn.execute(
                "SELECT consecutive_errors FROM cobaia_warmup_state WHERE account_handle = ?",
                (handle,)
            ).fetchone()
            return row["consecutive_errors"] if row else 0
        finally:
            conn.close()

    def reset_errors(self, account_handle: Optional[str] = None):
        """Reset consecutive_errors to 0 on success."""
        self._ensure_tables()
        handle = account_handle or self.cfg.account_handle
        conn = self._db()
        try:
            conn.execute(
                "UPDATE cobaia_warmup_state SET consecutive_errors = 0 WHERE account_handle = ?",
                (handle,)
            )
            conn.commit()
        finally:
            conn.close()


