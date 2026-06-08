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
import re
import sqlite3
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


# ─── parsing helpers (module-level for reuse) ───────────────────────────

def _parse_role_from_headline(headline: str) -> Optional[str]:
    """'Tech Recruiter @ Nubank | Hiring Eng' -> 'Tech Recruiter'."""
    if not headline:
        return None
    for sep in [" @ ", " | ", " - ", " – ", " at ", " na ", " no "]:
        if sep in headline:
            return headline.split(sep, 1)[0].strip()
    return headline.strip()


def _parse_mutual(text: str) -> int:
    """'12 mutual connections including...' -> 12.  '12 conexões em comum' -> 12."""
    if not text:
        return 0
    m = re.search(r"(\d+)\s*(mutual|comum|comuns|em\s+comum)", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"^\s*(\d+)\b", text)
    return int(m.group(1)) if m else 0


def _parse_degree(text: str) -> Optional[str]:
    """'2nd' / 'connection of 3rd degree' / '2º' -> '2nd'."""
    if not text:
        return None
    t = text.lower()
    if "1st" in t or "1°" in t or "1º" in t or "primeiro" in t:
        return "1st"
    if "2nd" in t or "2°" in t or "2º" in t or "segundo" in t:
        return "2nd"
    if "3rd" in t or "3°" in t or "3º" in t or "terceiro" in t:
        return "3rd"
    if "out" in t or "fora" in t:
        return "out"
    return None


