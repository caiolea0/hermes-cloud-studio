"""F.7 P5 hardening — Hunter.io email verifier wrapper.

Task 6 (PLAN.md F.7) + MCP HARD REQ: validate email deliverability ANTES
warmup send. Risk: bounce rate >2% queima sender reputation cobaia domain.

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
from typing import Optional

import httpx

logger = logging.getLogger("hermes.email_verifier")

_HUNTER_BASE = "https://api.hunter.io/v2"
_CACHE_TTL_DAYS = 30
_RATE_LIMIT_PER_MIN = 15
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class EmailVerifier:
    """Hunter.io v2 client + SQLite cache + rate limit + Sentry breadcrumbs."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        db_path: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.api_key = api_key or os.getenv("HUNTER_API_KEY", "")
        self.db_path = db_path or os.getenv("HERMES_DB_PATH") or str(
            Path(__file__).resolve().parent.parent / "hermes_local.db"
        )
        self._client = http_client
        self._owns_client = http_client is None
        self._rate_window: list[float] = []
        self._rate_lock = asyncio.Lock()

    # ---------- internal ----------

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        return self._client

    async def aclose(self) -> None:
        if self._client and self._owns_client:
            await self._client.aclose()
            self._client = None

    def _breadcrumb(self, message: str, data: dict) -> None:
        from core.sentry_via_gateway import add_breadcrumb
        add_breadcrumb(category="hunter", message=message, data=data, level="info")

    async def _throttle(self) -> None:
        """Enforce 15 req/min sliding window (Hunter free tier)."""
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
        """Returns dict with status/score/checks.

        Status: 'valid' | 'invalid' | 'accept_all' | 'unknown' | 'quota_exhausted'
        | 'format_invalid' | 'no_api_key'

        cached: True if served from SQLite cache (no API call).
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

        if not self.api_key:
            logger.warning("hunter verify_email called without HUNTER_API_KEY")
            return {
                "email": email,
                "status": "no_api_key",
                "score": 0,
                "cached": False,
            }

        await self._throttle()
        client = await self._http()
        try:
            self._breadcrumb("verify_email.api_call", {"email": email})
            resp = await client.get(
                f"{_HUNTER_BASE}/email-verifier",
                params={"email": email, "api_key": self.api_key},
            )
        except httpx.HTTPError as e:
            logger.error("hunter http error: %s", e)
            return {
                "email": email,
                "status": "unknown",
                "score": 0,
                "cached": False,
                "error": str(e),
            }

        if resp.status_code == 401:
            return {"email": email, "status": "no_api_key", "score": 0, "cached": False}
        if resp.status_code == 429:
            return {"email": email, "status": "quota_exhausted", "score": 0, "cached": False}
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except Exception:
                detail = {"http_status": resp.status_code}
            err_id = (detail.get("errors") or [{}])[0].get("id")
            if err_id == "usage_exceeded":
                return {"email": email, "status": "quota_exhausted", "score": 0, "cached": False}
            return {
                "email": email,
                "status": "unknown",
                "score": 0,
                "cached": False,
                "error": detail,
            }

        try:
            payload = resp.json()
        except Exception as e:
            return {"email": email, "status": "unknown", "score": 0, "cached": False, "error": str(e)}

        data = payload.get("data") or {}
        result = {
            "email": email,
            "status": data.get("status", "unknown"),
            "score": data.get("score", 0),
            "smtp_check": bool(data.get("smtp_check")),
            "mx_records": bool(data.get("mx_records")),
            "disposable": bool(data.get("disposable")),
            "webmail": bool(data.get("webmail")),
            "cached": False,
            "verified_at": _iso(_now_utc()),
        }
        self._cache_put(email, result, payload)
        return result

    async def domain_search(self, domain: str, limit: int = 10) -> dict:
        """Find emails associated with company domain (prospect enrichment)."""
        if not self.api_key:
            return {"status": "no_api_key", "emails": []}
        await self._throttle()
        client = await self._http()
        try:
            resp = await client.get(
                f"{_HUNTER_BASE}/domain-search",
                params={"domain": domain, "api_key": self.api_key, "limit": limit},
            )
        except httpx.HTTPError as e:
            return {"status": "error", "emails": [], "error": str(e)}
        if resp.status_code == 429:
            return {"status": "quota_exhausted", "emails": []}
        if resp.status_code >= 400:
            return {"status": "error", "emails": [], "http_status": resp.status_code}
        payload = resp.json()
        data = payload.get("data") or {}
        return {
            "status": "ok",
            "domain": domain,
            "organization": data.get("organization"),
            "emails": data.get("emails", []),
        }

    async def email_count(self, domain: str) -> dict:
        """Quick check pre-search if domain has emails indexed (NO quota cost)."""
        client = await self._http()
        try:
            resp = await client.get(
                f"{_HUNTER_BASE}/email-count", params={"domain": domain}
            )
        except httpx.HTTPError as e:
            return {"status": "error", "count": 0, "error": str(e)}
        if resp.status_code >= 400:
            return {"status": "error", "count": 0, "http_status": resp.status_code}
        payload = resp.json()
        data = payload.get("data") or {}
        return {"status": "ok", "domain": domain, "total": data.get("total", 0)}

    async def check_account_usage(self) -> dict:
        """Returns {used, available, plan_name} — quota monitor."""
        if not self.api_key:
            return {"status": "no_api_key"}
        client = await self._http()
        try:
            resp = await client.get(
                f"{_HUNTER_BASE}/account", params={"api_key": self.api_key}
            )
        except httpx.HTTPError as e:
            return {"status": "error", "error": str(e)}
        if resp.status_code == 401:
            return {"status": "no_api_key"}
        if resp.status_code >= 400:
            return {"status": "error", "http_status": resp.status_code}
        payload = resp.json()
        data = payload.get("data") or {}
        calls = data.get("calls") or {}
        return {
            "status": "ok",
            "plan_name": data.get("plan_name", "free"),
            "calls_used": (calls.get("used") if isinstance(calls.get("used"), int)
                           else (calls.get("used") or {}).get("searches", 0)),
            "calls_available": (calls.get("available") if isinstance(calls.get("available"), int)
                                else (calls.get("available") or {}).get("searches", 0)),
            "raw": data,
        }
