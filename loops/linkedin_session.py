"""Hermes Cloud Studio — LinkedIn session expiry monitor loop (1h) — MERGED-011."""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

import core.state as state
from core.state import (
    VM_API_URL,
    _telegram_notify,
    set_runtime_state,
)

logger = logging.getLogger("hermes.server")

# MERGED-018 — confirmação por falhas consecutivas mata spam por flake de rede.
# Probe 1h * 3 = 3h de janela antes de declarar sessão morta.
REQUIRED_FAILS = 3


async def linkedin_session_monitor_loop():
    """Every 1h: GET /api/linkedin/session-check.

    MERGED-018: contabiliza falhas consecutivas; só declara sessão morta após
    REQUIRED_FAILS (3) probes seguidos falhando. Uma probe ok zera o contador.
    Evita spam Telegram por flake de rede / VM lag.
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
        if ok:
            if state._LI_SESSION_FAIL_STREAK > 0:
                logger.info(
                    "session_monitor: probe OK, reset fail_streak=%d",
                    state._LI_SESSION_FAIL_STREAK,
                )
            state._LI_SESSION_FAIL_STREAK = 0
            set_runtime_state("li_session_fail_streak", 0)
            if not state._LI_SESSION_LAST_OK:
                await _telegram_notify("✅ Hermes LinkedIn: sessão restaurada.")
            state._LI_SESSION_LAST_OK = True
            set_runtime_state("li_session_last_ok", True)
        else:
            state._LI_SESSION_FAIL_STREAK += 1
            set_runtime_state("li_session_fail_streak", state._LI_SESSION_FAIL_STREAK)
            confirmed_dead = state._LI_SESSION_FAIL_STREAK >= REQUIRED_FAILS
            if not confirmed_dead:
                logger.info(
                    "session_monitor: probe fail %d/%d (aguardando confirmação)",
                    state._LI_SESSION_FAIL_STREAK, REQUIRED_FAILS,
                )
            else:
                need_notify = state._LI_SESSION_LAST_OK or (
                    now - state._LI_SESSION_LAST_NOTIFIED > 43200
                )
                if need_notify:
                    await _telegram_notify(
                        f"⚠️ Hermes LinkedIn: sessão caiu (session_ok=false, "
                        f"{state._LI_SESSION_FAIL_STREAK} probes falharam).\n"
                        "Renove o cookie LI_AT no Chrome e o sync rodará no próximo ciclo (03:00), "
                        "ou rode agora manualmente: python scripts/li_at_sync.py"
                    )
                    state._LI_SESSION_LAST_NOTIFIED = now
                    set_runtime_state("li_session_last_notified", state._LI_SESSION_LAST_NOTIFIED)
                state._LI_SESSION_LAST_OK = False
                set_runtime_state("li_session_last_ok", False)
        await asyncio.sleep(3600)
