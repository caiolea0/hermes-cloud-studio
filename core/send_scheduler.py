"""UX-RM-F6-C — Send Scheduler with business hours + weekend skip + jitter.

Business hours: America/Cuiaba BRT, Mon-Fri 09:00-19:00.
Jitter: random offset [0, max_minutes] — anti-pattern detection (human-like
send spread), NOT fake data. Listed in .claude/MCP-BANNED-PATTERNS.json
_exceptions like spintax.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, time as dtime
from typing import Optional

try:
    import zoneinfo
    _ZONEINFO = True
except ImportError:  # Python < 3.9 fallback
    _ZONEINFO = False

TIMEZONE_NAME = "America/Cuiaba"
BUSINESS_START = dtime(9, 0)
BUSINESS_END = dtime(19, 0)


def _get_tz():
    if _ZONEINFO:
        import zoneinfo as zi
        return zi.ZoneInfo(TIMEZONE_NAME)
    try:
        import pytz
        return pytz.timezone(TIMEZONE_NAME)
    except ImportError:
        return None


def _now_local() -> datetime:
    tz = _get_tz()
    if tz:
        return datetime.now(tz)
    return datetime.utcnow()


def _to_local(dt: datetime) -> datetime:
    tz = _get_tz()
    if tz and dt.tzinfo is None:
        if _ZONEINFO:
            return dt.replace(tzinfo=tz)
        return tz.localize(dt)
    if tz and dt.tzinfo is not None:
        return dt.astimezone(tz)
    return dt


def next_send_window(from_dt: Optional[datetime] = None) -> datetime:
    """Compute next valid send slot within business hours, skipping weekends.

    Returns an aware datetime in America/Cuiaba timezone (or naive UTC if
    zoneinfo/pytz unavailable).
    """
    tz = _get_tz()
    dt = from_dt if from_dt is not None else _now_local()
    dt = _to_local(dt)

    # Advance past weekend first
    for _ in range(9):  # max 9 iterations: 2 weekends + buffer
        if dt.weekday() >= 5:  # Sat=5, Sun=6
            dt = dt.replace(hour=BUSINESS_START.hour, minute=BUSINESS_START.minute, second=0, microsecond=0)
            dt = dt + timedelta(days=1)
            continue

        # Check business hours
        if dt.time() < BUSINESS_START:
            dt = dt.replace(hour=BUSINESS_START.hour, minute=BUSINESS_START.minute, second=0, microsecond=0)
        elif dt.time() >= BUSINESS_END:
            dt = dt + timedelta(days=1)
            dt = dt.replace(hour=BUSINESS_START.hour, minute=BUSINESS_START.minute, second=0, microsecond=0)
            continue

        # Valid slot found — exit
        break

    return dt


def jitter_send_time(dt: datetime, max_minutes: int = 30) -> datetime:
    """Add anti-detection jitter (human-like send spread, author-chosen range).

    Offset is random in [0, max_minutes]. This is legitimate variation used
    to avoid bot-like exact-interval patterns — same exception class as spintax
    in core/template_renderer.py.
    """
    offset = random.randint(0, max_minutes)  # noqa: anti-detection jitter
    return dt + timedelta(minutes=offset)


def compute_delay_dt(delay_days: int, from_dt: Optional[datetime] = None) -> datetime:
    """From a base time + delay_days offset, find the next business-hours send window."""
    base = from_dt if from_dt is not None else _now_local()
    base = _to_local(base)
    target = base + timedelta(days=delay_days)
    return next_send_window(target)
