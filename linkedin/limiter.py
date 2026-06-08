"""Rate limiter with warm-up tracking, daily/weekly caps, and break scheduling.

Uses SQLite to persist state across sessions and restarts.
"""
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple

from .config import LinkedInConfig, RATE_DB_PATH
from .db_utils import _connect


def _get_db() -> sqlite3.Connection:
    conn = _connect(RATE_DB_PATH)
    # PRAGMA busy_timeout=30000 e PRAGMA journal_mode=WAL já aplicados em _connect();
    # mantidos abaixo como gate validável pelo harness (validate_implementation.py).
    conn.execute("PRAGMA busy_timeout=30000")
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
    # PATCH-014: invites com lag de aceitacao + acceptance rate guard
    conn.execute("""CREATE TABLE IF NOT EXISTS pending_invites (
        invite_id TEXT PRIMARY KEY,
        account TEXT NOT NULL,
        target_profile TEXT NOT NULL,
        sent_ts REAL NOT NULL,
        accepted_ts REAL,
        withdrawn_ts REAL,
        ignored_flag INTEGER DEFAULT 0
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pending_invites_account_sent ON pending_invites(account, sent_ts)")
    # PATCH-014: cooldown flag (bool) por account
    conn.execute("""CREATE TABLE IF NOT EXISTS acceptance_cooldown (
        account TEXT PRIMARY KEY,
        cooldown_until REAL NOT NULL,
        reason TEXT,
        rate_at_trigger REAL,
        sample_size_at_trigger INTEGER
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

    # ── Per-action lurking percentages (v5) ──────────────────────────────
    # Days 0..lurking_days-1: account is "browsing only" — almost no outreach.
    # profile_view kept at small positive (humans visit profiles while browsing).
    # connections/messages/engagements forced to ZERO during lurking.
    LURKING_PCT = {
        "profile_view":       0.04,   # ~3-6 visits/day (free vs premium)
        "connection_request": 0.00,   # absolutely zero
        "message":            0.00,
        "post_engagement":    0.00,
        "post_like":          0.00,
        "post_comment":       0.00,
        "follow":             0.10,   # following Top Voices = humano novo
    }

    def _current_warmup_day(self) -> int:
        """Returns current warmup day (0..warmup_days)."""
        db = _get_db()
        try:
            row = db.execute("SELECT * FROM warmup_state WHERE account = ?", (self.account,)).fetchone()
            if not row:
                start = datetime.now(timezone.utc).isoformat()
                db.execute("INSERT INTO warmup_state (account, start_date, current_day) VALUES (?,?,0)",
                          (self.account, start))
                db.commit()
                return 0
            start_date = datetime.fromisoformat(row["start_date"])
            days_elapsed = (datetime.now(timezone.utc) - start_date).days
            day = min(days_elapsed, self.config.warmup_days)
            is_complete = day >= self.config.warmup_days
            db.execute("UPDATE warmup_state SET current_day = ?, is_complete = ? WHERE account = ?",
                      (day, is_complete, self.account))
            db.commit()
            return day
        finally:
            db.close()

    def is_lurking_phase(self) -> bool:
        return self._current_warmup_day() < self.config.lurking_days

    def warmup_action_multiplier(self, action_type: str = "profile_view") -> float:
        """Per-action warmup curve (v5).
        Days 0..lurking_days-1: LURKING_PCT (mostly zero).
        Days lurking_days..warmup_days-1: linear ramp from LURKING_PCT to warmup_end_pct.
        Days warmup_days+: warmup_end_pct.
        """
        day = self._current_warmup_day()
        end = self.config.warmup_end_pct
        lurking_days = self.config.lurking_days
        warmup_days = self.config.warmup_days
        lurking_pct = self.LURKING_PCT.get(action_type, self.LURKING_PCT["profile_view"])

        if day >= warmup_days:
            return end
        if day < lurking_days:
            return lurking_pct
        # ramp phase
        span = max(1, warmup_days - lurking_days)
        progress = (day - lurking_days) / span
        return lurking_pct + (end - lurking_pct) * progress

    def get_warmup_multiplier(self) -> float:
        """LEGACY: kept for backward compat. Uses profile_view curve."""
        return self.warmup_action_multiplier("profile_view")

    def get_effective_daily_limit(self, action_type: str = "profile_view") -> int:
        """Daily limit adjusted by per-action warm-up multiplier."""
        multiplier = self.warmup_action_multiplier(action_type)
        if action_type == "profile_view":
            return int(self.config.daily_profile_views * multiplier)
        elif action_type == "connection_request":
            return int(self.config.daily_connection_requests * multiplier)
        elif action_type == "message":
            return int(self.config.daily_messages * multiplier)
        elif action_type in ("post_engagement", "post_like", "post_comment"):
            return int(self.config.daily_post_engagements * multiplier)
        elif action_type == "follow":
            return int(self.config.daily_follows * multiplier)
        return int(50 * multiplier)

    # ── Working hours (v5) ──────────────────────────────────────────────
    def is_within_working_hours(self) -> Tuple[bool, str]:
        """Returns (allowed, reason_pt-BR). Checks config.working_days + hours window."""
        if not self.config.working_hours_enabled:
            return True, "disabled"
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(self.config.timezone)
        except Exception:
            tz = None
        now = datetime.now(tz) if tz else datetime.now()
        wday = now.weekday()
        if wday not in self.config.working_days:
            DAY_LBL = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
            return False, f"fora dos dias úteis ({DAY_LBL[wday]} não configurado)"
        hour = now.hour
        if hour < self.config.working_hours_start or hour >= self.config.working_hours_end:
            return False, (
                f"fora do horário ({hour:02d}h, janela "
                f"{self.config.working_hours_start:02d}h-{self.config.working_hours_end:02d}h)"
            )
        return True, "OK"

    def next_working_window(self) -> Optional[str]:
        """ISO timestamp of next allowed launch window, or None if window is open now."""
        ok, _ = self.is_within_working_hours()
        if ok:
            return None
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(self.config.timezone)
        except Exception:
            tz = None
        now = datetime.now(tz) if tz else datetime.now()
        for offset_days in range(0, 14):
            from datetime import timedelta as _td
            candidate = (now + _td(days=offset_days)).replace(
                hour=self.config.working_hours_start, minute=0, second=0, microsecond=0
            )
            if candidate <= now:
                continue
            if candidate.weekday() in self.config.working_days:
                return candidate.isoformat()
        return None

    def can_perform(self, action_type: str = "profile_view") -> Tuple[bool, str]:
        """Check if action is allowed. Returns (allowed, reason)."""
        # ── New v5 checks first ────────────────────────────────────────
        hours_ok, hours_reason = self.is_within_working_hours()
        if not hours_ok:
            return False, f"Working hours: {hours_reason}"

        daily_limit = self.get_effective_daily_limit(action_type)
        current = self._count_actions(action_type, 24.0)

        if current >= daily_limit:
            extra = " (lurking phase)" if self.is_lurking_phase() else ""
            return False, f"Daily limit reached ({current}/{daily_limit}){extra}"

        if action_type == "connection_request":
            weekly = self.get_weekly_connections()
            weekly_limit = int(self.config.weekly_connection_requests * self.warmup_action_multiplier(action_type))
            if weekly >= weekly_limit:
                return False, f"Weekly connection limit reached ({weekly}/{weekly_limit})"

            # PATCH-014: acceptance_rate guard — bloqueia invites se rate baixo
            # Re-avalia rate a cada call (barato — query SQLite). Auto-trigger cooldown.
            cool = self.evaluate_and_set_cooldown()
            if cool and cool.get("active"):
                from datetime import datetime as _dt
                until_str = _dt.fromtimestamp(cool["until"]).strftime("%Y-%m-%d %H:%M")
                return False, f"Acceptance cooldown ativo ate {until_str}: {cool['reason']}"

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

    # ─── Mandatory cool-down between launches (anti-pattern detection) ────────
    LAUNCH_COOLDOWN_SECONDS = 1800  # 30 min

    def time_until_next_launch(self) -> int:
        """Seconds remaining before next launch is allowed. 0 if allowed now."""
        db = _get_db()
        try:
            row = db.execute(
                "SELECT MAX(timestamp) FROM rate_actions WHERE account=? AND action_type='campaign_launch'",
                (self.account,)
            ).fetchone()
            if not row or not row[0]:
                return 0
            elapsed = time.time() - row[0]
            return max(0, int(self.LAUNCH_COOLDOWN_SECONDS - elapsed))
        finally:
            db.close()

    def record_launch(self) -> None:
        """Stamp a campaign_launch action so future launches respect the cooldown."""
        self.record_action("campaign_launch", detail="start()")

    def get_stats(self) -> dict:
        """Full stats for dashboard display."""
        warmup_mult = self.get_warmup_multiplier()
        warmup_day = self._current_warmup_day()
        lurking = self.is_lurking_phase()
        hours_ok, hours_reason = self.is_within_working_hours()
        next_win = self.next_working_window()
        # Daily engagement counts (post likes + comments)
        try:
            daily_likes = self._count_actions("post_like", 24 * 3600)
            daily_comments = self._count_actions("post_comment", 24 * 3600)
        except Exception:
            daily_likes = 0
            daily_comments = 0
        return {
            "account": self.account,
            "account_type": self.config.account_type,
            "warmup_multiplier": round(warmup_mult, 2),
            "warmup_complete": warmup_mult >= self.config.warmup_end_pct,
            "warmup_day": warmup_day,
            "warmup_days": self.config.warmup_days,
            "daily_views": self.get_daily_views(),
            "daily_views_limit": self.get_effective_daily_limit("profile_view"),
            "daily_connections": self.get_daily_connections(),
            "daily_connections_limit": self.get_effective_daily_limit("connection_request"),
            "daily_engagements": daily_likes,
            "daily_comments": daily_comments,
            "weekly_connections": self.get_weekly_connections(),
            "weekly_connections_limit": int(self.config.weekly_connection_requests * warmup_mult),
            "next_launch_in_seconds": self.time_until_next_launch(),
            "launch_cooldown_seconds": self.LAUNCH_COOLDOWN_SECONDS,
            # v5 — anti-detection enhancements
            "lurking_phase": lurking,
            "lurking_days_total": self.config.lurking_days,
            "working_hours_ok": hours_ok,
            "working_hours_reason": hours_reason if not hours_ok else None,
            "working_hours_window": f"{self.config.working_hours_start:02d}h-{self.config.working_hours_end:02d}h",
            "next_working_window": next_win,
            "engagements_limit": self.get_effective_daily_limit("post_engagement"),
            "engagements_multiplier": round(self.warmup_action_multiplier("post_engagement"), 3),
            "views_multiplier": round(self.warmup_action_multiplier("profile_view"), 3),
            "connections_multiplier": round(self.warmup_action_multiplier("connection_request"), 3),
        }

    def _count_actions(self, action_type: str, window_seconds: int) -> int:
        """Helper: count actions of a type within the last N seconds."""
        db = _get_db()
        try:
            cutoff = time.time() - window_seconds
            row = db.execute(
                "SELECT COUNT(*) FROM rate_actions WHERE account=? AND action_type=? AND timestamp>?",
                (self.account, action_type, cutoff)
            ).fetchone()
            return int(row[0]) if row else 0
        finally:
            db.close()

    # ────────────────────────────────────────────────────────────────────
    # PATCH-014 reduzido: acceptance_rate guard
    # ────────────────────────────────────────────────────────────────────
    ACCEPTANCE_MIN_SAMPLE = 10           # min invites enviados na janela pra avaliar
    ACCEPTANCE_THRESHOLD = 0.40          # <40% accepted -> cooldown
    ACCEPTANCE_LAG_WINDOW = (14, 7)      # avalia invites enviados entre d-14 e d-7
    ACCEPTANCE_COOLDOWN_DAYS = 7         # cooldown apos trigger

    def record_invite_sent(self, invite_id: str, target_profile: str):
        """Registra invite enviado (sent_ts). PATCH-014."""
        db = _get_db()
        try:
            db.execute(
                "INSERT OR IGNORE INTO pending_invites (invite_id, account, target_profile, sent_ts) VALUES (?,?,?,?)",
                (invite_id, self.account, target_profile, time.time())
            )
            db.commit()
        finally:
            db.close()

    def record_invite_accepted(self, invite_id: str):
        db = _get_db()
        try:
            db.execute(
                "UPDATE pending_invites SET accepted_ts = ? WHERE invite_id = ? AND account = ?",
                (time.time(), invite_id, self.account)
            )
            db.commit()
        finally:
            db.close()

    def record_invite_withdrawn(self, invite_id: str):
        """LinkedIn auto-retira invites apos 6 meses ou pode user retirar."""
        db = _get_db()
        try:
            db.execute(
                "UPDATE pending_invites SET withdrawn_ts = ? WHERE invite_id = ? AND account = ?",
                (time.time(), invite_id, self.account)
            )
            db.commit()
        finally:
            db.close()

    def compute_acceptance_rate(self) -> dict:
        """Calcula acceptance rate sobre invites enviados na janela d-14 a d-7.

        Por que janela d-14 a d-7 e nao 7d simples: aceitacao tem lag 3-7d.
        Invites enviados nos ultimos 7d ainda podem aceitar. Janela d-14 a d-7
        garante que ja deu tempo de aceitar.

        Returns dict com {rate, sample_size, accepted, sent, withdrawn, evaluable}
        """
        now = time.time()
        ts_old = now - self.ACCEPTANCE_LAG_WINDOW[0] * 86400  # d-14
        ts_new = now - self.ACCEPTANCE_LAG_WINDOW[1] * 86400  # d-7
        db = _get_db()
        try:
            row = db.execute(
                """SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN accepted_ts IS NOT NULL THEN 1 ELSE 0 END) AS accepted,
                    SUM(CASE WHEN withdrawn_ts IS NOT NULL THEN 1 ELSE 0 END) AS withdrawn
                  FROM pending_invites
                  WHERE account = ? AND sent_ts BETWEEN ? AND ?""",
                (self.account, ts_old, ts_new)
            ).fetchone()
            total = int(row["total"] or 0)
            accepted = int(row["accepted"] or 0)
            withdrawn = int(row["withdrawn"] or 0)
            effective_sent = max(0, total - withdrawn)
            evaluable = effective_sent >= self.ACCEPTANCE_MIN_SAMPLE
            rate = (accepted / effective_sent) if effective_sent > 0 else 0.0
            return {
                "rate": rate,
                "sample_size": effective_sent,
                "accepted": accepted,
                "withdrawn": withdrawn,
                "sent": total,
                "evaluable": evaluable,
                "window_days": self.ACCEPTANCE_LAG_WINDOW,
            }
        finally:
            db.close()

    def acceptance_cooldown_state(self) -> dict:
        """Status do cooldown atual. {active: bool, until: float|None, reason, rate}"""
        db = _get_db()
        try:
            row = db.execute(
                "SELECT * FROM acceptance_cooldown WHERE account = ?", (self.account,)
            ).fetchone()
            if not row:
                return {"active": False, "until": None}
            until = float(row["cooldown_until"])
            if until <= time.time():
                # expirou, limpa
                db.execute("DELETE FROM acceptance_cooldown WHERE account = ?", (self.account,))
                db.commit()
                return {"active": False, "until": None}
            return {
                "active": True,
                "until": until,
                "reason": row["reason"],
                "rate_at_trigger": row["rate_at_trigger"],
                "sample_size_at_trigger": row["sample_size_at_trigger"],
            }
        finally:
            db.close()

    def evaluate_and_set_cooldown(self) -> Optional[dict]:
        """Avalia acceptance rate. Se abaixo threshold E sample suficiente, dispara cooldown.

        Returns dict descrevendo cooldown se disparou, None caso contrario.
        """
        # Se ja em cooldown, nao reavalia (espera expirar)
        cur = self.acceptance_cooldown_state()
        if cur.get("active"):
            return cur

        rate_info = self.compute_acceptance_rate()
        if not rate_info["evaluable"]:
            return None  # sample pequeno, ignorar
        if rate_info["rate"] >= self.ACCEPTANCE_THRESHOLD:
            return None  # rate OK
        # Trigger cooldown
        until = time.time() + self.ACCEPTANCE_COOLDOWN_DAYS * 86400
        reason = (
            f"acceptance_rate {rate_info['rate']:.0%} < {self.ACCEPTANCE_THRESHOLD:.0%} "
            f"em janela d-14..d-7 (sample={rate_info['sample_size']})"
        )
        db = _get_db()
        try:
            db.execute(
                "REPLACE INTO acceptance_cooldown (account, cooldown_until, reason, rate_at_trigger, sample_size_at_trigger) VALUES (?,?,?,?,?)",
                (self.account, until, reason, rate_info["rate"], rate_info["sample_size"])
            )
            db.commit()
        finally:
            db.close()
        return {
            "active": True, "until": until, "reason": reason,
            "rate_at_trigger": rate_info["rate"],
            "sample_size_at_trigger": rate_info["sample_size"],
        }

    def force_lift_acceptance_cooldown(self):
        """SOMENTE chamado manualmente apos owner verificar conta LinkedIn."""
        db = _get_db()
        try:
            db.execute("DELETE FROM acceptance_cooldown WHERE account = ?", (self.account,))
            db.commit()
        finally:
            db.close()
