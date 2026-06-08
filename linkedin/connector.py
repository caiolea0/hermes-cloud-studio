"""LinkedIn Connector — sends connection requests with optional AI-personalized notes.

Flow:
1. Receive list of profile URLs or search query
2. Visit each profile (reuses viewer logic)
3. Check if already connected / pending
4. Click Connect → optional "Add a note" with AI note (Ollama)
5. Record action in rate limiter
"""
import asyncio
import json
import logging
import os
import random
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .config import LinkedInConfig, DATA_DIR
from .engager import _generate_comment_ollama, _validate_comment_claude
from .human import (
    click_human, move_mouse_human, random_delay,
    scroll_human, simulate_page_reading, type_human,
)
from .limiter import RateLimiter
from .stealth import close_stealth_browser, launch_stealth_browser, save_session

logger = logging.getLogger("hermes.linkedin.connector")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")


def _db_path() -> Path:
    return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))) / "data" / "command_center.db"


def _record_connection(campaign_id, profile_url, note_sent, sent_at):
    """Insert a row into linkedin_connections."""
    try:
        conn = sqlite3.connect(str(_db_path()), timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            INSERT OR IGNORE INTO linkedin_connections
              (campaign_id, profile_url, status, note_sent, sent_at, status_updated_at, refresh_attempts)
            VALUES (?, ?, 'pending', ?, ?, ?, 0)
        """, (campaign_id, profile_url, note_sent, sent_at, sent_at))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"_record_connection failed: {e}")


async def refresh_connection_statuses(config: Optional[LinkedInConfig] = None, max_per_run: int = 30):
    """Periodic job: re-check pending connections by visiting each profile.

    Status detection:
      - Button "Pending" / "Pendente" visible -> still pending
      - Button "Message" / "Mensagem" visible -> accepted (now 1st connection)
      - Button "Connect" / "Conectar" visible -> rejected or withdrawn -> treat as ignored
      - If pending > 30 days -> ignored

    Updates linkedin_connections.status accordingly.
    """
    config = config or LinkedInConfig()
    db = _db_path()
    try:
        conn = sqlite3.connect(str(db), timeout=5)
        conn.row_factory = sqlite3.Row
        # Pending older than 30 days -> mark ignored without visiting
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        conn.execute("""
            UPDATE linkedin_connections SET status='ignored', status_updated_at=?
            WHERE status='pending' AND sent_at < ?
        """, (datetime.now(timezone.utc).isoformat(), cutoff))
        conn.commit()
        rows = conn.execute("""
            SELECT id, profile_url FROM linkedin_connections
            WHERE status='pending'
            ORDER BY refresh_attempts ASC, sent_at ASC
            LIMIT ?
        """, (max_per_run,)).fetchall()
        conn.close()
    except Exception as e:
        logger.error(f"refresh_connection_statuses: db read failed: {e}")
        return {"checked": 0, "updated": 0, "error": str(e)}

    if not rows:
        return {"checked": 0, "updated": 0}

    browser, context, page = await launch_stealth_browser(config)
    updated = 0
    try:
        for r in rows:
            try:
                await page.goto(r["profile_url"], wait_until="domcontentloaded")
                await asyncio.sleep(random.uniform(2, 4))
                new_status = await _detect_connection_status_on_profile(page)
                if new_status and new_status != "pending":
                    c2 = sqlite3.connect(str(db), timeout=5)
                    c2.execute("""
                        UPDATE linkedin_connections
                        SET status=?, status_updated_at=?, refresh_attempts=refresh_attempts+1
                        WHERE id=?
                    """, (new_status, datetime.now(timezone.utc).isoformat(), r["id"]))
                    c2.commit()
                    c2.close()
                    updated += 1
                else:
                    c2 = sqlite3.connect(str(db), timeout=5)
                    c2.execute("UPDATE linkedin_connections SET refresh_attempts=refresh_attempts+1 WHERE id=?", (r["id"],))
                    c2.commit()
                    c2.close()
            except Exception as e:
                logger.warning(f"refresh row {r['id']}: {e}")
                continue
    finally:
        try:
            await close_stealth_browser(page)
        except Exception:
            pass

    return {"checked": len(rows), "updated": updated}


async def _detect_connection_status_on_profile(page) -> Optional[str]:
    """Read the primary CTA button to infer connection state."""
    try:
        for sel, label in [
            ("button[aria-label*='Pending']", "pending"),
            ("button[aria-label*='Pendente']", "pending"),
            ("button[aria-label*='Message']", "accepted"),
            ("button[aria-label*='Mensagem']", "accepted"),
            ("button[aria-label*='Connect']", "ignored"),  # withdrawn/rejected -> ignored
            ("button[aria-label*='Conectar']", "ignored"),
        ]:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                return label
    except Exception:
        pass
    return None
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

CONNECTION_NOTE_PROMPT = (
    "Você é um profissional de tecnologia brasileiro buscando expandir sua rede. "
    "Escreva uma nota curta de conexão no LinkedIn (máx 280 caracteres) para enviar a {name}, "
    "que é {title} na empresa {company}. "
    "Seja direto, profissional e mencione algo relevante ao perfil deles. "
    "Sem emojis. Sem 'Olá {name},' no início. Comece direto com a proposta. "
    "Responda APENAS com o texto da nota."
)


async def _generate_connection_note(
    name: str, title: str, company: str, template: Optional[str] = None
) -> Optional[str]:
    """Generate personalized connection note via Ollama."""
    if template:
        # simple template substitution
        note = template.replace("{nome}", name).replace("{empresa}", company).replace("{titulo}", title)
        if len(note) <= 300:
            return note

    prompt = (
        CONNECTION_NOTE_PROMPT.format(name=name, title=title or "profissional", company=company or "empresa")
        + f"\n\nNome: {name}\nCargo: {title}\nEmpresa: {company}\n\nNota:"
    )

    import httpx
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.7, "top_p": 0.9, "num_predict": 80},
                },
                timeout=45,
            )
        note = r.json().get("response", "").strip()
        if note.startswith('"') and note.endswith('"'):
            note = note[1:-1].strip()
        # enforce 280 char limit
        if len(note) > 280:
            note = note[:277] + "..."
        return note if len(note) > 15 else None
    except Exception as e:
        logger.warning(f"Ollama note generation failed: {e}")
        return None


class LinkedInConnector:
    """Sends LinkedIn connection requests with optional AI-personalized notes."""

    def __init__(self, config: Optional[LinkedInConfig] = None):
        self.config = config or LinkedInConfig()
        self.limiter = RateLimiter(self.config)
        self.browser = None
        self.context = None
        self.page = None
        self.connections_sent: List[Dict] = []
        self._log_callback: Optional[Callable] = None
        self._campaign_id: Optional[int] = None

    def set_log_callback(self, callback: Callable):
        self._log_callback = callback

    def _log(self, msg: str, phase: str = "info", **kwargs):
        logger.info(f"[{phase}] {msg}")
        if self._log_callback:
            self._log_callback(msg, phase=phase, **kwargs)

    def set_campaign_id(self, campaign_id: int):
        """Stash the campaign id so each connection row is linked to it in DB."""
        self._campaign_id = campaign_id

    async def start(self, campaign_config: dict) -> dict:
        """Main entry — run connection campaign.

        campaign_config keys:
            mode: str              — "search" | "urls" | "visited"
            query: str             — search query (mode=search)
            profile_urls: list     — explicit URLs (mode=urls)
            location: str          — location filter for search
            send_note: bool        — send personalized note (default False)
            note_template: str     — optional template with {nome}/{empresa}/{titulo}
            max_connections: int   — max connections to send (default 15)
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
                    "type": "linkedin_connector",
                    "connections": [], "connections_sent": 0, "accepted": 0, "pending": 0, "rejected": 0, "ignored": 0,
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
                    "type": "linkedin_connector",
                    "connections": [], "connections_sent": 0, "accepted": 0, "pending": 0, "rejected": 0, "ignored": 0,
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
        mode = campaign_config.get("mode", "search")
        query = campaign_config.get("query", "recruiter")
        profile_urls = campaign_config.get("profile_urls", [])
        location = campaign_config.get("location", "Brazil")
        send_note = campaign_config.get("send_note", False)
        note_template = campaign_config.get("note_template", "")
        max_connections = campaign_config.get("max_connections", 15)

        self._log("Iniciando campanha de conexões...", phase="starting")

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
            # rate limit check
            effective_limit = self.limiter.get_effective_daily_limit("connection_request")
            already_sent = self.limiter.get_daily_connections()
            remaining = max(0, effective_limit - already_sent)
            actual_max = min(max_connections, remaining)

            if actual_max <= 0:
                self._log("Limite diário de conexões atingido", phase="done", level="warn")
                return self._build_result()

            self._log(
                f"Limite hoje: {effective_limit} | Enviadas: {already_sent} | Restantes: {remaining}",
                phase="planning",
            )

            if mode == "urls" and profile_urls:
                await self._connect_from_urls(profile_urls[:actual_max], send_note, note_template)
            elif mode == "search":
                await self._connect_from_search(query, location, actual_max, send_note, note_template)
            else:
                # "visited" mode — get recently visited profiles from DB
                visited_urls = self._get_recently_visited(actual_max)
                if visited_urls:
                    await self._connect_from_urls(visited_urls, send_note, note_template)
                else:
                    self._log("Nenhum perfil visitado recentemente encontrado", phase="done", level="warn")

            await save_session(self.context, self.config)
            self._log(f"Concluído: {len(self.connections_sent)} conexões enviadas", phase="done")
            return self._build_result()

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

    async def _connect_from_search(
        self, query: str, location: str, max_count: int, send_note: bool, note_template: str
    ):
        """Search for profiles and send connections."""
        from urllib.parse import quote
        keywords = quote(query)
        url = f"https://www.linkedin.com/search/results/people/?keywords={keywords}"
        if location.lower() == "brazil":
            url += "&geoUrn=%5B%22106057199%22%5D"

        await self.page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(2, 5))
        await simulate_page_reading(self.page, min_time=2, max_time=5)

        page_num = 1
        while len(self.connections_sent) < max_count:
            links = await self._extract_profile_links()
            if not links:
                break

            for link_data in links:
                if len(self.connections_sent) >= max_count:
                    break

                allowed, reason = self.limiter.can_perform("connection_request")
                if not allowed:
                    self._log(f"Rate limit: {reason}", phase="monitoring")
                    return

                needs_break, break_dur = self.limiter.needs_break()
                if needs_break:
                    self._log(f"Pausa de {break_dur/60:.1f} min...", phase="monitoring")
                    await asyncio.sleep(break_dur)
                    self.limiter.record_break()

                result = await self._visit_and_connect(link_data, send_note, note_template)
                if result:
                    self.connections_sent.append(result)
                    self.limiter.record_action("connection_request", result["url"])
                    self._log(f"Conexão enviada para {result['name']} ({len(self.connections_sent)}/{max_count})", phase="visiting")

                await random_delay(self.config.min_action_delay * 1.5, self.config.max_action_delay * 2)

            has_next = await self._go_to_next_page()
            if not has_next:
                break
            page_num += 1
            await asyncio.sleep(random.uniform(2, 5))

    async def _connect_from_urls(self, urls: List[str], send_note: bool, note_template: str):
        """Connect from explicit profile URL list."""
        for url in urls:
            allowed, reason = self.limiter.can_perform("connection_request")
            if not allowed:
                self._log(f"Rate limit: {reason}", phase="monitoring")
                break

            needs_break, break_dur = self.limiter.needs_break()
            if needs_break:
                self._log(f"Pausa de {break_dur/60:.1f} min...", phase="monitoring")
                await asyncio.sleep(break_dur)
                self.limiter.record_break()

            link_data = {"url": url, "name": "", "subtitle": ""}
            result = await self._visit_and_connect(link_data, send_note, note_template)
            if result:
                self.connections_sent.append(result)
                self.limiter.record_action("connection_request", url)
                self._log(f"Conexão enviada para {result['name']}", phase="visiting")

            await random_delay(self.config.min_action_delay * 2, self.config.max_action_delay * 2.5)

    async def _visit_and_connect(
        self, link_data: dict, send_note: bool, note_template: str
    ) -> Optional[dict]:
        """Visit a profile and send connection request."""
        url = link_data.get("url", "")
        if not url:
            return None

        try:
            await self.page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(1.5, 3))
            await simulate_page_reading(
                self.page,
                min_time=self.config.page_dwell_min,
                max_time=self.config.page_dwell_max,
                speed=self.config.mouse_speed,
            )

            # extract profile data
            name = await self._get_text("h1.text-heading-xlarge") or link_data.get("name", "")
            title = await self._get_text(".text-body-medium.break-words") or ""
            company = await self._get_company()
            connection_degree = await self._get_connection_degree()

            # skip if already 1st/2nd degree (already connected or mutual)
            if connection_degree in ("1st", "Following"):
                self._log(f"Já conectado com {name} — pulando", phase="visiting")
                return None

            # find Connect button
            connect_btn = await self._find_connect_button()
            if not connect_btn:
                self._log(f"Botão Connect não encontrado para {name}", phase="visiting")
                return None

            await connect_btn.scroll_into_view_if_needed()
            await asyncio.sleep(random.uniform(0.5, 1.5))
            await move_mouse_human(self.page, connect_btn, speed=self.config.mouse_speed)
            await connect_btn.click()
            await asyncio.sleep(random.uniform(1.0, 2.5))

            note_sent = ""
            if send_note:
                # look for "Add a note" button in the modal
                add_note_btn = await self.page.query_selector('button[aria-label="Add a note"]')
                if add_note_btn:
                    await add_note_btn.click()
                    await asyncio.sleep(random.uniform(0.8, 1.5))

                    note_text = await _generate_connection_note(name, title, company, note_template or None)
                    if note_text:
                        note_input = await self.page.query_selector('#custom-message')
                        if note_input:
                            await type_human(self.page, '#custom-message', note_text, speed=self.config.typing_speed)
                            await asyncio.sleep(random.uniform(1.0, 2.0))
                            note_sent = note_text
                            self._log(f"Nota personalizada adicionada para {name}", phase="visiting")

            # send
            send_btn = await self.page.query_selector('button[aria-label="Send now"]')
            if not send_btn:
                send_btn = await self.page.query_selector('button[aria-label="Send invitation"]')
            if send_btn:
                await move_mouse_human(self.page, send_btn, speed=self.config.mouse_speed)
                await send_btn.click()
                await asyncio.sleep(random.uniform(1.0, 2.5))
                sent_at = datetime.now(timezone.utc).isoformat()
                # Persist to linkedin_connections (status='pending' initially)
                _record_connection(
                    campaign_id=getattr(self, "_campaign_id", None),
                    profile_url=url.split("?")[0].rstrip("/"),
                    note_sent=note_sent,
                    sent_at=sent_at,
                )
                return {
                    "url": url,
                    "profile_url": url.split("?")[0].rstrip("/"),
                    "name": name,
                    "title": title,
                    "headline": title,
                    "current_company": company,
                    "company": company,
                    "status": "pending",
                    "note_sent": note_sent,
                    "sent_at": sent_at,
                }

            # dismiss modal if send failed
            cancel_btn = await self.page.query_selector('button[aria-label="Dismiss"]')
            if cancel_btn:
                await cancel_btn.click()

        except Exception as e:
            logger.warning(f"Connect error for {url}: {e}")

        return None

    async def _get_text(self, selector: str) -> str:
        try:
            el = await self.page.query_selector(selector)
            return (await el.inner_text()).strip() if el else ""
        except Exception:
            return ""

    async def _get_company(self) -> str:
        try:
            exp = await self.page.query_selector("#experience ~ .pvs-list__outer-container")
            if exp:
                first = await exp.query_selector(".pvs-entity--padded")
                if first:
                    comp_el = await first.query_selector("span.t-bold span[aria-hidden='true']")
                    if comp_el:
                        return (await comp_el.inner_text()).strip()
        except Exception:
            pass
        return ""

    async def _get_connection_degree(self) -> str:
        try:
            el = await self.page.query_selector(".dist-value")
            if el:
                return (await el.inner_text()).strip()
        except Exception:
            pass
        return ""

    async def _find_connect_button(self):
        """Find Connect button (handles both top-of-profile and More menu)."""
        # direct Connect button
        selectors = [
            'button[aria-label*="Connect"]',
            'button.pvs-profile-actions__action[aria-label*="Connect"]',
        ]
        for sel in selectors:
            try:
                btn = await self.page.query_selector(sel)
                if btn and await btn.is_visible():
                    return btn
            except Exception:
                pass

        # try More menu
        try:
            more_btn = await self.page.query_selector('button[aria-label="More actions"]')
            if more_btn:
                await more_btn.click()
                await asyncio.sleep(random.uniform(0.5, 1.2))
                connect_option = await self.page.query_selector(
                    'div[aria-label*="Connect"], span:has-text("Connect")'
                )
                if connect_option:
                    return connect_option
        except Exception:
            pass

        return None

    async def _extract_profile_links(self) -> List[dict]:
        """Extract profile links from search results."""
        links = []
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

                subtitle = ""
                try:
                    parent = await el.evaluate_handle("el => el.closest('[data-chameleon-result-urn]')")
                    sub_el = await parent.query_selector(".entity-result__primary-subtitle")
                    if sub_el:
                        subtitle = (await sub_el.inner_text()).strip()
                except Exception:
                    pass

                url = f"https://www.linkedin.com{profile_path}" if profile_path.startswith("/") else profile_path
                links.append({"url": url, "name": name, "subtitle": subtitle})
        except Exception as e:
            logger.warning(f"Extract links error: {e}")
        return links

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

    def _get_recently_visited(self, limit: int) -> List[str]:
        """Get recently visited profile URLs from rate_actions DB."""
        import sqlite3
        from .config import RATE_DB_PATH
        try:
            conn = sqlite3.connect(str(RATE_DB_PATH))
            cutoff = time.time() - 86400 * 3  # last 3 days
            rows = conn.execute(
                "SELECT detail FROM rate_actions WHERE account=? AND action_type='profile_view' "
                "AND timestamp>? ORDER BY timestamp DESC LIMIT ?",
                (self.config.account_email or "default", cutoff, limit),
            ).fetchall()
            conn.close()
            return [r[0] for r in rows if r[0] and r[0].startswith("http")]
        except Exception:
            return []

    def _build_result(self) -> dict:
        # Refresh status from linkedin_connections (in case some have flipped)
        connections_enriched = self._hydrate_statuses()
        accepted = sum(1 for c in connections_enriched if c.get("status") == "accepted")
        pending = sum(1 for c in connections_enriched if c.get("status") == "pending")
        rejected = sum(1 for c in connections_enriched if c.get("status") == "rejected")
        ignored = sum(1 for c in connections_enriched if c.get("status") == "ignored")
        return {
            "type": "linkedin_connector",
            "connections_sent": len(connections_enriched),
            "accepted": accepted,
            "pending": pending,
            "rejected": rejected,
            "ignored": ignored,
            "with_note": sum(1 for c in connections_enriched if c.get("note_sent")),
            "connections": connections_enriched,
            "rate_limiter_stats": self.limiter.get_stats(),
        }

    def _hydrate_statuses(self) -> List[Dict]:
        """Pull current status from linkedin_connections table for each sent."""
        if not self._campaign_id:
            return self.connections_sent
        try:
            conn = sqlite3.connect(str(_db_path()), timeout=5)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT profile_url, status FROM linkedin_connections WHERE campaign_id=?",
                (self._campaign_id,)
            ).fetchall()
            status_by_url = {r["profile_url"]: r["status"] for r in rows}
            conn.close()
            for c in self.connections_sent:
                pu = c.get("profile_url") or (c.get("url", "").split("?")[0].rstrip("/"))
                if pu in status_by_url:
                    c["status"] = status_by_url[pu]
            return self.connections_sent
        except Exception as e:
            logger.warning(f"_hydrate_statuses failed: {e}")
            return self.connections_sent

    async def _cleanup(self):
        if self.page:
            try:
                await close_stealth_browser(self.page)
            except Exception:
                pass

        if self.connections_sent:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = DATA_DIR / f"linkedin_connections_{ts}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.connections_sent, f, ensure_ascii=False, indent=2)
