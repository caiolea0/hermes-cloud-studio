"""F.5.3 Commit 2 — MCPClientPool TTL 5min auto-respawn.

Pool de fastmcp.Client (STDIO subprocess) compartilhado entre dispatches gateway.
Evita spawn 100-300ms/call (latency proibitivo Brain F.6 chain calls).

Cross-ref: PLAN.md F.5.3 D1+D2 + .claude/MCP-ENFORCEMENT-STRATEGY.md.

Pattern:
    pool = MCPClientPool(ttl_seconds=300, max_idle=10)
    client = await pool.acquire("hermes-linkedin", "python3", ["mcps/hermes-linkedin/server.py"])
    result = await client.call_tool("get_health", {})
    ...
    await pool.close_all()  # shutdown handler
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

try:
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport
except ImportError as exc:  # pragma: no cover — VM-only dep
    raise SystemExit(
        f"fastmcp não instalado. F.5.3 exige fastmcp>=3.0 na VM. Erro: {exc}"
    )

log = logging.getLogger("hermes.gateway.pool")


class MCPClientPool:
    """Connection pool per upstream server (STDIO subprocess).

    TTL 5min default + auto-respawn on disconnect. Max idle clients = 10
    (gateway tem 3 customs F.5.2 + ~5 públicos F.5.6, 10 dá folga).
    """

    def __init__(self, ttl_seconds: int = 300, max_idle: int = 10) -> None:
        self._clients: dict[str, Client] = {}
        self._last_used: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self.ttl = ttl_seconds
        self.max_idle = max_idle

    async def acquire(
        self,
        server_name: str,
        command: str,
        args: list[str],
        cwd: Optional[str] = None,
    ) -> Client:
        """Retorna client conectado pro server_name. Spawn lazy + cache TTL.

        Args:
            server_name: identificador upstream (ex 'hermes-linkedin').
            command: executável STDIO (ex 'python3').
            args: argumentos (ex ['mcps/hermes-linkedin/server.py']).
            cwd: working directory opcional.

        Returns:
            fastmcp.Client conectado, pronto pra call_tool().
        """
        async with self._lock:
            now = time.monotonic()
            # Evict expired clients (TTL)
            expired = [s for s, t in self._last_used.items() if now - t > self.ttl]
            for s in expired:
                await self._close_locked(s)
                log.info("pool evict expired: %s (idle %ds)", s, int(now - self._last_used.get(s, now)))

            # Cache hit — health check before reuse
            if server_name in self._clients:
                client = self._clients[server_name]
                try:
                    if client.is_connected():
                        self._last_used[server_name] = now
                        return client
                    log.warning("pool client %s disconnected, respawn", server_name)
                except Exception as e:
                    log.warning("pool client %s health check failed (%s), respawn", server_name, e)
                await self._close_locked(server_name)

            # Enforce max_idle (LRU evict if at cap)
            if len(self._clients) >= self.max_idle:
                lru_server = min(self._last_used, key=self._last_used.get)
                log.info("pool max_idle=%d hit, evict LRU: %s", self.max_idle, lru_server)
                await self._close_locked(lru_server)

            # Spawn new client
            transport = StdioTransport(command=command, args=args, cwd=cwd)
            client = Client(transport)
            await client.__aenter__()  # async context enter (connects subprocess)
            self._clients[server_name] = client
            self._last_used[server_name] = now
            log.info("pool spawn new: %s (pool size=%d)", server_name, len(self._clients))
            return client

    async def _close_locked(self, server_name: str) -> None:
        """Close client (lock must already be held)."""
        client = self._clients.pop(server_name, None)
        self._last_used.pop(server_name, None)
        if client is None:
            return
        try:
            await client.__aexit__(None, None, None)
        except Exception as e:
            log.warning("pool close %s raised: %s", server_name, e)

    async def close_all(self) -> None:
        """Shutdown handler — close all pooled clients (evita zombie subprocess VM)."""
        async with self._lock:
            for s in list(self._clients.keys()):
                await self._close_locked(s)
            log.info("pool close_all done")

    def stats(self) -> dict:
        """Pool stats pra debugging / observability."""
        now = time.monotonic()
        return {
            "pool_size": len(self._clients),
            "max_idle": self.max_idle,
            "ttl_seconds": self.ttl,
            "clients": [
                {"server": s, "idle_seconds": int(now - t)}
                for s, t in sorted(self._last_used.items())
            ],
        }
