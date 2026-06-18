"""hermes-hunter MCP — FastMCP 3.0 wrapper sobre Hunter.io v2.

R7 hardening — routes api.hunter.io calls via MCP gateway instead of
core/email_verifier.py direct httpx (BANNED-PATTERNS httpx loophole fix).

Tools (4):
  1. verify_email(email)           — email-verifier endpoint
  2. domain_search(domain, limit)  — domain-search endpoint
  3. email_count(domain)           — email-count endpoint (NO quota cost)
  4. check_account_usage()         — account endpoint (quota monitor)

API key: HUNTER_API_KEY env (canonical .env loaded at startup).
Rate limit: 15 req/min free tier.
Quota: 25 verifies/month free tier.

Run: python mcps/hunter/server.py  (cwd = repo root)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_env_canonical() -> None:
    """Load .env from canonical VM/PC locations (stdlib only — no python-dotenv dep)."""
    candidates = [
        Path.home() / ".hermes" / ".env",
        _REPO_ROOT / ".env",
    ]
    for p in candidates:
        if not p.exists():
            continue
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
            break
        except Exception:
            pass


_load_env_canonical()

try:
    from fastmcp import FastMCP
except ImportError as exc:
    raise SystemExit(
        "fastmcp not installed. R7 requires fastmcp>=3.0 on VM "
        "(pip install fastmcp>=3.0). Error: " + str(exc)
    )

import httpx  # noqa: E402 — allowed in mcps/ (MCP servers own external API calls)

MCP_NAME = "hermes-hunter"
MCP_VERSION = "0.1.0-r7"
_BASE_URL = "https://api.hunter.io/v2"
_RATE_LIMIT_PER_MIN = 15

mcp = FastMCP(MCP_NAME, version=MCP_VERSION)


def _api_key() -> str:
    return os.getenv("HUNTER_API_KEY", "")


@mcp.tool()
async def verify_email(email: str) -> dict:
    """Verify email deliverability via Hunter.io.

    Returns dict with status/score/smtp_check/mx_records/disposable/webmail.
    Status: 'valid' | 'invalid' | 'accept_all' | 'unknown' | 'quota_exhausted' | 'no_api_key'
    """
    key = _api_key()
    if not key:
        return {"email": email, "status": "no_api_key", "score": 0}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_BASE_URL}/email-verifier",
                params={"email": email, "api_key": key},
            )
    except httpx.HTTPError as exc:
        return {"email": email, "status": "unknown", "score": 0, "error": str(exc)}

    if resp.status_code == 401:
        return {"email": email, "status": "no_api_key", "score": 0}
    if resp.status_code == 429:
        return {"email": email, "status": "quota_exhausted", "score": 0}
    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = {"http_status": resp.status_code}
        err_id = (detail.get("errors") or [{}])[0].get("id")
        if err_id == "usage_exceeded":
            return {"email": email, "status": "quota_exhausted", "score": 0}
        return {"email": email, "status": "unknown", "score": 0, "error": detail}

    try:
        payload = resp.json()
    except Exception as exc:
        return {"email": email, "status": "unknown", "score": 0, "error": str(exc)}

    data = payload.get("data") or {}
    return {
        "email": email,
        "status": data.get("status", "unknown"),
        "score": data.get("score", 0),
        "smtp_check": bool(data.get("smtp_check")),
        "mx_records": bool(data.get("mx_records")),
        "disposable": bool(data.get("disposable")),
        "webmail": bool(data.get("webmail")),
    }


@mcp.tool()
async def domain_search(domain: str, limit: int = 10) -> dict:
    """Find emails associated with a company domain (prospect enrichment).

    Returns dict with status/emails/organization.
    """
    key = _api_key()
    if not key:
        return {"domain": domain, "status": "no_api_key", "emails": []}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_BASE_URL}/domain-search",
                params={"domain": domain, "api_key": key, "limit": limit},
            )
    except httpx.HTTPError as exc:
        return {"domain": domain, "status": "error", "emails": [], "error": str(exc)}

    if resp.status_code == 429:
        return {"domain": domain, "status": "quota_exhausted", "emails": []}
    if resp.status_code >= 400:
        return {"domain": domain, "status": "error", "emails": [], "http_status": resp.status_code}

    payload = resp.json()
    data = payload.get("data") or {}
    return {
        "domain": domain,
        "status": "ok",
        "organization": data.get("organization"),
        "emails": data.get("emails", []),
    }


@mcp.tool()
async def email_count(domain: str) -> dict:
    """Quick count of emails indexed for a domain (NO quota cost).

    Returns dict with status/domain/total.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_BASE_URL}/email-count",
                params={"domain": domain},
            )
    except httpx.HTTPError as exc:
        return {"domain": domain, "status": "error", "total": 0, "error": str(exc)}

    if resp.status_code >= 400:
        return {"domain": domain, "status": "error", "total": 0, "http_status": resp.status_code}

    payload = resp.json()
    data = payload.get("data") or {}
    return {"domain": domain, "status": "ok", "total": data.get("total", 0)}


@mcp.tool()
async def check_account_usage() -> dict:
    """Return Hunter.io quota usage for the configured API key.

    Returns dict with status/plan_name/calls_used/calls_available.
    """
    key = _api_key()
    if not key:
        return {"status": "no_api_key"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_BASE_URL}/account",
                params={"api_key": key},
            )
    except httpx.HTTPError as exc:
        return {"status": "error", "error": str(exc)}

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
    }


if __name__ == "__main__":
    mcp.run()
