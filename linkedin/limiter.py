"""Rate limiter with warm-up tracking, daily/weekly caps, and break scheduling.

Uses SQLite to persist state across sessions and restarts.
"""
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple

from .config import LinkedInConfig, RATE_DB_PATH


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(RATE_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS rate_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account TEXT NOT NULL,
        action_type TEXT NOT NULL,
        timestamp REAL NOT NULL,
        detail TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS warmup_state (
        account TEXT PRIMARY KEY,
        start_date TEXT NOT NULL,
        current_day INTEGER DEFAULT 0,
        is_complete BOOLEAN DEFAULT 0
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS session_state (
        account TEXT PRIMARY KEY,
        session_start REAL,
        total_actions_session INTEGER DEFAULT 0,
        last_break REAL,
        last_action REAL
    )""")
    conn.commit()
    return conn


class RateLimiter:
    def __init__(self, config: LinkedInConfig):
        self.config = config
        self.account = config.account_email or "default"
        self._init_session()

    def _init_session(self):
        db = _get_db()
        try:
            row = db.execute("SELECT * FROM session_state WHERE account = ?", (self.account,)).fetchone()
            if not row:
                now = time.time()
                db.execute(
                    "INSERT INTO session_state (account, session_start, total_actions_session, last_break, last_action) VALUES (?,?,0,?,?)",
                    (self.account, now, now, now)
                )
                db.commit()
        finally:
            db.close()

    def _count_actions(self, action_type: str, since_hours: float) -> int:
        db = _get_db()
        try:
            cutoff = time.time() - (since_hours * 3600)
            row = db.execute(
                "SELECT COUNT(*) as cnt FROM rate_actions WHERE account = ? AND action_type = ? AND timestamp > ?",
                (self.account, action_type, cutoff)
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            db.close()

    def get_daily_views(self) -> int:
        return self._count_actions("profile_view", 24.0)

    def get_daily_connections(self) -> int:
        return self._count_actions("connection_request", 24.0)

    def get_weekly_connections(self) -> int:
        return self._count_actions("connection_request", 168.0)

    def get_daily_messages(self) -> int:
        return self._count_actions("message", 24.0)

    def get_warmup_multiplier(self) -> float:
        """Returns 0.0-1.0 multiplier based on warm-up progress."""
        db = _get_db()
        try:
            row = db.execute("SELECT * FROM warmup_state WHERE account = ?", (self.account,)).fetchone()
            if not row:
                start = datetime.now(timezone.utc).isoformat()
                db.execute("INSERT INTO warmup_state (account, start_date, current_day) VALUES (?,?,0)",
                          (self.account, start))
                db.commit()
                return self.config.warmup_start_pct

            if row["is_complete"]:
                return self.config.warmup_end_pct

            start_date = datetime.fromisoformat(row["start_date"])
            days_elapsed = (datetime.now(timezone.utc) - start_date).days
            day = min(days_elapsed, self.config.warmup_days)

            db.execute("UPDATE warmup_state SET current_day = ?, is_complete = ? WHERE account = ?",
                      (day, day >= self.config.warmup_days, self.account))
            db.commit()

            progress = day / self.config.warmup_days
            return self.config.warmup_start_pct + (self.config.warmup_end_pct - self.config.warmup_start_pct) * progress
        finally:
            db.close()

    def get_effective_daily_limit(self, action_type: str = "profile_view") -> int:
        """Daily limit adjusted by warm-up multiplier."""
        multiplier = self.get_warmup_multiplier()
        if action_type == "profile_view":
            return int(self.config.daily_profile_views * multiplier)
        elif action_type == "connection_request":
            return int(self.config.daily_connection_requests * multiplier)
        elif action_type == "message":
            return int(self.config.daily_messages * multiplier)
        return int(50 * multiplier)

    def can_perform(self, action_type: str = "profile_view") -> Tuple[bool, str]:
        """Check if action is allowed. Returns (allowed, reason)."""
        daily_limit = self.get_effective_daily_limit(action_type)
        current = self._count_actions(action_type, 24.0)

        if current >= daily_limit:
            return False, f"Daily limit reached ({current}/{daily_limit})"

        if action_type == "connection_request":
            weekly = self.get_weekly_connections()
            weekly_limit = int(self.config.weekly_connection_requests * self.get_warmup_multiplier())
            if weekly >= weekly_limit:
                return False, f"Weekly connection limit reached ({weekly}/{weekly_limit})"

        db = _get_db()
        try:
            row = db.execute("SELECT * FROM session_state WHERE account = ?", (self.account,)).fetchone()
            if row:
                session_hours = (time.time() - row["session_start"]) / 3600
                if session_hours >= self.config.session_max_hours:
                    return False, f"Session max duration reached ({session_hours:.1f}h)"
        finally:
            db.close()

        return True, "OK"

    def needs_break(self) -> Tuple[bool, float]:
        """Check if we need a break. Returns (needs_break, break_duration_seconds)."""
        db = _get_db()
        try:
            row = db.execute("SELECT * FROM session_state WHERE account = ?", (self.account,)).fetchone()
            if not row:
                return False, 0

            actions_since_break = row["total_actions_session"]
            if actions_since_break >= self.config.break_after_actions:
                import random
                duration = random.uniform(self.config.break_duration_min, self.config.break_duration_max)
                return True, duration
        finally:
            db.close()
        return False, 0

    def record_action(self, action_type: str, detail: str = ""):
        """Record an action for rate limiting."""
        now = time.time()
        db = _get_db()
        try:
            db.execute(
                "INSERT INTO rate_actions (account, action_type, timestamp, detail) VALUES (?,?,?,?)",
                (self.account, action_type, now, detail)
            )
            db.execute(
                "UPDATE session_state SET total_actions_session = total_actions_session + 1, last_action = ? WHERE account = ?",
                (now, self.account)
            )
            db.commit()
        finally:
            db.close()

    def record_break(self):
        """Record that a break was taken, reset action counter."""
        db = _get_db()
        try:
            db.execute(
                "UPDATE session_state SET total_actions_session = 0, last_break = ? WHERE account = ?",
                (time.time(), self.account)
            )
            db.commit()
        finally:
            db.close()

    def reset_session(self):
        """Start a new session."""
        now = time.time()
        db = _get_db()
        try:
            db.execute(
                "REPLACE INTO session_state (account, session_start, total_actions_session, last_break, last_action) VALUES (?,?,0,?,?)",
                (self.account, now, now, now)
            )
            db.commit()
        finally:
            db.close()

    def get_stats(self) -> dict:
        """Full stats for dashboard display."""
        warmup_mult = self.get_warmup_multiplier()
        return {
            "account": self.account,
            "account_type": self.config.account_type,
            "warmup_multiplier": round(warmup_mult, 2),
            "warmup_complete": warmup_mult >= self.config.warmup_end_pct,
            "daily_views": self.get_daily_views(),
            "daily_views_limit": self.get_effective_daily_limit("profile_view"),
            "daily_connections": self.get_daily_connections(),
            "daily_connections_limit": self.get_effective_daily_limit("connection_request"),
            "weekly_connections": self.get_weekly_connections(),
            "weekly_connections_limit": int(self.config.weekly_connection_requests * warmup_mult),
        }
