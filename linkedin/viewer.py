"""LinkedIn Profile Viewer — visits profiles with full anti-detection.

Flow:
1. Launch stealth browser (Patchright preferred)
2. Authenticate (reuse session or manual login)
3. Search for profiles by role/location
4. Visit each profile with human-like behavior
5. Extract profile data
6. Respect rate limits + breaks
7. Save session + return results
"""
import asyncio
import json
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .config import LinkedInConfig, DATA_DIR
from .human import (
    click_human, move_mouse_human, random_delay,
    scroll_human, simulate_page_reading, type_human,
)
from .limiter import RateLimiter
from .stealth import close_stealth_browser, launch_stealth_browser, save_session

logger = logging.getLogger("hermes.linkedin.viewer")


class LinkedInViewer:
    """Visits LinkedIn profiles with stealth and human behavior simulation."""

    def __init__(self, config: Optional[LinkedInConfig] = None):
        self.config = config or LinkedInConfig()
        self.limiter = RateLimiter(self.config)
        self.browser = None
        self.context = None
        self.page = None
        self.profiles_visited: List[Dict] = []
        self._log_callback: Optional[Callable] = None
        self._is_authenticated = False

    def set_log_callback(self, callback: Callable):
        """Set callback for real-time log updates: callback(msg, phase, **kwargs)"""
        self._log_callback = callback

    def _log(self, msg: str, phase: str = "info", **kwargs):
        logger.info(f"[{phase}] {msg}")
        if self._log_callback:
            self._log_callback(msg, phase=phase, **kwargs)

    async def start(self) -> dict:
        """Main entry point — launch browser, authenticate, run the viewing pipeline.

        Returns structured result dict for dashboard display.
        """
        self._log("Iniciando browser stealth...", phase="starting")

        try:
            self.browser, self.context, self.page = await launch_stealth_browser(self.config)
            self._log("Browser launched com anti-deteccao ativa", phase="connecting",
                      detail={"headless": self.config.headless, "proxy": bool(self.config.proxy_server)})

            await self._authenticate()

            targets = self.config.__dict__.get("_targets", {})
            roles = targets.get("roles", ["tech recruiter", "project manager", "SMB owner"])
            location = targets.get("location", "Brazil")
            max_profiles = targets.get("max_profiles", 500)

            effective_limit = self.limiter.get_effective_daily_limit("profile_view")
            already_viewed = self.limiter.get_daily_views()
            remaining = max(0, effective_limit - already_viewed)
            actual_max = min(max_profiles, remaining)

            self._log(
                f"Limite hoje: {effective_limit} (warm-up: {self.limiter.get_warmup_multiplier():.0%}) | "
                f"Ja visitados: {already_viewed} | Restantes: {remaining}",
                phase="planning",
                detail={"effective_limit": effective_limit, "already_viewed": already_viewed}
            )

            if actual_max <= 0:
                self._log("Limite diario atingido — sem perfis para visitar", phase="done", level="warn")
                return self._build_result(roles)

            profiles_per_role = max(1, actual_max // len(roles))

            for role in roles:
                allowed, reason = self.limiter.can_perform("profile_view")
                if not allowed:
                    self._log(f"Rate limit: {reason}", phase="monitoring", level="warn")
                    break

                self._log(f"Buscando perfis: {role} em {location}...", phase="searching")
                found = await self._search_and_visit(role, location, profiles_per_role)
                self._log(f"Visitados {found} perfis de {role}", phase="visiting")

            await save_session(self.context, self.config)
            self._log(f"Concluido: {len(self.profiles_visited)} perfis visitados", phase="done")

            return self._build_result(roles)

        except Exception as e:
            self._log(f"Erro: {str(e)}", phase="error", level="error")
            raise
        finally:
            await self._cleanup()

    async def _authenticate(self):
        """Navigate to LinkedIn and verify/establish authentication."""
        self._log("Verificando autenticacao...", phase="authenticating")

        await self.page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(2, 4))

        url = self.page.url
        if "/feed" in url:
            self._is_authenticated = True
            self._log("Sessao ativa — autenticado", phase="authenticating")
            await simulate_page_reading(self.page, min_time=3, max_time=6)
            return

        if "/login" in url or "/uas/login" in url or "checkpoint" in url:
            self._log("Sessao expirada — login necessario", phase="authenticating", level="warn")
            await self._perform_login()
            return

        self._log(f"Pagina inesperada: {url}", phase="authenticating", level="warn")
        await self.page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        await self._perform_login()

    async def _perform_login(self):
        """Perform LinkedIn login with human-like behavior.

        NOTE: For security, credentials should be pre-stored in the session.
        This is a fallback — first run requires manual login or stored creds.
        """
        self._log("Aguardando login manual ou sessao salva...", phase="authenticating")

        email = self.config.account_email
        if not email:
            self._log("Sem credenciais — configure account_email", phase="error", level="error")
            raise RuntimeError("LinkedIn credentials not configured. Save a session file first.")

        # check if login form exists
        email_input = self.page.locator("#username")
        if await email_input.count() == 0:
            self._log("Formulario de login nao encontrado", phase="error", level="error")
            raise RuntimeError("Login form not found")

        await type_human(self.page, "#username", email, speed=self.config.typing_speed)
        await random_delay(0.5, 1.5)

        # password must be provided externally (env var or config)
        import os
        password = os.environ.get("LINKEDIN_PASSWORD", "")
        if not password:
            self._log("LINKEDIN_PASSWORD env var nao definida", phase="error", level="error")
            raise RuntimeError("Set LINKEDIN_PASSWORD environment variable")

        await type_human(self.page, "#password", password, speed=self.config.typing_speed)
        await random_delay(0.5, 2.0)

        await click_human(self.page, 'button[type="submit"]', speed=self.config.mouse_speed)
        await asyncio.sleep(random.uniform(3, 6))

        # check for CAPTCHA/checkpoint
        if "challenge" in self.page.url or "checkpoint" in self.page.url:
            self._log("CAPTCHA/verificacao detectada — intervencao manual necessaria", phase="authenticating", level="error")
            # wait up to 120s for manual resolution
            for _ in range(24):
                await asyncio.sleep(5)
                if "/feed" in self.page.url:
                    break
            else:
                raise RuntimeError("CAPTCHA not resolved within 120s")

        if "/feed" in self.page.url:
            self._is_authenticated = True
            self._log("Login realizado com sucesso", phase="authenticating")
            await save_session(self.context, self.config)
        else:
            raise RuntimeError(f"Login failed, ended up at: {self.page.url}")

    async def _search_and_visit(self, role: str, location: str, max_count: int) -> int:
        """Search LinkedIn for profiles and visit them."""
        search_url = self._build_search_url(role, location)
        self._log(f"Navegando para busca: {role}", phase="searching")

        await self.page.goto(search_url, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(2, 5))
        await simulate_page_reading(self.page, min_time=2, max_time=5, speed=self.config.mouse_speed)

        visited_count = 0
        page_num = 1

        while visited_count < max_count:
            allowed, reason = self.limiter.can_perform("profile_view")
            if not allowed:
                self._log(f"Rate limit atingido: {reason}", phase="monitoring")
                break

            # check for breaks
            needs_break, break_duration = self.limiter.needs_break()
            if needs_break:
                self._log(f"Pausa de {break_duration/60:.1f} min...", phase="monitoring")
                await asyncio.sleep(break_duration)
                self.limiter.record_break()
                self._log("Retomando apos pausa", phase="visiting")

            # extract profile links from search results
            links = await self._extract_profile_links()
            if not links:
                self._log(f"Sem mais resultados na pagina {page_num}", phase="searching")
                has_next = await self._go_to_next_page()
                if not has_next:
                    break
                page_num += 1
                continue

            for link_data in links:
                if visited_count >= max_count:
                    break

                allowed, reason = self.limiter.can_perform("profile_view")
                if not allowed:
                    break

                profile = await self._visit_profile(link_data, role)
                if profile:
                    self.profiles_visited.append(profile)
                    self.limiter.record_action("profile_view", profile.get("url", ""))
                    visited_count += 1

                    if visited_count % 10 == 0:
                        self._log(f"Visitados {visited_count}/{max_count} perfis de {role}...",
                                  phase="visiting", step=4, total=5)

                # human delay between profile visits
                await random_delay(self.config.min_action_delay, self.config.max_action_delay)

            # go to next search results page
            if visited_count < max_count:
                has_next = await self._go_to_next_page()
                if not has_next:
                    break
                page_num += 1
                await asyncio.sleep(random.uniform(2, 5))

        return visited_count

    def _build_search_url(self, role: str, location: str) -> str:
        """Build LinkedIn people search URL."""
        from urllib.parse import quote
        keywords = quote(role)
        url = f"https://www.linkedin.com/search/results/people/?keywords={keywords}&origin=GLOBAL_SEARCH_HEADER"
        if location:
            url += f"&geoUrn=%5B%22106057199%22%5D"  # Brazil geo URN
        return url

    async def _extract_profile_links(self) -> List[dict]:
        """Extract profile links from search results page."""
        links = []
        try:
            # scroll to load all results
            for _ in range(3):
                await scroll_human(self.page, "down", random.randint(300, 600))
                await asyncio.sleep(random.uniform(0.5, 1.5))

            results = await self.page.query_selector_all('[data-chameleon-result-urn] a[href*="/in/"]')
            seen = set()
            for el in results:
                href = await el.get_attribute("href")
                if not href or "/in/" not in href:
                    continue
                # normalize URL
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

                subtitle = ""
                try:
                    parent = await el.evaluate_handle("el => el.closest('[data-chameleon-result-urn]')")
                    sub_el = await parent.query_selector(".entity-result__primary-subtitle")
                    if sub_el:
                        subtitle = (await sub_el.inner_text()).strip()
                except Exception:
                    pass

                links.append({
                    "url": f"https://www.linkedin.com{profile_path}" if profile_path.startswith("/") else profile_path,
                    "name": name,
                    "subtitle": subtitle,
                })

        except Exception as e:
            logger.warning(f"Error extracting links: {e}")

        return links

    async def _visit_profile(self, link_data: dict, role: str) -> Optional[dict]:
        """Visit a single profile page and extract info."""
        url = link_data.get("url", "")
        if not url:
            return None

        try:
            await self.page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(1, 3))

            # simulate reading the profile
            await simulate_page_reading(
                self.page,
                min_time=self.config.page_dwell_min,
                max_time=self.config.page_dwell_max,
                speed=self.config.mouse_speed,
            )

            # extract profile data
            profile = await self._extract_profile_data()
            profile["url"] = url
            profile["role_match"] = role
            profile["visited"] = True
            profile["visited_at"] = datetime.now(timezone.utc).isoformat()

            if not profile.get("name"):
                profile["name"] = link_data.get("name", "Unknown")

            return profile

        except Exception as e:
            logger.warning(f"Error visiting {url}: {e}")
            return None

    async def _extract_profile_data(self) -> dict:
        """Extract structured data from a LinkedIn profile page."""
        data = {}

        try:
            name_el = await self.page.query_selector("h1.text-heading-xlarge")
            if name_el:
                data["name"] = (await name_el.inner_text()).strip()
        except Exception:
            pass

        try:
            title_el = await self.page.query_selector(".text-body-medium.break-words")
            if title_el:
                data["title"] = (await title_el.inner_text()).strip()
        except Exception:
            pass

        try:
            loc_el = await self.page.query_selector(".text-body-small.inline.t-black--light.break-words")
            if loc_el:
                data["city"] = (await loc_el.inner_text()).strip()
        except Exception:
            pass

        try:
            company = ""
            exp_section = await self.page.query_selector("#experience ~ .pvs-list__outer-container")
            if exp_section:
                first_exp = await exp_section.query_selector(".pvs-entity--padded")
                if first_exp:
                    comp_el = await first_exp.query_selector("span.t-bold span[aria-hidden='true']")
                    if comp_el:
                        company = (await comp_el.inner_text()).strip()
            data["company"] = company
        except Exception:
            pass

        try:
            connections_el = await self.page.query_selector("li.text-body-small span.t-bold")
            if connections_el:
                data["connections"] = (await connections_el.inner_text()).strip()
        except Exception:
            pass

        return data

    async def _go_to_next_page(self) -> bool:
        """Click next page in search results."""
        try:
            next_btn = self.page.locator('button[aria-label="Next"]')
            if await next_btn.count() > 0 and await next_btn.is_enabled():
                await click_human(self.page, 'button[aria-label="Next"]', speed=self.config.mouse_speed)
                await asyncio.sleep(random.uniform(2, 5))
                return True
        except Exception:
            pass
        return False

    def _build_result(self, roles: List[str]) -> dict:
        """Build structured result for dashboard."""
        by_role = {}
        by_city = {}
        for p in self.profiles_visited:
            r = p.get("role_match", "unknown")
            by_role[r] = by_role.get(r, 0) + 1
            c = p.get("city", "Unknown")
            by_city[c] = by_city.get(c, 0) + 1

        return {
            "type": "linkedin_viewer",
            "profiles_visited": len(self.profiles_visited),
            "profiles_found": len(self.profiles_visited),
            "by_role": by_role,
            "by_city": by_city,
            "profiles": self.profiles_visited,
            "rate_limiter_stats": self.limiter.get_stats(),
        }

    async def _cleanup(self):
        """Clean shutdown."""
        if self.page:
            try:
                await close_stealth_browser(self.page)
            except Exception:
                pass

        # save results to disk
        if self.profiles_visited:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            result_path = DATA_DIR / f"linkedin_results_{ts}.json"
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(self.profiles_visited, f, ensure_ascii=False, indent=2)
            self._log(f"Resultados salvos em {result_path}", phase="done")
