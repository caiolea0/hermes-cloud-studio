"""F.3.2 — Event emit helper pra lab_runner + flows.

Emit JSON events stdout pra backend api/lab.py F.3.1 parse + WS broadcast lab.*

REGRA INVIOLAVEL: NUNCA emit payload com SENSITIVE_KEYS (li_at, token, cookie, password, etc).
Sanitizer recursivo strip antes serialize.

Whitelist 7 event types (R4 F.3.2). Outros logged warning + skipped.
"""
from __future__ import annotations
import json
import sys
import time
from typing import Any

SENSITIVE_KEYS = frozenset({
    "li_at", "token", "cookie", "session_id", "password", "auth",
    "authorization", "set-cookie", "jsessionid", "csrf", "api_key",
    "secret", "bearer", "x-li-track", "x-restli-protocol-version",
    "jsession", "li_rm", "lidc", "bcookie", "bscookie",
})

ALLOWED_EVENTS = frozenset({
    "run_started", "step_progress", "screenshot_captured",
    "compliance_score", "fingerprint_dump", "run_completed", "run_failed",
})


def _sanitize(obj: Any) -> Any:
    """Recursivamente remove SENSITIVE_KEYS de dicts. Preserva lists, scalars."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items() if str(k).lower() not in SENSITIVE_KEYS}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


def mask_email(email: str) -> str:
    """Mask email pra logs: 'milgrauz.exe@gmail.com' -> 'm***e@g***l.com'."""
    if not email or "@" not in email:
        return "***"
    user, _, domain = email.partition("@")
    if len(user) > 2:
        user = user[0] + "***" + user[-1]
    elif len(user) == 2:
        user = user[0] + "*"
    if "." in domain:
        d_main, _, d_tld = domain.partition(".")
        if len(d_main) > 2:
            d_main = d_main[0] + "***" + d_main[-1]
        domain = f"{d_main}.{d_tld}"
    return f"{user}@{domain}"


def emit(event_type: str, **payload: Any) -> None:
    """Emit JSON event stdout. Sanitize SENSITIVE_KEYS recursive.

    Strict whitelist event_type — fora ALLOWED_EVENTS = log warning stderr + skip stdout.
    Errors (broken pipe, JSON serialization) swallowed — emit nunca crash flow.
    """
    if event_type not in ALLOWED_EVENTS:
        try:
            print(
                f"[lab] WARN: emit event_type '{event_type}' fora ALLOWED_EVENTS — skipped",
                file=sys.stderr,
                flush=True,
            )
        except Exception:
            pass
        return

    try:
        sanitized = _sanitize(payload)
        envelope = {"event": event_type, "ts": time.time(), **sanitized}
        print(json.dumps(envelope, separators=(",", ":"), default=str), flush=True)
    except BrokenPipeError:
        # SSH pipe fechou — owner abort OR connection drop. Não crash flow.
        pass
    except Exception as e:
        try:
            print(
                f"[lab] WARN: emit failed event={event_type} err={type(e).__name__}: {e}",
                file=sys.stderr,
                flush=True,
            )
        except Exception:
            pass
