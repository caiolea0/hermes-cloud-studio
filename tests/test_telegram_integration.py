"""F.7 C4 — TelegramClient + CobaiaAlertListener unit tests (5 tests, mocked).

All network calls are mocked — no real Telegram API hits.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from core.telegram_client import TelegramClient, escape_markdown
from daemon.telegram_alert import CobaiaAlertListener


# ── TelegramClient tests ───────────────────────────────────────────────────────


def test_send_message_rate_limit_5_per_hour():
    """After 5 successful sends, 6th is rejected (hourly cap)."""
    client = TelegramClient(token="fake", chat_id="123", max_per_hour=5, min_interval_s=0.0)
    with patch.object(client, "_do_send", return_value=True) as mock_send:
        for i in range(5):
            result = client.send_message(f"msg {i}")
            assert result is True, f"Send {i} should succeed"
        # 6th send should be blocked by hourly cap
        result = client.send_message("msg 6")
        assert result is False, "6th send should be rate-limited"
        assert mock_send.call_count == 5


def test_send_alert_severity_emoji_prefix():
    """send_alert prepends correct emoji for each severity level."""
    client = TelegramClient(token="fake", chat_id="123", max_per_hour=10, min_interval_s=0.0)
    sent_texts: list[str] = []

    def capture_send(text: str, parse_mode: str) -> bool:
        sent_texts.append(text)
        return True

    with patch.object(client, "_do_send", side_effect=capture_send):
        client.send_alert("critical", "Test", "body")
        client.send_alert("warning", "Test", "body")
        client.send_alert("info", "Test", "body")
        client.send_alert("ok", "Test", "body")

    assert sent_texts[0].startswith("🚨")
    assert sent_texts[1].startswith("⚠️")
    assert sent_texts[2].startswith("ℹ️")
    assert sent_texts[3].startswith("✅")


def test_telegram_client_handles_api_failure():
    """Failed HTTP call logs warning and returns False without raising."""
    client = TelegramClient(token="fake", chat_id="123", max_per_hour=5, min_interval_s=0.0)
    with patch("httpx.post", side_effect=ConnectionError("network down")):
        result = client.send_message("test")
    assert result is False
    # _record_send should NOT have been called (nothing in window)
    assert len(client._send_times) == 0


# ── CobaiaAlertListener tests ─────────────────────────────────────────────────


def test_telegram_alert_listener_cobaia_auto_paused():
    """cobaia.auto_paused event triggers critical alert via client."""
    mock_client = MagicMock()
    mock_client.send_alert.return_value = True
    listener = CobaiaAlertListener(client=mock_client)

    listener.handle_event(
        "cobaia.auto_paused",
        {"account_handle": "cobaia-test", "reason": "3 consecutive errors", "consecutive_errors": 3},
    )

    mock_client.send_alert.assert_called_once()
    call_kwargs = mock_client.send_alert.call_args[1] if mock_client.send_alert.call_args[1] else {}
    call_args = mock_client.send_alert.call_args[0] if mock_client.send_alert.call_args[0] else ()
    # Check severity=critical was passed (positional or keyword)
    all_args = list(call_args) + list(call_kwargs.values())
    assert "critical" in all_args or call_kwargs.get("severity") == "critical"


def test_telegram_alert_threshold_fires_at_5_errors():
    """CobaiaAlertListener sends batch alert exactly when error count hits threshold."""
    mock_client = MagicMock()
    mock_client.send_alert.return_value = True
    listener = CobaiaAlertListener(client=mock_client)

    # Force last_threshold_alert to old value so cooldown doesn't block
    listener._last_threshold_alert = 0.0

    # Send 4 errors — no threshold alert yet
    for i in range(4):
        listener.handle_event("cobaia.error", {"message": f"error {i}"})
    assert mock_client.send_alert.call_count == 0

    # 5th error crosses threshold → alert fires
    listener.handle_event("cobaia.error", {"message": "error 5"})
    assert mock_client.send_alert.call_count == 1
    call_kwargs = mock_client.send_alert.call_args
    assert call_kwargs is not None
