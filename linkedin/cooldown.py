"""LinkedIn health probe + cooldown detector.

Strategy: do a lightweight authenticated GET to /feed/ via the SOCKS5 proxy
with the LI_AT cookie. The response code reveals state:

  - 200 / 302 -> ok (200 = logged in feed; 302 to /feed/ = same)
  - 302 to /login or /checkpoint -> challenge (cookie expired / verify needed)
  - 429 -> cooldown (rate-limited by IP/account)
  - 4xx (other) / 5xx / timeout -> blocked

State is cached on disk so all 4 pipelines + the API endpoints read the
same value. Avoids hammering LinkedIn during cooldown.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hermes.linkedin.cooldown")

CACHE_FILE = (
    Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
    / "data"
    / "linkedin_health.json"
)

# How long to trust a cached "ok" state before re-probing.
OK_CACHE_TTL_SECONDS = 300            # 5 min
# How long to enforce cooldown without probing (LinkedIn 429 typically lasts).
COOLDOWN_DEFAULT_SECONDS = 1800       # 30 min
COOLDOWN_MAX_SECONDS = 3600           # 60 min cap
CHALLENGE_CACHE_SECONDS = 600         # 10 min between challenge probes


def read_cached() -> Optional[dict]:
    """Return the last health state if still within its TTL, else None."""
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        ts = data.get("probed_at_ts", 0)
        state = data.get("state")
        age = time.time() - ts
        ttl = {
            "ok": OK_CACHE_TTL_SECONDS,
            "cooldown": data.get("retry_after_seconds", COOLDOWN_DEFAULT_SECONDS),
            "challenge": CHALLENGE_CACHE_SECONDS,
            "blocked": OK_CACHE_TTL_SECONDS,
        }.get(state, OK_CACHE_TTL_SECONDS)
        if age < ttl:
            data["_cache_age_seconds"] = round(age)
            data["_cache_remaining_seconds"] = round(ttl - age)
            return data
    except Exception as e:
        logger.warning(f"read_cached: {e}")
    return None


def write_cache(state: str, http_code: Optional[int] = None,
                reason: Optional[str] = None,
                retry_after_seconds: Optional[int] = None) -> dict:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "state": state,
        "http_code": http_code,
        "reason": reason,
        "retry_after_seconds": retry_after_seconds,
        "probed_at_ts": time.time(),
        "probed_at": datetime.now(timezone.utc).isoformat(),
    }
    if retry_after_seconds:
        payload["retry_at"] = (
            datetime.now(timezone.utc) + timedelta(seconds=retry_after_seconds)
        ).isoformat()
    try:
        CACHE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"write_cache failed: {e}")
    return payload


async def probe_linkedin() -> dict:
    """Single live probe to LinkedIn /feed/ — no caching. Returns same shape as cache."""
    import httpx
    li_at = os.environ.get("LI_AT", "").strip()
    proxy = os.environ.get("LINKEDIN_PROXY", "").strip() or None

    if not li_at:
        result = write_cache("challenge", reason="no_li_at_cookie")
        return result

    cookies = {"li_at": li_at}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }
    client_kwargs = dict(
        cookies=cookies, headers=headers,
        timeout=httpx.Timeout(15.0, connect=10.0),
        follow_redirects=False,
    )
    if proxy:
        # httpx >=0.28 uses `proxy=` (singular); <0.28 used `proxies=`
        try:
            client_kwargs["proxy"] = proxy
        except Exception:
            pass

    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            r = await client.get("https://www.linkedin.com/feed/")
    except httpx.TimeoutException:
        return write_cache("blocked", reason="timeout")
    except Exception as e:
        return write_cache("blocked", reason=f"network_error:{str(e)[:80]}")

    code = r.status_code
    if code == 200:
        return write_cache("ok", http_code=code)
    if code in (301, 302, 303, 307, 308):
        loc = r.headers.get("location", "").lower()
        req_path = str(r.request.url.path).lower()
        # Redirect-loop detection: LinkedIn redirecting /feed/ → /feed/ (or any
        # self-redirect) means our li_at is invalid — LinkedIn keeps trying to
        # re-auth us and fails. Chrome would crash with ERR_TOO_MANY_REDIRECTS.
        # The naive "feed in loc → ok" check missed this and falsely reported healthy.
        try:
            from urllib.parse import urlparse
            loc_path = urlparse(loc).path.lower() if loc.startswith("http") else loc.split("?")[0].lower()
        except Exception:
            loc_path = loc
        if loc_path and loc_path.rstrip("/") == req_path.rstrip("/"):
            return write_cache("challenge", http_code=code,
                              reason="expired_li_at_redirect_loop")
        if "checkpoint" in loc or "login" in loc or "challenge" in loc or "/uas/" in loc:
            return write_cache("challenge", http_code=code,
                              reason=f"redirected_to:{loc[:80]}")
        if "/hp" in loc_path:
            # /hp = LinkedIn's logged-out homepage. li_at not accepted.
            return write_cache("challenge", http_code=code,
                              reason="li_at_rejected_redirect_to_hp")
        if "feed" in loc and loc_path != req_path:
            return write_cache("ok", http_code=code, reason="redirect_to_feed")
        return write_cache("ok", http_code=code, reason=f"other_redirect:{loc[:80]}")
    if code == 429:
        retry_after = r.headers.get("retry-after")
        try:
            ra = int(retry_after) if retry_after else COOLDOWN_DEFAULT_SECONDS
        except ValueError:
            ra = COOLDOWN_DEFAULT_SECONDS
        ra = min(max(ra, 60), COOLDOWN_MAX_SECONDS)
        return write_cache("cooldown", http_code=code, reason="http_429",
                           retry_after_seconds=ra)
    if 500 <= code < 600:
        return write_cache("blocked", http_code=code, reason=f"server_{code}")
    if code in (401, 403):
        return write_cache("challenge", http_code=code, reason=f"http_{code}")
    return write_cache("blocked", http_code=code, reason=f"http_{code}")


async def check_health(force_refresh: bool = False) -> dict:
    """Public entry: returns cached health or probes if expired/forced."""
    if not force_refresh:
        cached = read_cached()
        if cached:
            return cached
    return await probe_linkedin()


def mark_cooldown_from_error(error_msg: str) -> dict:
    """Called from inside a pipeline when LinkedIn navigation fails with patterns
    indicative of cooldown. Forces a cooldown state in the cache so subsequent
    launches abort early."""
    em = (error_msg or "").lower()
    if "429" in em or "too many" in em:
        reason = "http_429_detected_in_run"
    elif "redirect" in em and ("login" in em or "challenge" in em or "checkpoint" in em):
        reason = "challenge_detected_in_run"
        return write_cache("challenge", reason=reason)
    elif "http_response_code_failure" in em or "err_http_response" in em:
        reason = "patchright_response_code_failure"
    elif "too_many_redirects" in em:
        reason = "too_many_redirects"
    else:
        reason = "generic_error"
    return write_cache(
        "cooldown",
        reason=reason,
        retry_after_seconds=COOLDOWN_DEFAULT_SECONDS,
    )


def fmt_state(payload: dict) -> str:
    """Pretty-format for log lines."""
    s = payload.get("state", "?")
    code = payload.get("http_code")
    r = payload.get("retry_after_seconds")
    if r:
        return f"{s} (HTTP {code}, retry em {r//60}min)"
    return f"{s} (HTTP {code})" if code else s
