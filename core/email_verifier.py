"""F.7 P5 hardening — Hunter.io email verifier wrapper.

Task 6 (PLAN.md F.7) + MCP HARD REQ: validate email deliverability ANTES
warmup send. Risk: bounce rate >2% queima sender reputation cobaia domain.

R7 refactor — direct httpx api.hunter.io replaced by GatewayDispatcher
dispatch to mcps/hunter/server.py (hermes-hunter MCP). Fixes BANNED-PATTERNS
httpx loophole (only `requests.*` was caught, not `httpx.AsyncClient`).

Endpoints downstream:
  POST /api/cobaia/verify-email   {email}
  GET  /api/cobaia/hunter-usage

Hunter.io free tier:
  - 25 verifies/month (NOT 50 — check Hunter dashboard)
  - 15 req/min rate limit
  - 100 searches/month domain_search

Cache strategy:
  - SQLite hunter_email_cache table
  - TTL 30 dias (LinkedIn change emails infrequent)
  - Hit cache → 0 API call (preserva quota)

Quota exhaust → graceful fallback (status='quota_exhausted', cached:bool)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("hermes.email_verifier")

_CACHE_TTL_DAYS = 30
_RATE_LIMIT_PER_MIN = 15
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

# R7 R5 bearer — per-role or shared fallback
_HUNTER_BEARER: str = (
    os.getenv("HERMES_GATEWAY_BEARER_BRAIN_F7_COBAIA")
    or os.getenv("HERMES_GATEWAY_OAUTH_SECRET", "")
)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class EmailVerifier:
    """Hunter.io v2 client via MCP gateway + SQLite cache + rate limit + Sentry breadcrumbs.

    R7: httpx direct calls replaced by GatewayDispatcher → hermes-hunter MCP.
    API key no longer passed by caller; MCP server reads HUNTER_API_KEY from its env.
    `api_key` param kept for backward compat (guards no_api_key early exit).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        db_path: Optional[str] = None,
        dispatcher: Any = None,
    ):
        self.api_key = api_key or os.getenv("HUNTER_API_KEY", "")
        self.db_path = db_path or os.getenv("HERMES_DB_PATH") or str(
            Path(__file__).resolve().parent.parent / "hermes_local.db"
        )
        self._dispatcher = dispatcher  # injected in tests; lazily created otherwise
        self._rate_window: list[float] = []
        self._rate_lock = asyncio.Lock()

    # ---------- internal ----------

    def _get_dispatcher(self) -> Any:
        if self._dispatcher is None:
            from brain.dispatch import GatewayDispatcher
            self._dispatcher = GatewayDispatcher(bearer=_HUNTER_BEARER)
        return self._dispatcher

    def _unwrap_gateway(self, resp: dict) -> dict:
        """Extract tool-return dict from gateway dispatch response."""
        if not resp.get("ok"):
            return {}
        payload = resp.get("response")
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list) and payload:
            # FastMCP TextContent: [{"type": "text", "text": "{...json...}"}]
            text = payload[0].get("text", "") if isinstance(payload[0], dict) else ""
            if text:
                try:
                    return json.loads(text)
                except Exception:
                    pass
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except Exception:
                pass
        return {}

    def _breadcrumb(self, message: str, data: dict) -> None:
        from core.sentry_via_gateway import add_breadcrumb
        add_breadcrumb(category="hunter", message=message, data=data, level="info")

    async def _throttle(self) -> None:
        """Enforce 15 req/min sliding window (Hunter free tier, defense-in-depth)."""
        async with self._rate_lock:
            now = time.time()
            self._rate_window = [t for t in self._rate_window if now - t < 60]
            if len(self._rate_window) >= _RATE_LIMIT_PER_MIN:
                wait = 60 - (now - self._rate_window[0]) + 0.1
                logger.info("hunter rate limit throttle %.1fs", wait)
                await asyncio.sleep(wait)
                now = time.time()
                self._rate_window = [t for t in self._rate_window if now - t < 60]
            self._rate_window.append(now)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _cache_get(self, email: str) -> Optional[dict]:
        try:
            conn = self._conn()
            row = conn.execute(
                "SELECT * FROM hunter_email_cache WHERE email = ?",
                (email.lower(),),
            ).fetchone()
            conn.close()
        except sqlite3.OperationalError:
            return None  # table missing (migration not applied)
        if not row:
            return None
        try:
            expires = datetime.fromisoformat(row["expires_at"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < _now_utc():
                return None  # expired
        except Exception:
            return None
        return {
            "email": row["email"],
            "status": row["status"],
            "score": row["score"],
            "smtp_check": bool(row["smtp_check"]),
            "mx_records": bool(row["mx_records"]),
            "disposable": bool(row["disposable"]),
            "webmail": bool(row["webmail"]),
            "cached": True,
            "verified_at": row["verified_at"],
        }

    def _cache_put(self, email: str, result: dict, raw: dict) -> None:
        try:
            conn = self._conn()
            now = _now_utc()
            expires = now + timedelta(days=_CACHE_TTL_DAYS)
            conn.execute(
                """INSERT OR REPLACE INTO hunter_email_cache
                   (email, status, score, smtp_check, mx_records, disposable,
                    webmail, raw_json, verified_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    email.lower(),
                    result.get("status", "unknown"),
                    result.get("score"),
                    1 if result.get("smtp_check") else 0,
                    1 if result.get("mx_records") else 0,
                    1 if result.get("disposable") else 0,
                    1 if result.get("webmail") else 0,
                    json.dumps(raw)[:50_000],
                    _iso(now),
                    _iso(expires),
                ),
            )
            conn.commit()
            conn.close()
        except sqlite3.OperationalError as e:
            logger.warning("hunter cache_put failed (migration missing?): %s", e)

    # ---------- public ----------

    def is_valid_format(self, email: str) -> bool:
        return bool(_EMAIL_RE.match(email or ""))

    async def verify_email(self, email: str) -> dict:
        """Verify email via hermes-hunter MCP → gateway dispatch.

        Status: 'valid' | 'invalid' | 'accept_all' | 'unknown' | 'quota_exhausted'
        | 'format_invalid' | 'no_api_key' | 'gateway_error'

        cached: True if served from SQLite cache (no MCP call).
        """
        if not email or not self.is_valid_format(email):
            return {
                "email": email,
                "status": "format_invalid",
                "score": 0,
                "cached": False,
            }

        cached = self._cache_get(email)
        if cached:
            self._breadcrumb("verify_email.cache_hit", {"email": email})
            return cached

        await self._throttle()
        self._breadcrumb("verify_email.gateway_dispatch", {"email": email})

        dispatcher = self._get_dispatcher()
        resp = await dispatcher.invoke_tool(
            server="hermes-hunter",
            tool="verify_email",
            args={"email": email},
        )

        if not resp.get("ok"):
            logger.warning("hunter gateway dispatch failed: %s", resp.get("error"))
            return {
                "email": email,
                "status": "unknown",
                "score": 0,
                "cached": False,
                "error": resp.get("error", "gateway_unavailable"),
            }

        result = self._unwrap_gateway(resp)
        if not result:
            return {"email": email, "status": "unknown", "score": 0, "cached": False}

        result["cached"] = False
        if result.get("status") not in ("quota_exhausted", "no_api_key", "unknown"):
            self._cache_put(email, result, result)
        return result

    async def domain_search(self, domain: str, limit: int = 10) -> dict:
        """Find emails for company domain via hermes-hunter MCP."""
        dispatcher = self._get_dispatcher()
        resp = await dispatcher.invoke_tool(
            server="hermes-hunter",
            tool="domain_search",
            args={"domain": domain, "limit": limit},
        )
        if not resp.get("ok"):
            return {"domain": domain, "status": "error", "emails": [],
                    "error": resp.get("error", "gateway_unavailable")}
        return self._unwrap_gateway(resp) or {"domain": domain, "status": "unknown", "emails": []}

    async def email_count(self, domain: str) -> dict:
        """Quick count emails for domain via hermes-hunter MCP (no quota cost)."""
        dispatcher = self._get_dispatcher()
        resp = await dispatcher.invoke_tool(
            server="hermes-hunter",
            tool="email_count",
            args={"domain": domain},
        )
        if not resp.get("ok"):
            return {"domain": domain, "status": "error", "total": 0,
                    "error": resp.get("error", "gateway_unavailable")}
        return self._unwrap_gateway(resp) or {"domain": domain, "status": "unknown", "total": 0}

    async def check_account_usage(self) -> dict:
        """Return Hunter.io quota usage via hermes-hunter MCP."""
        dispatcher = self._get_dispatcher()
        resp = await dispatcher.invoke_tool(
            server="hermes-hunter",
            tool="check_account_usage",
            args={},
        )
        if not resp.get("ok"):
            return {"status": "error", "error": resp.get("error", "gateway_unavailable")}
        return self._unwrap_gateway(resp) or {"status": "unknown"}

    async def aclose(self) -> None:
        """No-op — R7 uses GatewayDispatcher (per-call httpx client, no persistent conn)."""
