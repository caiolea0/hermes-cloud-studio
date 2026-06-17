"""H5 HARDENING — Sentry via MCP gateway wrapper (B4 fix).

Substitui `import sentry_sdk` direto em 15+ call sites por dispatch via
gateway loopback (defense-in-depth MCP HARD REQ F.4/F.6/F.7/F.8).

Control flow:
  1. Gateway dispatch: POST /dispatch/sentry/{tool} (fire-and-forget, non-blocking)
  2. Fallback: sentry_sdk direct call se SDK instalado (VM env)
  3. Buffer: ring buffer in-memory se ambos indisponíveis (flush_buffer() retry)

Callers passam `requester=` string p/ audit trail (F.4 D7 pattern):
  core/auto_skill_runner.py  → "brain-f4"
  brain/decide.py            → "brain-core"
  brain/persistence.py       → "brain-core"
  api/cobaia.py              → "brain-f7-cobaia"
  daemon/email_digest.py     → "brain-f7-cobaia"
  daemon/cobaia_warmup_scheduler.py → "brain-f7-cobaia"
  core/cobaia_autotune.py    → "brain-f7-cobaia-autotune"
  api/skills.py              → "brain-f4"
  api/skills_webhook.py      → "brain-f4-webhook"
  scripts/quarantine_skills.py → "brain-f4-cron"
  core/pipeline_engine.py    → "brain-f9"
  core/observability.py      → "brain-f8"
  core/telegram_client.py    → "brain-f7-cobaia"
  core/email_verifier.py     → "brain-f7-cobaia"
  scripts/check_nim_credits.py → "brain-f8"
"""
from __future__ import annotations

import logging
import sys
from typing import Any, Optional

logger = logging.getLogger("hermes.sentry_gateway")

# Optional sentry_sdk — graceful absent in dev/PC; installed on VM
try:
    import sentry_sdk as _sentry_sdk  # type: ignore[import-not-found]
    _SENTRY_AVAILABLE = True
except ImportError:
    _sentry_sdk = None  # type: ignore
    _SENTRY_AVAILABLE = False

_LOCAL_BUFFER: list[dict] = []  # Ring buffer — events queued when gateway + sdk unavailable
_MAX_BUFFER = 100


def _gateway_dispatch_async(tool: str, args: dict, requester: str) -> None:
    """Fire-and-forget gateway dispatch — never raises, non-blocking."""
    try:
        import asyncio
        from brain.dispatch import GatewayDispatcher  # lazy to avoid circular

        async def _do() -> None:
            try:
                d = GatewayDispatcher()
                await d.invoke_tool("sentry", tool, args, requester=requester)
            except Exception:  # noqa: BLE001 — best-effort only
                pass

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_do())
        except RuntimeError:
            # No running loop (sync context) — skip gateway, fallback below handles it
            pass
    except Exception:  # noqa: BLE001
        pass


def capture_exception(
    exc: Optional[BaseException] = None,
    requester: str = "unknown",
    extra: Optional[dict] = None,
    level: str = "error",
) -> None:
    """Capture exception — gateway → sentry_sdk direct → buffer.

    If exc is None, captures sys.exc_info()[1] (current exception context).
    """
    if exc is None:
        exc = sys.exc_info()[1]

    exc_str = str(exc)[:1000] if exc else "no_active_exception"
    exc_type = type(exc).__name__ if exc else "UnknownException"

    # 1. Gateway dispatch (fire-and-forget, non-blocking)
    try:
        _gateway_dispatch_async(
            "capture_exception",
            {"message": exc_str, "exception_type": exc_type, "level": level, "extra": extra or {}, "requester": requester},
            requester,
        )
    except Exception:  # noqa: BLE001 — dispatch must never block caller
        pass

    # 2. sentry_sdk direct (primary on VM where SDK initialized)
    if _SENTRY_AVAILABLE and _sentry_sdk is not None:
        try:
            if exc is not None:
                _sentry_sdk.capture_exception(exc)
            else:
                _sentry_sdk.capture_exception()
        except Exception:  # noqa: BLE001
            pass
        return

    # 3. Buffer (dev env, no SDK, no gateway)
    if len(_LOCAL_BUFFER) < _MAX_BUFFER:
        _LOCAL_BUFFER.append({
            "type": "exception",
            "exc": exc_str,
            "exc_type": exc_type,
            "requester": requester,
            "extra": extra or {},
        })


def capture_message(
    message: str,
    level: str = "info",
    requester: str = "unknown",
    **_kwargs: Any,
) -> None:
    """Capture message — gateway → sentry_sdk direct → buffer.

    `**_kwargs` absorbs non-standard args from existing call sites (e.g. `extras=`).
    """
    msg = str(message)[:1000]

    _gateway_dispatch_async(
        "capture_message",
        {"message": msg, "level": level, "requester": requester},
        requester,
    )

    if _SENTRY_AVAILABLE and _sentry_sdk is not None:
        try:
            _sentry_sdk.capture_message(msg, level=level)
        except Exception:  # noqa: BLE001
            pass
        return

    if len(_LOCAL_BUFFER) < _MAX_BUFFER:
        _LOCAL_BUFFER.append({"type": "message", "message": msg, "level": level, "requester": requester})


def capture_message_with_extras(
    message: str,
    extras: dict,
    level: str = "warning",
    requester: str = "unknown",
) -> None:
    """Replaces `with sentry_sdk.push_scope() as scope: scope.set_extra(...); capture_message(...)`.

    Dispatches gateway first, then uses push_scope if SDK available.
    """
    msg = str(message)[:1000]

    _gateway_dispatch_async(
        "capture_message",
        {"message": msg, "level": level, "extras": extras, "requester": requester},
        requester,
    )

    if _SENTRY_AVAILABLE and _sentry_sdk is not None:
        try:
            with _sentry_sdk.push_scope() as scope:
                for k, v in extras.items():
                    scope.set_extra(k, v)
                _sentry_sdk.capture_message(msg, level=level)
        except Exception:  # noqa: BLE001
            pass
        return

    if len(_LOCAL_BUFFER) < _MAX_BUFFER:
        _LOCAL_BUFFER.append({
            "type": "message_with_extras",
            "message": msg,
            "level": level,
            "extras": extras,
            "requester": requester,
        })


def add_breadcrumb(
    category: Optional[str] = None,
    message: Optional[str] = None,
    level: str = "info",
    data: Optional[dict] = None,
    **_kwargs: Any,
) -> None:
    """Add Sentry breadcrumb — fire-and-forget, silent fallback.

    `**_kwargs` absorbs extra args for call-site compatibility.
    """
    if _SENTRY_AVAILABLE and _sentry_sdk is not None:
        try:
            _sentry_sdk.add_breadcrumb(
                category=category,
                message=message,
                level=level,
                data=data or {},
            )
        except Exception:  # noqa: BLE001
            pass


def flush_buffer() -> int:
    """Retry buffered events against sentry_sdk (call after SDK initialized or gateway recovered)."""
    global _LOCAL_BUFFER
    if not _LOCAL_BUFFER:
        return 0
    buffered = _LOCAL_BUFFER[:]
    _LOCAL_BUFFER = []
    count = 0
    for item in buffered:
        try:
            item_type = item.get("type", "exception")
            req = item.get("requester", "unknown")
            if item_type == "message" or item_type == "message_with_extras":
                capture_message(item.get("message", ""), level=item.get("level", "info"), requester=req)
            else:
                capture_exception(requester=req, extra=item.get("extra"))
            count += 1
        except Exception:  # noqa: BLE001
            pass
    return count
