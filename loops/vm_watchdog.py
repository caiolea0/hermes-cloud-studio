"""Hermes Cloud Studio — VM health watchdog loop (30s ping + auto-restart via SSH) — MERGED-011."""
from __future__ import annotations

import asyncio
import os

import httpx

from config import settings
from core.state import (
    VM_API_URL,
    _telegram_notify,
    logger,
)


async def vm_health_watchdog_loop():
    """Monitora hermes_api_v2 na VM. Probe /api/_ping a cada 30s.

    Recovery:
      - 3 falhas consecutivas (90s sem responder) -> tenta restart via SSH
      - 6 falhas (180s) -> alerta Telegram + continua tentando
      - Reset contador apos sucesso
    """
    consecutive_fail = 0
    alerted = False
    RESTART_CMD = settings.hermes_vm_restart_cmd
    SSH_KEY = os.environ.get("USERPROFILE", "") + r"\.ssh\id_ed25519"
    vm_user = settings.vm_user
    vm_host = settings.vm_host

    await asyncio.sleep(30)
    while True:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(f"{VM_API_URL}/api/_ping")
                if r.status_code == 200:
                    if consecutive_fail > 0:
                        logger.info(f"vm_watchdog: VM voltou apos {consecutive_fail} falhas")
                    consecutive_fail = 0
                    alerted = False
                else:
                    consecutive_fail += 1
                    logger.warning(f"vm_watchdog: ping status={r.status_code} (fail #{consecutive_fail})")
        except Exception as e:
            consecutive_fail += 1
            logger.warning(f"vm_watchdog: ping erro {type(e).__name__} (fail #{consecutive_fail})")

        if consecutive_fail == 3:
            logger.error("vm_watchdog: 3 falhas consecutivas — tentando restart via SSH")
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ssh", "-i", SSH_KEY,
                    "-o", "ConnectTimeout=10", "-o", "BatchMode=yes",
                    f"{vm_user}@{vm_host}", RESTART_CMD,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
                logger.info(f"vm_watchdog: restart SSH rc={proc.returncode} "
                            f"out={stdout.decode()[:200]} err={stderr.decode()[:200]}")
            except Exception as e:
                logger.error(f"vm_watchdog: SSH restart falhou: {e}")

        if consecutive_fail == 6 and not alerted:
            try:
                await _telegram_notify(
                    f"VM Hermes ({vm_host}:8420) sem responder ha {consecutive_fail*30}s. "
                    f"Restart SSH tentado mas sem efeito. Verificar manualmente:\n"
                    f"  ssh {vm_user}@{vm_host}\n"
                    f"  ps aux | grep hermes_api"
                )
                alerted = True
            except Exception as e:
                logger.warning(f"vm_watchdog: telegram alert falhou: {e}")

        await asyncio.sleep(30)
