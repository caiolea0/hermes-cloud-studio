"""Hermes Cloud Studio — LinkedIn session expiry monitor loop (1h) — MERGED-011."""
from __future__ import annotations

import asyncio
import time

import httpx

import core.state as state
from core.state import (
    VM_API_URL,
    _telegram_notify,
    set_runtime_state,
)


async def linkedin_session_monitor_loop():
    """Every 1h: GET /api/linkedin/session-check. If session_ok flips False, alert via Telegram.
    Avoids spamming — only notifies on transitions True→False (or every 12h while broken).
    """
    await asyncio.sleep(60)
    while True:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{VM_API_URL}/api/linkedin/session-check")
                ok = r.status_code == 200 and r.json().get("ok")
        except Exception:  # noqa: silenciado intencional — fallback de sonda
            ok = False

        now = time.time()
        if not ok:
            need_notify = state._LI_SESSION_LAST_OK or (now - state._LI_SESSION_LAST_NOTIFIED > 43200)
            if need_notify:
                await _telegram_notify(
                    "⚠️ Hermes LinkedIn: sessão caiu (session_ok=false).\n"
                    "Renove o cookie LI_AT no Chrome e o sync rodará no próximo ciclo (03:00), "
                    "ou rode agora manualmente: python scripts/li_at_sync.py"
                )
                state._LI_SESSION_LAST_NOTIFIED = now
                set_runtime_state("li_session_last_notified", state._LI_SESSION_LAST_NOTIFIED)
        elif not state._LI_SESSION_LAST_OK:
            await _telegram_notify("✅ Hermes LinkedIn: sessão restaurada.")

        state._LI_SESSION_LAST_OK = ok
        set_runtime_state("li_session_last_ok", state._LI_SESSION_LAST_OK)
        await asyncio.sleep(3600)
