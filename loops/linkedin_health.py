"""Hermes Cloud Studio — LinkedIn health probe loop (cooldown/challenge/blocked detection) — MERGED-011."""
from __future__ import annotations

import asyncio
import time

import httpx

import core.state as state
from core.state import (
    VM_API_URL,
    _telegram_notify,
    logger,
    set_runtime_state,
    ws_manager,
)


async def linkedin_health_monitor_loop():
    """Probe health every 3min. Telegram on state transitions. WS broadcast."""
    await asyncio.sleep(30)
    while True:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                fr = "true" if state._LI_HEALTH_LAST_STATE not in (None, "ok") else "false"
                r = await client.get(f"{VM_API_URL}/api/linkedin/health",
                                     params={"force_refresh": fr})
                health = r.json() if r.status_code == 200 else {}
            new_state = health.get("state")
        except Exception as e:
            logger.warning(f"health monitor probe failed: {e}")
            await asyncio.sleep(180)
            continue

        if new_state and new_state != state._LI_HEALTH_LAST_STATE:
            if state._LI_HEALTH_LAST_STATE is None:
                if new_state != "ok":
                    await _telegram_notify(
                        f"⚠️ Hermes LinkedIn: estado inicial é {new_state.upper()} — "
                        f"motivo: {health.get('reason')} — "
                        f"HTTP {health.get('http_code')}. Não rode campanhas até liberar."
                    )
            elif state._LI_HEALTH_LAST_STATE == "ok":
                await _telegram_notify(
                    f"🛑 Hermes LinkedIn entrou em {new_state.upper()}\n"
                    f"Motivo: {health.get('reason')}\n"
                    f"HTTP: {health.get('http_code')}\n"
                    f"Retry em ~{(health.get('retry_after_seconds') or 0)//60}min.\n"
                    f"Campanhas serão bloqueadas até liberar."
                )
            elif new_state == "ok":
                await _telegram_notify(
                    f"✅ Hermes LinkedIn liberado — pode rodar campanhas novamente."
                )
            try:
                await ws_manager.broadcast({"type": "linkedin_health", "data": health})
            except Exception:  # noqa: silenciado intencional — WS/broadcast opcional
                pass
            # F.2.3 — daemon.log_event paralelo pra Mission Control timeline ver health transitions.
            try:
                await ws_manager.broadcast({
                    "type": "daemon.log_event",
                    "category": "linkedin_health",
                    "level": "info" if new_state == "ok" else "warning",
                    "message": f"LinkedIn health → {new_state}",
                    "metadata": {
                        "state": new_state,
                        "previous_state": state._LI_HEALTH_LAST_STATE,
                        "reason": health.get("reason"),
                        "http_code": health.get("http_code"),
                        "retry_after_seconds": health.get("retry_after_seconds"),
                    },
                    "timestamp": time.time(),
                })
            except Exception:  # noqa: silenciado intencional — WS/broadcast opcional
                pass
            state._LI_HEALTH_LAST_STATE = new_state
            state._LI_HEALTH_NOTIFIED_AT = time.time()
            set_runtime_state("li_health_last_state", state._LI_HEALTH_LAST_STATE)
            set_runtime_state("li_health_notified_at", state._LI_HEALTH_NOTIFIED_AT)

        # Sleep duration adapts to state
        delay = {"ok": 180, "cooldown": 60, "challenge": 60, "blocked": 300}.get(new_state, 120)
        await asyncio.sleep(delay)
