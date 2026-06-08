"""LinkedIn Company Finder — discovers recruiters/HR at target companies.

Flow:
1. Receive list of company names or LinkedIn company URLs
2. Navigate to company's People page on LinkedIn
3. Filter by HR / Recruiting department
4. Extract profile list (name, title, URL)
5. Save to linkedin_targets table
6. Optionally chain into viewer or connector
"""
import asyncio
import json
import logging
import os
import random
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.parse import quote

from .config import LinkedInConfig, DATA_DIR
from .human import (
    click_human, move_mouse_human, random_delay,
    scroll_human, simulate_page_reading,
)
from .limiter import RateLimiter
from .stealth import close_stealth_browser, launch_stealth_browser, save_session

logger = logging.getLogger("hermes.linkedin.company_finder")


async def hydrate_profile(profile_url: str, config: Optional[LinkedInConfig] = None,
                          max_age_days: int = 7) -> Optional[Dict]:
    """Fetch full profile data for a URL — cache hit returns immediately,
    cache miss does a single-page visit via stealth browser.

    Returns the profile dict (rich schema) or None on failure.
    """
    db = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / "data" / "command_center.db"
    canonical = profile_url.split("?")[0].rstrip("/")
    # Try cache first
    try:
        if db.exists():
            conn = sqlite3.connect(str(db), timeout=5)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM linkedin_profiles WHERE profile_url=?", (canonical,)
            ).fetchone()
            conn.close()
            if row:
                last_seen = row["last_seen_at"]
                age_ok = False
                try:
                    age_ok = (datetime.now(timezone.utc) - datetime.fromisoformat(last_seen.replace("Z","+00:00"))).days < max_age_days
                except Exception:
                    age_ok = False
                if age_ok:
                    return {
                        "profile_url": row["profile_url"],
                        "name": row["name"],
                        "photo": row["photo"],
                        "headline": row["headline"],
                        "current_role": row["current_role"],
                        "current_company": row["current_company"],
                        "company_domain": row["company_domain"],
                        "location": row["location"],
                        "bio": row["bio"],
                        "mutual_count": row["mutual_count"],
                        "degree": row["degree"],
                        "top_skills": json.loads(row["top_skills"]) if row["top_skills"] else [],
                        "last_activity": row["last_activity"],
                        "_from_cache": True,
                    }
    except Exception as e:
        logger.warning(f"hydrate_profile cache read failed: {e}")

    # Cache miss or stale — do a single live visit
    from .viewer import LinkedInViewer  # local import to avoid circular
    config = config or LinkedInConfig()
    viewer = LinkedInViewer(config)
    try:
        viewer.browser, viewer.context, viewer.page = await launch_stealth_browser(config)
        await viewer.page.goto(canonical, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(2, 4))
        data = await viewer._extract_profile_data()
        data["profile_url"] = canonical
        # cache it
        from .viewer import _upsert_profile_cache
        _upsert_profile_cache(data)
        data["_from_cache"] = False
        return data
    except Exception as e:
        logger.warning(f"hydrate_profile live fetch failed: {e}")
        return None
    finally:
        try:
            await close_stealth_browser(viewer.page)
        except Exception:
            pass

# LinkedIn function filters for People tab
HR_FUNCTIONS = ["Human Resources", "Recruiting"]
RECRUITER_TITLE_KEYWORDS = [
    "recruiter", "recrutador", "talent", "talento", "hr ", "rh ",
    "people", "pessoas", "acquisition", "captação", "headhunter",
    "sourcer", "hiring",
]


def _is_recruiter_title(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in RECRUITER_TITLE_KEYWORDS)


def _company_slug(company_input: str) -> Optional[str]:
    """Extract LinkedIn company slug from URL or name."""
    if "linkedin.com/company/" in company_input:
        parts = company_input.split("/company/")
        slug = parts[1].strip("/").split("/")[0].split("?")[0]
        return slug
    # treat as name — will be searched
    return None


