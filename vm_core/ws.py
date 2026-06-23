"""WebSocket manager para hermes_api_v2 (VM side).

Gerencia conexões WS ativas e broadcast de eventos do daemon.
Separado de vm_core/state.py para evitar import circular com vm_api/broadcast.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Set

from fastapi import WebSocket

logger = logging.getLogger("hermes_api_v2")


class WSManager:
    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
        logger.info("ws_manager: nova conexão, total=%d", len(self._connections))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)
        logger.debug("ws_manager: desconexão, total=%d", len(self._connections))

    async def broadcast(self, event: dict) -> None:
        if not self._connections:
            return
        payload = json.dumps(event, default=str)
        dead: Set[WebSocket] = set()
        async with self._lock:
            conns = set(self._connections)
        for ws in conns:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        if dead:
            async with self._lock:
                self._connections -= dead
            logger.debug("ws_manager: removidas %d conexões mortas", len(dead))

    def connection_count(self) -> int:
        return len(self._connections)


ws_manager = WSManager()
