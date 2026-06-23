"""H2-F3 — Per-domain rate limiter para scrape_website (polite crawling).

Garante:
  - Mínimo de MIN_INTERVAL segundos entre requests ao MESMO domínio.
  - Cap de MAX_CONCURRENT domínios simultâneos (global asyncio.Semaphore).

Uso no daemon:
    from core.scrape_limiter import ScrapeLimiter
    _limiter = ScrapeLimiter()

    async with _limiter.domain_slot(url):
        result = await asyncio.to_thread(scrape_website, url)
"""
from __future__ import annotations

import asyncio
import logging
import time
from urllib.parse import urlparse

logger = logging.getLogger("hermes.scrape_limiter")

DEFAULT_MIN_INTERVAL: float = 4.0   # segundos entre requests ao mesmo host
DEFAULT_MAX_CONCURRENT: int = 4     # cap global de domínios simultâneos


class ScrapeLimiter:
    """Polite per-domain rate limiter + global concurrency cap (async-safe)."""

    def __init__(
        self,
        min_interval: float = DEFAULT_MIN_INTERVAL,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    ) -> None:
        self._min_interval = min_interval
        # Semaphore garante cap global (criado lazy para evitar problema de event loop)
        self._sem: asyncio.Semaphore | None = None
        self._max_concurrent = max_concurrent
        # Mapa domain → monotonic timestamp da última request
        self._domain_last: dict[str, float] = {}
        # Lock por domínio garante que dois coroutines do mesmo domínio não disparam juntos
        self._domain_locks: dict[str, asyncio.Lock] = {}

    def _get_sem(self) -> asyncio.Semaphore:
        if self._sem is None:
            self._sem = asyncio.Semaphore(self._max_concurrent)
        return self._sem

    @staticmethod
    def _extract_domain(url: str) -> str:
        try:
            netloc = urlparse(url).netloc or url
            return netloc.replace("www.", "").lower()
        except Exception:
            return url.lower()

    def _domain_lock(self, domain: str) -> asyncio.Lock:
        if domain not in self._domain_locks:
            self._domain_locks[domain] = asyncio.Lock()
        return self._domain_locks[domain]

    async def _wait_domain(self, domain: str) -> None:
        """Aguarda MIN_INTERVAL desde última request a este domínio."""
        async with self._domain_lock(domain):
            last = self._domain_last.get(domain, 0.0)
            elapsed = time.monotonic() - last
            if elapsed < self._min_interval:
                wait = self._min_interval - elapsed
                logger.debug("scrape_limiter domain=%s wait=%.2fs", domain, wait)
                await asyncio.sleep(wait)
            self._domain_last[domain] = time.monotonic()

    async def acquire(self, url: str) -> None:
        """Adquire semaphore global + respeita intervalo por domínio."""
        await self._get_sem().acquire()
        domain = self._extract_domain(url)
        try:
            await self._wait_domain(domain)
        except Exception:
            # Libera semaphore se wait falhar (não deve acontecer)
            self._get_sem().release()
            raise

    def release(self) -> None:
        """Libera semaphore global."""
        try:
            self._get_sem().release()
        except Exception:
            pass

    # ---------------------------------------------------------------------------
    # Async context manager
    # ---------------------------------------------------------------------------

    class _Slot:
        def __init__(self, limiter: "ScrapeLimiter", url: str) -> None:
            self._limiter = limiter
            self._url = url

        async def __aenter__(self) -> "ScrapeLimiter._Slot":
            await self._limiter.acquire(self._url)
            return self

        async def __aexit__(self, *_) -> None:
            self._limiter.release()

    def domain_slot(self, url: str) -> "_Slot":
        """Async context manager: adquire semaphore + per-domain cooldown.

        Uso:
            async with limiter.domain_slot(url):
                result = await asyncio.to_thread(scrape_website, url)
        """
        return self._Slot(self, url)
