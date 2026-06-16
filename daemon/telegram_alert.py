"""F.7 C4 — Cobaia Telegram alert listener.

Handles WS-style events from cobaia daemon and sends Telegram alerts
via TelegramClient (rate-limited: 5/h cap, 1/min throttle).

Events handled:
  cobaia.auto_paused      (D4 trigger) → critical alert
  cobaia.paused           (manual)     → info alert
  cobaia.resumed                       → info alert
  skill.quarantined       (F.4.4)      → warning alert
  cobaia.error                         → count; batch alert at 5/h threshold

Error threshold (D5): 5 errors/hour → 🚨 batch summary alert (1 per hour max).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger("hermes.cobaia.telegram_alert")

_ERROR_THRESHOLD_PER_HOUR = 5
_THRESHOLD_ALERT_COOLDOWN = 3600.0  # max 1 threshold alert per hour


class CobaiaAlertListener:
    """Thread-safe Telegram alert dispatcher for cobaia events."""

    def __init__(self, client=None):
        if client is None:
            from core.telegram_client import TelegramClient
            client = TelegramClient()
        self._client = client
        self._lock = threading.Lock()
        self._error_window: list[float] = []   # monotonic timestamps of cobaia.error events
        self._last_threshold_alert: float = 0.0

    def handle_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Dispatch event to handler. Silently ignores unknown event types."""
        handlers = {
            "cobaia.auto_paused": self._on_auto_paused,
            "cobaia.paused": self._on_paused,
            "cobaia.resumed": self._on_resumed,
            "skill.quarantined": self._on_skill_quarantined,
            "cobaia.error": self._on_error,
        }
        handler = handlers.get(event_type)
        if handler:
            try:
                handler(data)
            except Exception as exc:
                logger.warning("telegram_alert handler %s error: %s", event_type, exc)

    def _on_auto_paused(self, data: dict[str, Any]) -> None:
        reason = data.get("reason", "unknown")
        errors = data.get("consecutive_errors", "?")
        account = data.get("account_handle", "cobaia")
        self._client.send_alert(
            severity="critical",
            title=f"Cobaia AUTO-PAUSADO — {account}",
            body=f"Motivo: {reason}\nErros consecutivos: {errors}",
        )

    def _on_paused(self, data: dict[str, Any]) -> None:
        reason = data.get("reason", "manual")
        account = data.get("account_handle", "cobaia")
        self._client.send_alert(
            severity="info",
            title=f"Cobaia pausado — {account}",
            body=f"Motivo: {reason}",
        )

    def _on_resumed(self, data: dict[str, Any]) -> None:
        account = data.get("account_handle", "cobaia")
        self._client.send_alert(
            severity="info",
            title=f"Cobaia retomado — {account}",
            body="Warmup continua.",
        )

    def _on_skill_quarantined(self, data: dict[str, Any]) -> None:
        skill = data.get("skill_name", "?")
        reason = data.get("reason", "auto")
        self._client.send_alert(
            severity="warning",
            title=f"Skill quarentenada: {skill}",
            body=f"Motivo: {reason}",
        )

    def _on_error(self, data: dict[str, Any]) -> None:
        """Track error; fire batch alert when threshold (5/h) exceeded."""
        with self._lock:
            now = time.monotonic()
            # Prune events older than 1h
            self._error_window = [t for t in self._error_window if now - t < 3600.0]
            self._error_window.append(now)
            count = len(self._error_window)
            if count >= _ERROR_THRESHOLD_PER_HOUR:
                since_last = now - self._last_threshold_alert
                if since_last >= _THRESHOLD_ALERT_COOLDOWN:
                    self._last_threshold_alert = now
                    msg = str(data.get("message", "?"))[:100]
                    self._client.send_alert(
                        severity="critical",
                        title=f"Cobaia — {count} erros/hora (limite {_ERROR_THRESHOLD_PER_HOUR})",
                        body=f"Ultimo erro: {msg}",
                    )


# Module-level singleton
_listener: CobaiaAlertListener | None = None


def get_listener() -> CobaiaAlertListener:
    global _listener
    if _listener is None:
        _listener = CobaiaAlertListener()
    return _listener


def dispatch_event(event_type: str, data: dict[str, Any]) -> None:
    """Convenience entry point for daemon/scheduler calls."""
    try:
        get_listener().handle_event(event_type, data)
    except Exception as exc:
        logger.warning("telegram_alert dispatch error: %s", exc)
