"""F.7 C4 — TelegramClient with rate limiting.

Rate limits (Telegram-safe):
  - max_per_hour=5 : sliding 1-hour window cap
  - min_interval_s=60 : minimum 60s between sends (1/min throttle)

Reuses TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID env vars (same as daemon/orchestrator.py).
Uses httpx (already a project dep).
"""
from __future__ import annotations

import logging
import os
import time
from collections import deque

logger = logging.getLogger("hermes.telegram_client")

SEVERITY_EMOJI: dict[str, str] = {
    "critical": "🚨",
    "warning": "⚠️",
    "info": "ℹ️",
    "ok": "✅",
}

_MD_SPECIAL = r"\_*[]()~`>#+-=|{}.!"


def escape_markdown(text: str) -> str:
    """Escape Telegram MarkdownV2 special characters."""
    for ch in _MD_SPECIAL:
        text = text.replace(ch, f"\\{ch}")
    return text


class TelegramClient:
    """Thin Telegram Bot API client with rate-limit guards.

    Limits:
        max_per_hour  — sliding 1-hour window (default 5)
        min_interval_s — minimum seconds between sends (default 60)

    On rate-limit hit: logs and returns False (no drop, no queue).
    On send failure: logs + Sentry breadcrumb, returns False.
    """

    def __init__(
        self,
        token: str | None = None,
        chat_id: str | None = None,
        max_per_hour: int = 5,
        min_interval_s: float = 60.0,
    ):
        self._token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        self._max_per_hour = max_per_hour
        self._min_interval_s = min_interval_s
        self._send_times: deque[float] = deque()
        self._last_sent: float = 0.0

    def _configured(self) -> bool:
        return bool(self._token and self._chat_id)

    def _check_rate_limit(self) -> tuple[bool, str]:
        """Prune window, then check min_interval and hourly cap."""
        now = time.monotonic()
        cutoff = now - 3600.0
        while self._send_times and self._send_times[0] < cutoff:
            self._send_times.popleft()
        elapsed = now - self._last_sent
        if self._last_sent > 0 and elapsed < self._min_interval_s:
            remaining = self._min_interval_s - elapsed
            return False, f"throttle: {remaining:.0f}s remaining"
        if len(self._send_times) >= self._max_per_hour:
            return False, f"rate_limit: {self._max_per_hour}/h cap reached"
        return True, ""

    def _record_send(self) -> None:
        now = time.monotonic()
        self._send_times.append(now)
        self._last_sent = now

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send text message. Returns True on success."""
        if not self._configured():
            logger.debug("telegram_client: not configured")
            return False
        allowed, reason = self._check_rate_limit()
        if not allowed:
            logger.info("telegram_client rate-limited: %s", reason)
            return False
        result = self._do_send(text, parse_mode)
        if result:
            self._record_send()
        return result

    def _do_send(self, text: str, parse_mode: str) -> bool:
        try:
            import httpx
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            resp = httpx.post(
                url,
                json={"chat_id": self._chat_id, "text": text, "parse_mode": parse_mode},
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("telegram_client: message sent OK")
            return True
        except Exception as exc:
            logger.warning("telegram_client send failed: %s", exc)
            _sentry_breadcrumb("cobaia.telegram_send_failed", {"error": str(exc)})
            return False

    def send_alert(self, severity: str, title: str, body: str) -> bool:
        """Send alert with severity emoji prefix in HTML parse mode."""
        emoji = SEVERITY_EMOJI.get(severity, "ℹ️")
        text = f"{emoji} <b>{title}</b>\n{body}"
        return self.send_message(text, parse_mode="HTML")


def _sentry_breadcrumb(msg: str, data: dict) -> None:
    try:
        import sentry_sdk  # type: ignore[import-not-found]
        sentry_sdk.add_breadcrumb(category="cobaia", message=msg, data=data, level="warning")
    except Exception:
        pass