class CompanyFinder:
    """Finds recruiters and HR professionals at target companies."""

    def __init__(self, config: Optional[LinkedInConfig] = None):
        self.config = config or LinkedInConfig()
        self.limiter = RateLimiter(self.config)
        self.browser = None
        self.context = None
        self.page = None
        self.found_profiles: List[Dict] = []
        self._log_callback: Optional[Callable] = None

    def set_log_callback(self, callback: Callable):
        self._log_callback = callback

    def _log(self, msg: str, phase: str = "info", **kwargs):
        logger.info(f"[{phase}] {msg}")
        if self._log_callback:
            self._log_callback(msg, phase=phase, **kwargs)

    async def start(self, campaign_config: dict) -> dict:
        """Main entry — run company discovery campaign.

        campaign_config keys:
            companies: list[str]      — company names or LinkedIn URLs
            scope: str                — "recruiters_only" | "hr_full" | "all_employees"
            post_action: str          — "save" | "view" | "connect"
            max_per_company: int      — max profiles per company (default 20)
        """
        # Reset session counter — fresh window per campaign
        try:
            self.limiter.reset_session()
        except Exception:
            pass
        # ── Pre-flight #1: launch cooldown (30 min mandatory spacing) ────────
        try:
            wait_s = self.limiter.time_until_next_launch()
            if wait_s > 0:
                wait_min = (wait_s + 59) // 60
                self._log(
                    f"Aguardando cooldown LinkedIn — proximo launch em {wait_min} min ({wait_s}s)",
                    phase="cooldown",
                )
                return {
                    "type": "linkedin_finder",
                    "found": 0, "by_company": {},
                    "_aborted_cooldown": True,
                    "cooldown_state": {
                        "state": "launch_cooldown",
                        "reason": "mandatory_spacing_30min",
                        "retry_after_seconds": wait_s,
                    },
                    "rate_limiter_stats": self.limiter.get_stats(),
                }
        except Exception as _e:
            logger.warning(f"launch cooldown check failed: {_e}")

        # ── Pre-flight: check LinkedIn health (cooldown / challenge) ──────────
        try:
            from .cooldown import check_health, fmt_state
            health = await check_health()
            if health.get("state") != "ok":
                self._log(
                    f"LinkedIn em cooldown: {fmt_state(health)} — abortando para preservar a conta",
                    phase="cooldown",
                    detail=health,
                )
                return {
                    "type": "linkedin_finder",
                    "found": 0, "by_company": {},
                    "_aborted_cooldown": True,
                    "cooldown_state": health,
                    "rate_limiter_stats": self.limiter.get_stats(),
                }
        except Exception as _e:
            logger.warning(f"cooldown precheck failed (continuing): {_e}")

        # Record this launch so the 30min spacing applies to the next one
        try:
            self.limiter.record_launch()
        except Exception:
            pass
        companies = campaign_config.get("companies", [])
        scope = campaign_config.get("scope", "recruiters_only")
        post_action = campaign_config.get("post_action", "save")
        max_per_company = campaign_config.get("max_per_company", 20)
        # Lite mode (default) extracts name + role + URL only — no photo/bio.
        # Lazy hydration happens via GET /api/linkedin/profiles/{url} on demand.
        # Set lite=False to do a full visit per profile (expensive — burns quota).
        self.lite_mode = campaign_config.get("lite", True)
        self._scope_cache = scope

        if not companies:
            return {"type": "linkedin_finder", "found": 0, "by_company": {}}

        self._log(f"Iniciando descoberta em {len(companies)} empresa(s)...", phase="starting")

        try:
            self.browser, self.context, self.page = await launch_stealth_browser(self.config)

            engine = getattr(self.page, "_engine_used", "unknown")
            self._log(f"Browser launched (engine: {engine})", phase="connecting")
            await self.page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(2, 4))
            if "/login" in self.page.url or "/uas/login" in self.page.url:
                raise RuntimeError("LinkedIn session expired. Re-authenticate first.")


            # ── v5 pre-outreach human warm-up ──────────────────────────
            if getattr(self.config, "pre_outreach_enabled", True):
                from .human import simulate_pre_outreach
                self._log(
                    f"Iniciando pré-aquecimento humano (~{self.config.pre_outreach_duration_seconds}s)",
                    phase="warming",
                )
                await simulate_pre_outreach(
                    self.page,
                    log_callback=lambda m: self._log(m, phase="warming"),
                    duration_seconds=self.config.pre_outreach_duration_seconds,
                    min_seconds=self.config.pre_outreach_min_seconds,
                )
            for company_input in companies:
                self._log(f"Processando empresa: {company_input}", phase="searching")

                slug = _company_slug(company_input)
                if slug:
                    profiles = await self._find_via_company_page(slug, scope, max_per_company)
                else:
                    profiles = await self._find_via_search(company_input, scope, max_per_company)

                self.found_profiles.extend(profiles)
                self._log(f"Encontrados {len(profiles)} perfis em '{company_input}'", phase="searching")

                await random_delay(5, 15)

            await save_session(self.context, self.config)

            # save to disk
            self._save_results()

            self._log(f"Concluído: {len(self.found_profiles)} perfis encontrados", phase="done")
            return self._build_result(post_action)

        except Exception as e:
            try:
                from .cooldown import mark_cooldown_from_error
                mark_cooldown_from_error(str(e))
            except Exception:
                pass
            self._log(f"Erro: {str(e)}", phase="error", level="error")
            raise
        finally:
            await self._cleanup()

    async def _find_via_company_page(
        self, slug: str, scope: str, max_count: int
    ) -> List[dict]:
        """Navigate to company People page and extract profiles."""
        profiles = []

        # build People tab URL with optional function filter
        if scope == "recruiters_only":
            # use search with function filter
            base_url = (
                f"https://www.linkedin.com/company/{slug}/people/"
                f"?facetCurrentFunction=12"  # function 12 = Human Resources
            )
        elif scope == "hr_full":
            base_url = f"https://www.linkedin.com/company/{slug}/people/?facetCurrentFunction=12"
        else:
            base_url = f"https://www.linkedin.com/company/{slug}/people/"

        await self.page.goto(base_url, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(3, 6))

        # check if company page loaded
        if "linkedin.com/company" not in self.page.url:
            self._log(f"Empresa '{slug}' não encontrada", phase="searching", level="warn")
            return []

        await simulate_page_reading(self.page, min_time=3, max_time=8)

        # scroll and collect profiles
        for scroll_round in range(5):
            if len(profiles) >= max_count:
                break

            await scroll_human(self.page, "down", random.randint(400, 700))
            await asyncio.sleep(random.uniform(1.0, 2.5))

            batch = await self._extract_people_cards(scope)
            for p in batch:
                if len(profiles) >= max_count:
                    break
                p["company_slug"] = slug
                if p["url"] not in {x["url"] for x in profiles}:
                    profiles.append(p)

        return profiles

    async def _find_via_search(
        self, company_name: str, scope: str, max_count: int
    ) -> List[dict]:
        """Search LinkedIn people filtering by company name."""
        profiles = []

        if scope in ("recruiters_only", "hr_full"):
            keywords = f'recruiter OR "talent acquisition" OR "RH" "{company_name}"'
        else:
            keywords = company_name

        url = (
            f"https://www.linkedin.com/search/results/people/"
            f"?keywords={quote(keywords)}&origin=GLOBAL_SEARCH_HEADER"
        )

        await self.page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(2, 5))
        await simulate_page_reading(self.page, min_time=2, max_time=5)

        # add company filter via URL if possible
        # try to get company ID by searching for the company
        company_id = await self._search_company_id(company_name)
        if company_id:
            url = (
                f"https://www.linkedin.com/search/results/people/"
                f"?currentCompany=%5B%22{company_id}%22%5D&origin=FACETED_SEARCH"
            )
            if scope in ("recruiters_only", "hr_full"):
                kw = quote('recruiter OR "talent acquisition" OR RH')
                url += f"&keywords={kw}"
            await self.page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(2, 5))

        for _ in range(3):
            if len(profiles) >= max_count:
                break

            batch = await self._extract_search_result_links(scope)
            for p in batch:
                if len(profiles) >= max_count:
                    break
                p["company_searched"] = company_name
                if p["url"] not in {x["url"] for x in profiles}:
                    profiles.append(p)

            has_next = await self._go_to_next_page()
            if not has_next:
                break
            await asyncio.sleep(random.uniform(2, 5))

        return profiles

    async def _extract_people_cards(self, scope: str) -> List[dict]:
        """Extract profile cards from company People tab."""
        profiles = []
        try:
            cards = await self.page.query_selector_all(
                ".org-people-profile-card__profile-info, "
                ".scaffold-finite-scroll__content .artdeco-entity-lockup"
            )
            for card in cards:
                try:
                    name_el = await card.query_selector(
                        ".artdeco-entity-lockup__title, .org-people-profile-card__profile-title"
                    )
                    name = (await name_el.inner_text()).strip() if name_el else ""

                    title_el = await card.query_selector(
                        ".artdeco-entity-lockup__subtitle, .org-people-profile-card__profile-position"
                    )
                    title = (await title_el.inner_text()).strip() if title_el else ""

                    link_el = await card.query_selector('a[href*="/in/"]')
                    href = await link_el.get_attribute("href") if link_el else ""
                    profile_path = href.split("?")[0] if href else ""
                    url = (
                        f"https://www.linkedin.com{profile_path}"
                        if profile_path.startswith("/") else profile_path
                    )

                    if not url or not name:
                        continue

                    # filter by title if recruiters_only
                    if scope == "recruiters_only" and not _is_recruiter_title(title):
                        continue

                    profiles.append({
                        "url": url,
                        "name": name,
                        "title": title,
                        "source": "company_page",
                        "found_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Extract people cards error: {e}")
        return profiles

    async def _extract_search_result_links(self, scope: str) -> List[dict]:
        """Extract profiles from search results page."""
        profiles = []
        try:
            for _ in range(3):
                await scroll_human(self.page, "down", random.randint(300, 600))
                await asyncio.sleep(random.uniform(0.5, 1.5))

            results = await self.page.query_selector_all('[data-chameleon-result-urn] a[href*="/in/"]')
            seen = set()
            for el in results:
                href = await el.get_attribute("href")
                if not href or "/in/" not in href:
                    continue
                profile_path = href.split("?")[0]
                if profile_path in seen:
                    continue
                seen.add(profile_path)

                name = ""
                try:
                    name_el = await el.query_selector("span[aria-hidden='true']")
                    if name_el:
                        name = (await name_el.inner_text()).strip()
                except Exception:
                    pass

                title = ""
                try:
                    parent = await el.evaluate_handle("el => el.closest('[data-chameleon-result-urn]')")
                    sub_el = await parent.query_selector(".entity-result__primary-subtitle")
                    if sub_el:
                        title = (await sub_el.inner_text()).strip()
                except Exception:
                    pass

                if scope == "recruiters_only" and title and not _is_recruiter_title(title):
                    continue

                url = (
                    f"https://www.linkedin.com{profile_path}"
                    if profile_path.startswith("/") else profile_path
                )
                profiles.append({
                    "url": url,
                    "name": name,
                    "title": title,
                    "source": "search",
                    "found_at": datetime.now(timezone.utc).isoformat(),
                })
        except Exception as e:
            logger.warning(f"Extract search links error: {e}")
        return profiles

    async def _search_company_id(self, company_name: str) -> Optional[str]:
        """Try to get LinkedIn company numeric ID from autocomplete."""
        try:
            url = (
                f"https://www.linkedin.com/search/results/companies/"
                f"?keywords={quote(company_name)}"
            )
            await self.page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(2, 4))

            # extract first company link to get ID
            link = await self.page.query_selector('a[href*="/company/"]')
            if link:
                href = await link.get_attribute("href")
                # try numeric ID from URL params
                if "?facetCurrentCompany" not in href:
                    # get company page and extract ID from page source
                    slug_part = href.split("/company/")[1].split("/")[0] if "/company/" in href else ""
                    if slug_part:
                        # LinkedIn company pages embed the numeric ID in data attributes
                        await self.page.goto(
                            f"https://www.linkedin.com/company/{slug_part}/",
                            wait_until="domcontentloaded"
                        )
                        await asyncio.sleep(random.uniform(1, 3))
                        # look for entityUrn in page
                        content = await self.page.content()
                        import re
                        match = re.search(r'"entityUrn":"urn:li:fs_normalized_company:(\d+)"', content)
                        if match:
                            return match.group(1)
        except Exception:
            pass
        return None

    async def _go_to_next_page(self) -> bool:
        try:
            next_btn = self.page.locator('button[aria-label="Next"]')
            if await next_btn.count() > 0 and await next_btn.is_enabled():
                await click_human(self.page, 'button[aria-label="Next"]', speed=self.config.mouse_speed)
                await asyncio.sleep(random.uniform(2, 5))
                return True
        except Exception:
            pass
        return False

    def _build_result(self, post_action: str) -> dict:
        # Frontend expects by_company = {company_name: [profile, profile, ...]}
        # Each profile minimally has: name, profile_url, current_role, photo (optional in lite mode)
        by_company: Dict[str, List[Dict]] = {}
        for p in self.found_profiles:
            key = (p.get("company_searched") or p.get("current_company")
                   or p.get("company") or p.get("company_slug") or "Outras")
            # Normalize each profile to the rich schema the frontend renders
            normalized = {
                "name": p.get("name"),
                "profile_url": p.get("profile_url") or p.get("url"),
                "current_role": p.get("current_role") or p.get("title"),
                "current_company": p.get("current_company") or key,
                "headline": p.get("headline") or p.get("title"),
                "photo": p.get("photo"),  # may be None in lite mode
                "location": p.get("location"),
                "degree": p.get("degree"),
            }
            by_company.setdefault(key, []).append(normalized)

        return {
            "type": "linkedin_finder",
            "found": len(self.found_profiles),
            "by_company": by_company,
            "post_action": post_action,
        }

    def _save_results(self):
        if self.found_profiles:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = DATA_DIR / f"linkedin_company_find_{ts}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.found_profiles, f, ensure_ascii=False, indent=2)

    async def _cleanup(self):
        if self.page:
            try:
                await close_stealth_browser(self.page)
            except Exception:
                pass