def _parse_last_activity(text: str) -> Optional[str]:
    """'posted • 3 days ago' / 'há 3 dias' -> 'há 3 dias'."""
    if not text:
        return None
    t = text.strip().lower()
    # English: "X minutes ago", "X hours ago", "X days ago", "X weeks ago"
    m = re.search(r"(\d+)\s*(minute|hour|day|week|month|year)s?\s*ago", t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        labels = {"minute": "min", "hour": "h", "day": "dia", "week": "sem", "month": "mês", "year": "ano"}
        return f"há {n} {labels.get(unit, unit)}{'s' if n > 1 and unit in ('day','week','year') else ''}"
    # Portuguese: "há X dias"
    m = re.search(r"há\s+\d+\s+(min|h|dia|sem|mês|ano)", t)
    if m:
        return text.strip()
    return text.strip()[:30]


def _company_domain_guess(company_name: str) -> Optional[str]:
    """Best-effort guess of company website domain for clearbit logo."""
    if not company_name:
        return None
    n = company_name.lower().strip()
    # well-known BR mappings
    known = {
        "nubank": "nubank.com.br", "stone": "stone.co", "ifood": "ifood.com.br",
        "magazine luiza": "magazineluiza.com.br", "magalu": "magazineluiza.com.br",
        "itaú": "itau.com.br", "itau": "itau.com.br", "itaú unibanco": "itau.com.br",
        "xp inc": "xpi.com.br", "xp": "xpi.com.br",
        "mercado livre": "mercadolivre.com.br", "mercadolibre": "mercadolibre.com",
        "globo": "globo.com", "embraer": "embraer.com", "totvs": "totvs.com",
    }
    if n in known:
        return known[n]
    # naive fallback: company-name.com (lowercased, dehyphenated)
    slug = re.sub(r"[^a-z0-9]+", "", n)
    return f"{slug}.com" if slug else None


def _upsert_profile_cache(profile: dict, db_path: Optional[Path] = None) -> None:
    """Insert or update profile in linkedin_profiles cache table."""
    if not profile.get("profile_url"):
        return
    db = db_path or (Path.home() / ".hermes" / "data" / "command_center.db")
    if not db.parent.exists():
        return
    try:
        conn = sqlite3.connect(str(db), timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            INSERT INTO linkedin_profiles
              (profile_url, name, photo, headline, current_role, current_company,
               company_domain, location, bio, mutual_count, degree, top_skills,
               last_activity, first_seen_at, last_seen_at, visit_count, extraction_meta)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(profile_url) DO UPDATE SET
              name = excluded.name,
              photo = COALESCE(excluded.photo, linkedin_profiles.photo),
              headline = COALESCE(excluded.headline, linkedin_profiles.headline),
              current_role = COALESCE(excluded.current_role, linkedin_profiles.current_role),
              current_company = COALESCE(excluded.current_company, linkedin_profiles.current_company),
              company_domain = COALESCE(excluded.company_domain, linkedin_profiles.company_domain),
              location = COALESCE(excluded.location, linkedin_profiles.location),
              bio = COALESCE(excluded.bio, linkedin_profiles.bio),
              mutual_count = COALESCE(excluded.mutual_count, linkedin_profiles.mutual_count),
              degree = COALESCE(excluded.degree, linkedin_profiles.degree),
              top_skills = COALESCE(excluded.top_skills, linkedin_profiles.top_skills),
              last_activity = COALESCE(excluded.last_activity, linkedin_profiles.last_activity),
              last_seen_at = excluded.last_seen_at,
              visit_count = linkedin_profiles.visit_count + 1,
              extraction_meta = excluded.extraction_meta
        """, (
            profile.get("profile_url"),
            profile.get("name"),
            profile.get("photo"),
            profile.get("headline"),
            profile.get("current_role"),
            profile.get("current_company"),
            _company_domain_guess(profile.get("current_company")),
            profile.get("location"),
            profile.get("bio"),
            profile.get("mutual_count", 0),
            profile.get("degree"),
            json.dumps(profile.get("top_skills", []), ensure_ascii=False),
            profile.get("last_activity"),
            now, now,
            json.dumps(profile.get("extraction_meta", {}), ensure_ascii=False),
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"profile cache upsert failed: {e}")


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
                    "type": "linkedin_viewer",
                    "profiles_visited": 0, "profiles": [], "by_role": {}, "by_city": {},
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
                    f"LinkedIn em cooldown: {fmt_state(health)} — abortando para "
                    f"preservar a conta",
                    phase="cooldown",
                    detail=health,
                )
                return {
                    "type": "linkedin_viewer",
                    "profiles_visited": 0,
                    "profiles": [],
                    "by_role": {}, "by_city": {},
                    "_aborted_cooldown": True,
                    "cooldown_state": health,
                    "rate_limiter_stats": self.limiter.get_stats(),
                }
        except Exception as e:
            logger.warning(f"cooldown precheck failed (continuing): {e}")

        # Record this launch so the 30min spacing applies to the next one
        try:
            self.limiter.record_launch()
        except Exception:
            pass

        # Reset the "session" counter (each campaign launch = fresh session window).
        try:
            self.limiter.reset_session()
        except Exception as e:
            logger.warning(f"limiter.reset_session failed: {e}")
        self._log("Iniciando browser stealth...", phase="starting")

        try:
            self.browser, self.context, self.page = await launch_stealth_browser(self.config)
            engine = getattr(self.page, "_engine_used", "unknown")
            self._log(
                f"Browser launched com anti-deteccao ativa (engine: {engine})",
                phase="connecting",
                detail={"headless": self.config.headless, "proxy": bool(self.config.proxy_server),
                        "engine": engine}
            )

            await self._authenticate()

            # Pre-outreach human warm-up (v5): scroll feed → notifications → mynetwork → feed
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
            # Auto-mark cooldown if the error pattern signals LinkedIn throttling
            try:
                from .cooldown import mark_cooldown_from_error
                mark_cooldown_from_error(str(e))
            except Exception:
                pass
            self._log(f"Erro: {str(e)}", phase="error", level="error")
            raise
        finally:
            await self._cleanup()

    async def _authenticate(self):
        """Navigate to LinkedIn and verify/establish authentication.

        Strategy: hit homepage first so LinkedIn can issue bcookie/lidc/JSESSIONID
        based on our li_at. Then navigate to /feed/. Going straight to /feed/
        with only li_at can trigger redirect loops in some LinkedIn states.
        """
        self._log("Verificando autenticacao...", phase="authenticating")

        # Step 1: homepage — establish session cookies
        try:
            await self.page.goto("https://www.linkedin.com/", wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            self._log(f"Falha em www.linkedin.com: {str(e)[:200]}", phase="authenticating", level="warn")
            # Dump diagnostics
            try:
                cookies = await self.context.cookies("https://www.linkedin.com")
                names = sorted({c.get("name","") for c in cookies})
                self._log(f"Cookies pre-error: {names} (page url={self.page.url[:120]})",
                          phase="authenticating", level="warn")
                from pathlib import Path
                import time as _t
                dbg = Path("/home/hermes-gcp/.hermes/data/debug")
                dbg.mkdir(parents=True, exist_ok=True)
                ts = int(_t.time())
                try:
                    await self.page.screenshot(path=str(dbg / f"home_fail_{ts}.png"), full_page=True)
                except Exception:
                    pass
            except Exception:
                pass
            raise
        await asyncio.sleep(random.uniform(2, 4))
        self._log(f"Homepage carregada: {self.page.url[:100]}", phase="authenticating")

        # Step 2: /feed/ — should work now that session cookies are set
        try:
            await self.page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            self._log(f"Falha em /feed/: {str(e)[:200]} (homepage funcionou)",
                      phase="authenticating", level="warn")
            try:
                cookies = await self.context.cookies("https://www.linkedin.com")
                names = sorted({c.get("name","") for c in cookies})
                self._log(f"Cookies após homepage: {names}", phase="authenticating", level="warn")
            except Exception:
                pass
            raise
        await asyncio.sleep(random.uniform(2, 4))

        url = self.page.url
        if "/feed" in url:
            self._is_authenticated = True
            self._log("Sessao ativa — autenticado", phase="authenticating")
            await simulate_page_reading(self.page, min_time=3, max_time=6)
            return

        if "/login" in url or "/uas/login" in url or "checkpoint" in url:
            self._log(f"Sessao expirada — login necessario (url: {url[:200]})", phase="authenticating", level="warn")
            # Dump cookies + screenshot for forensics
            try:
                cookies = await self.context.cookies("https://www.linkedin.com")
                names = sorted({c.get("name","") for c in cookies})
                self._log(f"Cookies presentes na sessão: {names}", phase="authenticating", level="warn")
                from pathlib import Path
                import time as _t
                dbg = Path("/home/hermes-gcp/.hermes/data/debug")
                dbg.mkdir(parents=True, exist_ok=True)
                ts = int(_t.time())
                await self.page.screenshot(path=str(dbg / f"auth_fail_{ts}.png"), full_page=True)
            except Exception as _e:
                logger.warning(f"auth dump failed: {_e}")
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
        """Search LinkedIn for profiles and visit them.

        Path that survives 2026 bot detection:
        1) navigate to /search/results/all/ (the search-bar default — NOT people)
        2) wait for page to settle
        3) click the "People" filter chip in the results header to switch to
           /search/results/people/ via SWITCH_SEARCH_VERTICAL origin (looks like
           a real user clicking the tab; direct URL nav to /people/ → redirect loop)
        """
        # PATCH 2026-06-07: ir direto pra /search/results/people/ — LinkedIn redireciona
        # /all/ pra /jobs/ pra contas novas com pouco signal social.
        from urllib.parse import quote_plus
        people_url = f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(role + ' ' + location)}&origin=GLOBAL_SEARCH_HEADER"
        self._log(f"Navegando para people search direto: {role} {location}", phase="searching")

        try:
            await self.page.goto(people_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(random.uniform(2, 4))
            # Se redirecionou pra /jobs/, fallback pra /all/
            if "/people/" not in self.page.url:
                self._log(f"redirect inesperado: {self.page.url[:120]} — fallback /all/", phase="searching")
                search_url = self._build_search_url(role, location)
                await self.page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            # Last-resort: try driving the search via the top search box
            self._log(f"Search URL falhou ({type(e).__name__}) — tentando search box", phase="searching", level="warn")
            await self.page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(random.uniform(2, 4))
            try:
                box = await self.page.query_selector("input[role='combobox'][placeholder*='Pesquisar'], input.search-global-typeahead__input, input[aria-label*='Search']")
                if box:
                    await box.click()
                    await asyncio.sleep(random.uniform(0.4, 0.9))
                    await box.fill("")
                    await box.type(role, delay=random.randint(60, 140))
                    await asyncio.sleep(random.uniform(0.5, 1.0))
                    await self.page.keyboard.press("Enter")
                    await self.page.wait_for_load_state("domcontentloaded", timeout=20000)
                else:
                    raise
            except Exception as e2:
                self._log(f"Search box também falhou ({type(e2).__name__})", phase="searching", level="error")
                raise

        await asyncio.sleep(random.uniform(2, 4))

        # Click "People" filter chip to scope results to profiles
        if "/people/" not in self.page.url:
            self._log("Clicando filtro 'Pessoas' / 'People'", phase="searching")
            clicked = False
            for sel in [
                "button[aria-label*='Pessoas']",
                "button[aria-label*='People']",
                "a[href*='/search/results/people/']",
                "li.search-reusables__primary-filter button",
            ]:
                try:
                    el = await self.page.query_selector(sel)
                    if el:
                        await el.scroll_into_view_if_needed()
                        await asyncio.sleep(random.uniform(0.3, 0.8))
                        await el.click()
                        clicked = True
                        break
                except Exception:
                    continue
            if clicked:
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass
                await asyncio.sleep(random.uniform(2, 4))
            else:
                self._log(f"Filtro 'Pessoas' não encontrado — continuando com all-results (url={self.page.url[:120]})", phase="searching", level="warn")

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
        """Build LinkedIn search URL (the /all/ variant — same URL the search bar emits).

        We deliberately avoid /search/results/people/ — direct nav to that URL
        triggers ERR_TOO_MANY_REDIRECTS on flagged or lurking-phase sessions.
        The /all/ tab is what the global search bar produces when you press
        Enter, and it loads reliably. The People filter is then applied in
        _search_and_visit by clicking the in-page tab chip.
        """
        from urllib.parse import quote
        q = role
        if location and location.strip().lower() not in role.lower():
            q = f"{role} {location}".strip()
        keywords = quote(q)
        return f"https://www.linkedin.com/search/results/all/?keywords={keywords}&origin=GLOBAL_SEARCH_HEADER"

    async def _extract_profile_links(self) -> List[dict]:
        """Extract profile links from search results page.

        Tries multiple selectors — LinkedIn changes the DOM frequently and
        a single brittle selector returns 0 hits when the real page is full.
        """
        links = []
        try:
            # scroll to load all results
            for _ in range(3):
                await scroll_human(self.page, "down", random.randint(300, 600))
                await asyncio.sleep(random.uniform(0.5, 1.5))

            # Try multiple selectors in order of specificity (2026 LinkedIn DOM has shifted).
            SELECTORS = [
                '[data-chameleon-result-urn] a[href*="/in/"]',         # legacy 2024-25
                'div.search-results-container a[href*="/in/"]',         # mid-2025
                '.reusable-search__result-container a[href*="/in/"]',   # 2025 reusable component
                'ul[role="list"] li a.app-aware-link[href*="/in/"]',    # 2026 list-based
                '[data-test-app-aware-link][href*="/in/"]',             # data-attr fallback
                'a[href*="/in/"][data-test-app-aware-link]',            # ordering variant
            ]
            results = []
            selector_used = None
            for sel in SELECTORS:
                try:
                    found = await self.page.query_selector_all(sel)
                    if found:
                        results = found
                        selector_used = sel
                        break
                except Exception:
                    continue

            if not results:
                # Dump debug artifact for forensics (max 1 per campaign)
                if not getattr(self, "_debug_dumped", False):
                    try:
                        from pathlib import Path
                        import time as _t
                        dbg_dir = Path("/home/hermes-gcp/.hermes/data/debug")
                        dbg_dir.mkdir(parents=True, exist_ok=True)
                        ts = int(_t.time())
                        await self.page.screenshot(path=str(dbg_dir / f"search_empty_{ts}.png"), full_page=True)
                        html = await self.page.content()
                        (dbg_dir / f"search_empty_{ts}.html").write_text(html[:200000])
                        self._log(
                            f"DEBUG: search returned 0 — screenshot+html salvos em /data/debug/search_empty_{ts}.* (url={self.page.url[:120]})",
                            phase="searching", level="warn",
                        )
                        self._debug_dumped = True
                    except Exception as _e:
                        logger.warning(f"debug dump failed: {_e}")
            else:
                self._log(f"Selector ativo: {selector_used} -> {len(results)} candidatos", phase="searching")
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

            # extract profile data (rich schema)
            profile = await self._extract_profile_data()
            profile["url"] = url
            if not profile.get("profile_url"):
                profile["profile_url"] = url.split("?")[0].rstrip("/")
            profile["role_match"] = role
            profile["visited"] = True
            profile["visited_at"] = datetime.now(timezone.utc).isoformat()

            if not profile.get("name"):
                profile["name"] = link_data.get("name", "Unknown")

            # cache the rich profile so it's retrievable later by URL
            try:
                _upsert_profile_cache(profile)
            except Exception as e:
                logger.warning(f"profile upsert exception: {e}")

            return profile

        except Exception as e:
            logger.warning(f"Error visiting {url}: {e}")
            return None

    async def _extract_profile_data(self) -> dict:
        """Extract rich structured data from a LinkedIn profile page.

        Returns dict with full schema expected by the dashboard. Missing fields
        are None (UI degrades gracefully). Selectors are tried in order with
        fallbacks because LinkedIn frequently changes class names.
        """
        data: dict = {}
        hits: dict = {}  # which selectors succeeded — for debugging

        async def _q_text(selectors: list, attr: str = None) -> Optional[str]:
            """Try selectors in order, return inner_text() or attribute of first hit."""
            for sel in selectors:
                try:
                    el = await self.page.query_selector(sel)
                    if el:
                        if attr:
                            v = await el.get_attribute(attr)
                        else:
                            v = await el.inner_text()
                        if v and v.strip():
                            hits[sel] = True
                            return v.strip()
                except Exception:
                    continue
            return None

        # Name (h1)
        data["name"] = await _q_text([
            "h1.text-heading-xlarge",
            "h1.top-card-layout__title",
            "main h1",
        ])

        # Profile photo — multiple selector variants
        data["photo"] = await _q_text([
            "img.pv-top-card-profile-picture__image",
            "img.profile-photo-edit__preview",
            "button.pv-top-card-profile-picture__image-button img",
            ".pv-top-card-profile-picture img",
        ], attr="src")

        # Headline (the line right under the name)
        data["headline"] = await _q_text([
            ".text-body-medium.break-words",
            ".top-card-layout__headline",
            "div.pv-text-details__about-this-profile-entrypoint + div",
        ])

        # Location
        data["location"] = await _q_text([
            ".text-body-small.inline.t-black--light.break-words",
            ".pv-text-details__left-panel .text-body-small",
            ".top-card__subline-item",
        ])

        # Current company — try header button (most reliable in 2026 DOM)
        data["current_company"] = await _q_text([
            "button[aria-label*='Current company']",
            ".pv-text-details__right-panel button[aria-label*='current']",
            "section.pv-top-card .inline-show-more-text",
        ])

        # If still missing, fall back to first experience entry
        if not data["current_company"]:
            try:
                exp_section = await self.page.query_selector("#experience ~ .pvs-list__outer-container")
                if exp_section:
                    first_exp = await exp_section.query_selector(".pvs-entity--padded")
                    if first_exp:
                        for sel in ["span.t-bold span[aria-hidden='true']",
                                    ".t-bold span", "[data-field='experience_company_logo']"]:
                            el = await first_exp.query_selector(sel)
                            if el:
                                v = await el.inner_text()
                                if v and v.strip():
                                    data["current_company"] = v.strip()
                                    break
            except Exception:
                pass

        # Parse role from headline (everything before " @ " or " | " or "-")
        if data.get("headline"):
            data["current_role"] = _parse_role_from_headline(data["headline"])
        else:
            data["current_role"] = None

        # Bio / About section (first 300 chars)
        bio_text = await _q_text([
            "#about ~ .pvs-list__outer-container .inline-show-more-text",
            "div.display-flex.ph5.pv3 .inline-show-more-text",
            "section.summary p",
        ])
        data["bio"] = (bio_text[:300] if bio_text else None)

        # Mutual connections count (from top card link "X mutual connections")
        mutual_text = await _q_text([
            ".pv-top-card--list-bullet li",
            "a[href*='facetNetwork=F'] span",
            "section.pv-top-card span.t-bold",
        ])
        data["mutual_count"] = _parse_mutual(mutual_text) if mutual_text else 0

        # Degree (1st / 2nd / 3rd)
        degree_text = await _q_text([
            ".dist-value",
            "span.distance-badge",
            ".artdeco-entity-lockup__badge",
        ])
        data["degree"] = _parse_degree(degree_text) if degree_text else None

        # Top skills (up to 5)
        try:
            skills_locator = self.page.locator(
                "#skills ~ .pvs-list__outer-container .mr1.hoverable-link-text span[aria-hidden='true']"
            )
            count = await skills_locator.count()
            skills: list = []
            for i in range(min(count, 5)):
                try:
                    s = (await skills_locator.nth(i).inner_text()).strip()
                    if s and s not in skills:
                        skills.append(s)
                except Exception:
                    continue
            data["top_skills"] = skills
        except Exception:
            data["top_skills"] = []

        # Last activity (from "Activity" section header — "posted X days ago")
        activity_text = await _q_text([
            "#content_collections ~ div .pvs-list__outer-container li:first-child .feed-shared-actor__sub-description",
            "section.pv-recent-activity-section li:first-child time",
            ".pv-recent-activity-section-v2__title + div",
        ])
        data["last_activity"] = _parse_last_activity(activity_text) if activity_text else None

        # Total connections count (e.g., "500+ connections") — separate from mutual
        connections_text = await _q_text([
            "li.text-body-small span.t-bold",
            "ul.pv-top-card--list span.t-bold",
        ])
        data["connections_total"] = connections_text  # raw label

        # Canonical profile URL (strip tracking params)
        try:
            url = self.page.url
            data["profile_url"] = url.split("?")[0].rstrip("/")
        except Exception:
            pass

        data["extraction_meta"] = {"selectors_hit": list(hits.keys())}
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
            r = p.get("current_role") or p.get("role_match") or "unknown"
            by_role[r] = by_role.get(r, 0) + 1
            loc = p.get("location") or "Unknown"
            city = loc.split(",")[0].strip() if loc else "Unknown"
            by_city[city] = by_city.get(city, 0) + 1

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
