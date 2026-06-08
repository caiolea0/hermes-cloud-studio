"""LinkedIn account type auto-detection.

Detects whether the authenticated account is free / premium / sales_navigator
by inspecting the LinkedIn DOM. Caches result to avoid hitting the page
on every session-check.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hermes.linkedin.account_detector")

CACHE_FILE = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / "data" / "linkedin_account_type.json"
CACHE_TTL_HOURS = 24


def read_cached() -> Optional[dict]:
    """Return cached account info if fresh; None if stale or missing."""
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        ts = datetime.fromisoformat(data["detected_at"])
        age = datetime.now(timezone.utc) - ts
        if age < timedelta(hours=CACHE_TTL_HOURS):
            data["_cache_age_hours"] = round(age.total_seconds() / 3600, 1)
            return data
    except Exception as e:
        logger.warning(f"read_cached: {e}")
    return None


def write_cache(account_type: str, evidence: list) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "account_type": account_type,
        "evidence": evidence,
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }
    CACHE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def detect_account_type(page) -> dict:
    """Visit /feed/ and inspect DOM for premium / sales_navigator markers.

    Returns: {"account_type": "free|premium|sales_navigator", "evidence": [...]}
    """
    evidence: list = []
    account_type = "free"

    # Navigate to feed (lightweight, doesn't burn quota like profile views)
    try:
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        await asyncio.sleep(2)
    except Exception as e:
        logger.warning(f"feed navigation failed: {e}")
        return {"account_type": "free", "evidence": [f"nav_error:{e}"]}

    # Check 1: Premium icon in top nav (gold "in" badge with premium tier)
    try:
        n = await page.locator("li-icon[type='premium-app-icon'], li-icon[type='premium-icon'], "
                              ".global-nav__premium-cta, [data-control-name*='premium_branding']").count()
        if n > 0:
            evidence.append("nav_premium_icon")
            account_type = "premium"
    except Exception:
        pass

    # Check 2: "Premium" badge on own profile sidebar (visible in user's screenshot)
    try:
        # Sidebar entity lockup shows "Premium" text/badge
        prem_text = await page.locator(
            ".pv-recent-activity-section-v2, "
            "aside [aria-label*='Premium'], "
            "div.entity-result__primary-subtitle:has-text('Premium')"
        ).count()
        if prem_text > 0:
            evidence.append("sidebar_premium_badge")
            account_type = "premium"
    except Exception:
        pass

    # Check 3: Quick test — visit /premium/my-premium/. If 200 OK with content
    # showing the subscription dashboard, premium. If redirected to upsell, free.
    try:
        await page.goto("https://www.linkedin.com/premium/my-premium/", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        cur_url = page.url
        # If LinkedIn redirected to /products/, /upsell/, or /premium-upsell/, it's free.
        # If stayed on /my-premium/, it's premium.
        if "/my-premium" in cur_url:
            # Check for active subscription header
            try:
                has_dashboard = await page.locator(
                    "h1:has-text('Premium'), [data-test-id='premium-dashboard'], "
                    "section[aria-label*='Sales Navigator']"
                ).count()
                if has_dashboard > 0:
                    evidence.append("my_premium_dashboard_visible")
                    account_type = "premium"
                # Specific check for Sales Navigator
                sn = await page.locator(
                    "*:has-text('Sales Navigator'), [data-control-name*='sales_navigator']"
                ).count()
                if sn > 0:
                    evidence.append("sales_navigator_detected")
                    account_type = "sales_navigator"
            except Exception:
                pass
        elif "/upsell" in cur_url or "/products" in cur_url:
            evidence.append(f"redirected_to_upsell:{cur_url[:80]}")
            # account_type stays "free"
    except Exception as e:
        evidence.append(f"premium_page_error:{str(e)[:80]}")

    # Check 4: visit own profile, look for "Premium" gold badge near the name
    try:
        await page.goto("https://www.linkedin.com/in/me/", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        # The gold "Premium" badge selectors
        prem_badge = await page.locator(
            ".pv-top-card__premium-badge, "
            "li-icon[type='linkedin-bug'][color='gold'], "
            "img[alt*='Premium'], "
            ".premium-icon, "
            "*:has-text('Premium account')"
        ).count()
        if prem_badge > 0:
            evidence.append("profile_premium_badge")
            account_type = "premium" if account_type == "free" else account_type
    except Exception:
        pass

    return {"account_type": account_type, "evidence": evidence}


async def detect_and_cache(config) -> dict:
    """High-level: launch stealth browser, detect, cache, close."""
    from .stealth import launch_stealth_browser, close_stealth_browser
    browser, context, page = await launch_stealth_browser(config)
    try:
        result = await detect_account_type(page)
        write_cache(result["account_type"], result["evidence"])
        return result
    finally:
        try:
            await close_stealth_browser(page)
        except Exception:
            pass
