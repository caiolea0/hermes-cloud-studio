"""LinkedIn Post Engager — reads posts, generates AI comments via Ollama, likes + comments.

Flow:
1. Search posts by keywords/hashtags
2. Extract full post content
3. Generate comment via Ollama (qwen2.5:7b on local PC via SSH tunnel)
4. Validate comment via Claude Code subprocess
5. Simulate reading (scroll + dwell)
6. Like the post
7. Post the comment
8. Record action in rate limiter
"""
import asyncio
import json
import logging
import os
import random
import subprocess
import time
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

import httpx

from .config import LinkedInConfig, DATA_DIR
from .human import (
    click_human, move_mouse_human, random_delay,
    scroll_human, simulate_page_reading, type_human,
)
from .limiter import RateLimiter
from .stealth import close_stealth_browser, launch_stealth_browser, save_session

logger = logging.getLogger("hermes.linkedin.engager")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


COMMENT_PROMPTS = {
    "professional": (
        "Você é um profissional de tecnologia brasileiro ativo no LinkedIn. "
        "Leia o post abaixo e escreva um comentário de 1 a 2 frases, profissional, "
        "que referencia algo ESPECÍFICO do conteúdo. Nunca use frases genéricas como "
        "'Ótimo post!' ou 'Concordo plenamente!'. Sem emojis. Responda APENAS com o comentário."
    ),
    "casual": (
        "Você é um profissional de tech brasileiro no LinkedIn. Leia o post e escreva "
        "um comentário curto (1-2 frases), descontraído mas respeitoso, referenciando algo "
        "concreto do texto. Pode usar no máximo 1 emoji se fizer sentido. APENAS o comentário."
    ),
    "technical": (
        "Você é um desenvolvedor/profissional técnico brasileiro no LinkedIn. Leia o post e "
        "adicione uma perspectiva técnica em 1-2 frases, referenciando detalhes específicos. "
        "Tom preciso e construtivo. Sem emojis. APENAS o comentário."
    ),
}


async def _generate_comment_ollama(post_text: str, tone: str = "professional") -> Optional[str]:
    """Generate comment via Ollama running on local PC."""
    system_prompt = COMMENT_PROMPTS.get(tone, COMMENT_PROMPTS["professional"])
    lang_hint = "pt-BR" if any(c in post_text for c in "ãçõáéíóúâêîôûàèìòù") else "en-US"

    full_prompt = (
        f"{system_prompt}\n\n"
        f"Idioma do post: {lang_hint}\n\n"
        f"Post:\n{post_text[:2000]}\n\n"
        "Comentário:"
    )

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {"temperature": 0.75, "top_p": 0.9, "num_predict": 120},
                },
                timeout=45,
            )
        data = r.json()
        comment = data.get("response", "").strip()
        # strip quotes if Ollama wrapped it
        if comment.startswith('"') and comment.endswith('"'):
            comment = comment[1:-1].strip()
        return comment if len(comment) > 10 else None
    except Exception as e:
        logger.warning(f"Ollama error: {e}")
        return None


def _validate_comment_claude(comment: str) -> Tuple[bool, str]:
    """Validate comment naturalness via Claude Code subprocess (no API cost)."""
    try:
        result = subprocess.run(
            [
                "claude", "-p",
                f"Analise se este comentário do LinkedIn parece escrito por um humano real "
                f"(não um bot). Responda EXATAMENTE com uma dessas duas opções:\n"
                f"APROVADO\nREJEITAR: <motivo em 5 palavras>\n\n"
                f"Comentário: {comment}",
            ],
            capture_output=True, text=True, timeout=30,
        )
        output = result.stdout.strip()
        approved = output.upper().startswith("APROVADO")
        return approved, output
    except Exception as e:
        logger.warning(f"Claude validation failed: {e} — skipping validation")
        return True, "validation_skipped"


async def _generate_validated_comment(
    post_text: str, tone: str = "professional", max_attempts: int = 3
) -> Optional[str]:
    """Generate comment and validate. Retry with refined prompt if rejected."""
    extra_hint = ""
    for attempt in range(max_attempts):
        comment = await _generate_comment_ollama(post_text + extra_hint, tone)
        if not comment:
            continue

        approved, reason = _validate_comment_claude(comment)
        if approved:
            return comment

        logger.info(f"Comment rejected (attempt {attempt+1}): {reason}")
        extra_hint = f"\n\nANTERIOR REJEITADO POR: {reason}. Seja mais natural e específico."
        await asyncio.sleep(1)

    logger.warning("Could not generate approved comment after max attempts")
    return None


async def _generate_validated_comment_with_meta(
    post_text: str, tone: str = "professional", max_attempts: int = 3
) -> dict:
    """Same as _generate_validated_comment but returns full metadata dict.

    Returns: {text, attempts, ollama_model, validation_score, validation_note}
    or {text: None, ...} if all attempts failed.
    """
    import os as _os
    model = _os.environ.get("OLLAMA_MODEL", "qwen3:8b")
    extra_hint = ""
    for attempt in range(max_attempts):
        comment = await _generate_comment_ollama(post_text + extra_hint, tone)
        if not comment:
            continue
        approved, reason = _validate_comment_claude(comment)
        # Crude score: 1.0 if APROVADO without caveats, 0.5 if approved with note, 0.0 if rejected
        score = 1.0 if approved and reason.upper().startswith("APROVADO") else (0.0 if not approved else 0.5)
        if approved:
            return {
                "text": comment,
                "attempts": attempt + 1,
                "ollama_model": model,
                "validation_score": score,
                "validation_note": reason,
            }
        extra_hint = f"\n\nANTERIOR REJEITADO POR: {reason}. Seja mais natural e específico."
        await asyncio.sleep(1)
    return {
        "text": None,
        "attempts": max_attempts,
        "ollama_model": model,
        "validation_score": 0.0,
        "validation_note": "all_attempts_rejected",
    }


class LinkedInEngager:
    """Engages LinkedIn posts: reads content, generates AI comment, likes + comments."""

    def __init__(self, config: Optional[LinkedInConfig] = None):
        self.config = config or LinkedInConfig()
        self.limiter = RateLimiter(self.config)
        self.browser = None
        self.context = None
        self.page = None
        self.engagements: List[Dict] = []
        self._log_callback: Optional[Callable] = None

    def set_log_callback(self, callback: Callable):
        self._log_callback = callback

    def _log(self, msg: str, phase: str = "info", **kwargs):
        logger.info(f"[{phase}] {msg}")
        if self._log_callback:
            self._log_callback(msg, phase=phase, **kwargs)

    async def start(self, campaign_config: dict) -> dict:
        """Main entry — run post engagement campaign.

        campaign_config keys:
            keywords: list[str]       — search terms / hashtags
            industries: list[str]     — filter hints (used in keyword expansion)
            do_like: bool             — like posts (default True)
            do_comment: bool          — post comment (default True)
            tone: str                 — professional | casual | technical
            max_posts: int            — max posts to engage (default 10)
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
                    "type": "linkedin_engager",
                    "posts": [], "liked": 0, "commented": 0,
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
                    "type": "linkedin_engager",
                    "posts": [], "liked": 0, "commented": 0,
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
        keywords = campaign_config.get("keywords", ["tecnologia", "recrutamento"])
        industries = campaign_config.get("industries", [])
        do_like = campaign_config.get("do_like", True)
        do_comment = campaign_config.get("do_comment", True)
        tone = campaign_config.get("tone", "professional")
        max_posts = campaign_config.get("max_posts", 10)

        self._log("Iniciando browser stealth para engajamento...", phase="starting")

        try:
            self.browser, self.context, self.page = await launch_stealth_browser(self.config)

            engine = getattr(self.page, "_engine_used", "unknown")
            self._log(f"Browser launched (engine: {engine})", phase="connecting")
            # auth check
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
            self._log("Sessão ativa — buscando posts...", phase="searching")

            effective_limit = self.limiter.get_effective_daily_limit("post_engagement")
            already_done = self._get_daily_engagements()
            remaining = max(0, effective_limit - already_done)
            actual_max = min(max_posts, remaining)

            if actual_max <= 0:
                self._log("Limite diário de engajamento atingido", phase="done", level="warn")
                return self._build_result()

            self._log(
                f"Limite hoje: {effective_limit} | Já feitos: {already_done} | Restantes: {remaining}",
                phase="planning",
            )

            # build expanded keyword list
            search_terms = _expand_keywords(keywords, industries)

            for term in search_terms:
                if len(self.engagements) >= actual_max:
                    break

                allowed, reason = self.limiter.can_perform("post_engagement")
                if not allowed:
                    self._log(f"Rate limit: {reason}", phase="monitoring", level="warn")
                    break

                self._log(f"Buscando posts: {term}", phase="searching")
                count = await self._search_and_engage(term, tone, do_like, do_comment, actual_max)
                self._log(f"Engajado em {count} posts de '{term}'", phase="visiting")

            await save_session(self.context, self.config)
            self._log(f"Concluído: {len(self.engagements)} posts engajados", phase="done")
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

    def _get_daily_engagements(self) -> int:
        """Count post_engagement actions in last 24h."""
        import sqlite3
        from .config import RATE_DB_PATH
        try:
            conn = sqlite3.connect(str(RATE_DB_PATH))
            cutoff = time.time() - 86400
            row = conn.execute(
                "SELECT COUNT(*) FROM rate_actions WHERE account=? AND action_type=? AND timestamp>?",
                (self.config.account_email or "default", "post_engagement", cutoff),
            ).fetchone()
            conn.close()
            return row[0] if row else 0
        except Exception:
            return 0

    async def _search_and_engage(
        self, term: str, tone: str, do_like: bool, do_comment: bool, max_total: int
    ) -> int:
        """Search for posts with term and engage them."""
        from urllib.parse import quote
        search_url = (
            f"https://www.linkedin.com/search/results/content/"
            f"?keywords={quote(term)}&origin=GLOBAL_SEARCH_HEADER&sortBy=%22date_posted%22"
        )

        await self.page.goto(search_url, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(2, 5))
        await simulate_page_reading(self.page, min_time=2, max_time=5)

        count = 0
        while len(self.engagements) < max_total:
            needs_break, break_dur = self.limiter.needs_break()
            if needs_break:
                self._log(f"Pausa de {break_dur/60:.1f} min...", phase="monitoring")
                await asyncio.sleep(break_dur)
                self.limiter.record_break()

            posts = await self._extract_posts()
            if not posts:
                break

            for post in posts:
                if len(self.engagements) >= max_total:
                    break

                allowed, reason = self.limiter.can_perform("post_engagement")
                if not allowed:
                    return count

                result = await self._engage_post(post, tone, do_like, do_comment)
                if result:
                    self.engagements.append(result)
                    self.limiter.record_action("post_engagement", post.get("post_url", ""))
                    count += 1

                    if count % 5 == 0:
                        self._log(f"Engajados {len(self.engagements)} posts...", phase="visiting")

                await random_delay(self.config.min_action_delay * 2, self.config.max_action_delay * 2)

            # next page
            has_next = await self._go_to_next_page()
            if not has_next:
                break
            await asyncio.sleep(random.uniform(2, 4))

        return count

    async def _extract_posts(self) -> List[dict]:
        """Extract post data from search results page."""
        posts = []
        try:
            # scroll to load posts
            for _ in range(4):
                await scroll_human(self.page, "down", random.randint(400, 800))
                await asyncio.sleep(random.uniform(0.8, 2.0))

            post_els = await self.page.query_selector_all(
                ".feed-shared-update-v2, .occludable-update"
            )

            for el in post_els[:15]:
                try:
                    # get post text
                    text_el = await el.query_selector(
                        ".feed-shared-text, .break-words, .feed-shared-update-v2__description"
                    )
                    text = (await text_el.inner_text()).strip() if text_el else ""
                    if len(text) < 30:
                        continue

                    # get post URL / URN for reference
                    urn = await el.get_attribute("data-urn") or ""
                    post_url = ""
                    if urn:
                        post_url = f"https://www.linkedin.com/feed/update/{urn}/"

                    # get author
                    author_el = await el.query_selector(
                        ".feed-shared-actor__name, .update-components-actor__name"
                    )
                    author = (await author_el.inner_text()).strip() if author_el else ""

                    # check if already liked (avoid double-liking)
                    like_btn = await el.query_selector(
                        'button[aria-label*="Like"], button[data-reaction-type]'
                    )
                    already_liked = False
                    if like_btn:
                        label = await like_btn.get_attribute("aria-label") or ""
                        already_liked = "Unlike" in label or "Remove" in label

                    posts.append({
                        "element": el,
                        "text": text,
                        "post_url": post_url,
                        "author": author,
                        "already_liked": already_liked,
                    })
                except Exception as ex:
                    logger.debug(f"Post extract error: {ex}")
                    continue

        except Exception as e:
            logger.warning(f"Extract posts error: {e}")

        return posts

    async def _engage_post(
        self, post: dict, tone: str, do_like: bool, do_comment: bool
    ) -> Optional[dict]:
        """Like and/or comment on a single post."""
        el = post["element"]
        text = post["text"]
        result = {
            "post_url": post["post_url"],
            "author": post["author"],
            "liked": False,
            "commented": False,
            "comment_text": "",
            "engaged_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            # scroll element into view + simulate reading
            await el.scroll_into_view_if_needed()
            await asyncio.sleep(random.uniform(0.5, 1.5))
            await simulate_page_reading(self.page, min_time=5, max_time=15)

            comment_text = None
            comment_meta = {}
            if do_comment:
                self._log("Gerando comentário via Ollama...", phase="generating")
                comment_meta = await _generate_validated_comment_with_meta(text, tone)
                comment_text = comment_meta.get("text")
                if not comment_text:
                    self._log("Comentário não aprovado — só curtindo", phase="visiting")
                    do_comment = False
                else:
                    # propagate metadata into result so frontend gets it
                    result["ollama_model"] = comment_meta.get("ollama_model")
                    result["validation_score"] = comment_meta.get("validation_score")
                    result["validation_note"] = comment_meta.get("validation_note")
                    result["generation_attempts"] = comment_meta.get("attempts", 1)

            # LIKE
            if do_like and not post.get("already_liked"):
                like_btn = await el.query_selector(
                    'button[aria-label*="Like"], button.reactions-react-button'
                )
                if like_btn:
                    await like_btn.scroll_into_view_if_needed()
                    await asyncio.sleep(random.uniform(0.5, 1.2))
                    await move_mouse_human(self.page, like_btn, speed=self.config.mouse_speed)
                    await like_btn.click()
                    await asyncio.sleep(random.uniform(0.8, 2.0))
                    result["liked"] = True
                    self._log("Post curtido", phase="visiting")

            # COMMENT
            if do_comment and comment_text:
                comment_btn = await el.query_selector(
                    'button[aria-label*="Comment"], button.comment-button'
                )
                if comment_btn:
                    await comment_btn.scroll_into_view_if_needed()
                    await asyncio.sleep(random.uniform(0.8, 1.5))
                    await move_mouse_human(self.page, comment_btn, speed=self.config.mouse_speed)
                    await comment_btn.click()
                    await asyncio.sleep(random.uniform(1.0, 2.5))

                    # find comment input
                    comment_input = await self.page.query_selector(
                        ".ql-editor[contenteditable='true'], .comments-comment-box__input"
                    )
                    if comment_input:
                        await comment_input.scroll_into_view_if_needed()
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                        await type_human(
                            self.page,
                            ".ql-editor[contenteditable='true'], .comments-comment-box__input",
                            comment_text,
                            speed=self.config.typing_speed,
                        )
                        await asyncio.sleep(random.uniform(1.0, 2.5))

                        # submit
                        submit_btn = await self.page.query_selector(
                            'button[class*="submit"], .comments-comment-box__submit-button'
                        )
                        if submit_btn:
                            await move_mouse_human(self.page, submit_btn, speed=self.config.mouse_speed)
                            await submit_btn.click()
                            await asyncio.sleep(random.uniform(1.5, 3.0))
                            result["commented"] = True
                            result["comment_text"] = comment_text
                            result["comment_tone"] = tone
                            # capture comment_id (LinkedIn data-id) for future edit/delete
                            comment_id = await self._extract_comment_id_after_post()
                            if comment_id:
                                result["comment_id"] = comment_id
                            self._log(f"Comentário postado: {comment_text[:50]}...", phase="visiting")

        except Exception as e:
            logger.warning(f"Engage post error: {e}")

        if result["liked"] or result["commented"]:
            return result
        return None

    async def _extract_comment_id_after_post(self) -> Optional[str]:
        """After submitting a comment, find the data-id of the comment we just posted.

        LinkedIn renders the new comment within ~1.5s. Strategy: wait, then look
        at the last article[data-id] in the comments list authored by the current
        user (use viewer's own name from session, fallback to last comment).
        """
        try:
            await asyncio.sleep(1.5)
            # Most reliable: find the last comment article with a data-id attribute
            comment_articles = await self.page.query_selector_all(
                "article.comments-comment-item[data-id], "
                "div.comments-comment-item[data-id], "
                "div[data-id*='comment']"
            )
            if comment_articles:
                last = comment_articles[-1]
                cid = await last.get_attribute("data-id")
                if cid:
                    return cid
        except Exception as e:
            logger.debug(f"comment_id extraction failed: {e}")
        return None

    # ─── Edit / Delete operations (called by hermes_api endpoints) ──────

    async def edit_comment(self, post_url: str, comment_id: str, new_text: str) -> dict:
        """Navigate to the post and edit our previously-posted comment."""
        result = {"ok": False, "post_url": post_url, "comment_id": comment_id}
        try:
            # Ensure browser is up
            if not self.page:
                from .stealth import launch_stealth_browser
                self.browser, self.context, self.page = await launch_stealth_browser(self.config)

            await self.page.goto(post_url, wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(2, 4))

            # Find comment by data-id
            comment_el = await self.page.query_selector(f"[data-id='{comment_id}']")
            if not comment_el:
                result["error"] = "Comment not found (may have been deleted or LinkedIn DOM changed)"
                return result

            await comment_el.scroll_into_view_if_needed()
            await asyncio.sleep(0.8)

            # Open menu "..."
            menu_btn = await comment_el.query_selector(
                "button[aria-label*='Actions for your comment'], "
                "button[aria-label*='Open control menu'], "
                "button.comments-comment-actions__trigger"
            )
            if not menu_btn:
                result["error"] = "Comment menu button not found"
                return result
            await menu_btn.click()
            await asyncio.sleep(random.uniform(0.6, 1.2))

            # Click Edit
            edit_btn = await self.page.query_selector(
                "div.artdeco-dropdown__content--is-open button:has-text('Edit'), "
                "div.artdeco-dropdown__content--is-open button:has-text('Editar')"
            )
            if not edit_btn:
                result["error"] = "Edit option not found (may be > edit window)"
                return result
            await edit_btn.click()
            await asyncio.sleep(random.uniform(0.8, 1.5))

            # Find the editable area (now inline within the comment)
            editor = await comment_el.query_selector(".ql-editor[contenteditable='true']")
            if not editor:
                editor = await self.page.query_selector(".ql-editor[contenteditable='true']")
            if not editor:
                result["error"] = "Editor not found"
                return result

            # Clear and type new text
            await editor.click()
            await self.page.keyboard.press("Control+A")
            await asyncio.sleep(0.3)
            await self.page.keyboard.press("Delete")
            await asyncio.sleep(0.5)
            await type_human(
                self.page, ".ql-editor[contenteditable='true']", new_text,
                speed=self.config.typing_speed,
            )
            await asyncio.sleep(random.uniform(0.8, 1.5))

            # Submit (Save)
            save_btn = await self.page.query_selector(
                "button.comments-comment-box__submit-button, "
                "button[aria-label*='Save']"
            )
            if save_btn:
                await save_btn.click()
                await asyncio.sleep(random.uniform(1.5, 3.0))
                result["ok"] = True
                result["new_text"] = new_text
                result["edited_at"] = datetime.now(timezone.utc).isoformat()
                self.limiter.record_action("comment_edit", detail=post_url)
            else:
                result["error"] = "Save button not found"

        except Exception as e:
            result["error"] = str(e)
            logger.warning(f"edit_comment failed: {e}")
        return result

    async def delete_comment(self, post_url: str, comment_id: str) -> dict:
        """Navigate to the post and delete our comment."""
        result = {"ok": False, "post_url": post_url, "comment_id": comment_id}
        try:
            if not self.page:
                from .stealth import launch_stealth_browser
                self.browser, self.context, self.page = await launch_stealth_browser(self.config)

            await self.page.goto(post_url, wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(2, 4))

            comment_el = await self.page.query_selector(f"[data-id='{comment_id}']")
            if not comment_el:
                result["error"] = "Comment not found"
                return result

            await comment_el.scroll_into_view_if_needed()
            await asyncio.sleep(0.8)

            menu_btn = await comment_el.query_selector(
                "button[aria-label*='Actions for your comment'], "
                "button[aria-label*='Open control menu'], "
                "button.comments-comment-actions__trigger"
            )
            if not menu_btn:
                result["error"] = "Comment menu button not found"
                return result
            await menu_btn.click()
            await asyncio.sleep(random.uniform(0.6, 1.2))

            del_btn = await self.page.query_selector(
                "div.artdeco-dropdown__content--is-open button:has-text('Delete'), "
                "div.artdeco-dropdown__content--is-open button:has-text('Excluir')"
            )
            if not del_btn:
                result["error"] = "Delete option not found"
                return result
            await del_btn.click()
            await asyncio.sleep(random.uniform(0.8, 1.5))

            # Confirm dialog
            confirm_btn = await self.page.query_selector(
                "button.artdeco-modal__confirm-dialog-btn--primary, "
                "div.artdeco-modal button:has-text('Delete'), "
                "div.artdeco-modal button:has-text('Excluir')"
            )
            if confirm_btn:
                await confirm_btn.click()
                await asyncio.sleep(random.uniform(1.5, 2.5))
                result["ok"] = True
                result["deleted_at"] = datetime.now(timezone.utc).isoformat()
                self.limiter.record_action("comment_delete", detail=post_url)
            else:
                # Some flows don't require confirmation
                result["ok"] = True
                result["deleted_at"] = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            result["error"] = str(e)
            logger.warning(f"delete_comment failed: {e}")
        return result

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

    def _build_result(self) -> dict:
        liked = sum(1 for e in self.engagements if e.get("liked"))
        commented = sum(1 for e in self.engagements if e.get("commented"))
        # Frontend expects {posts: [{post_url, text, author, engagement, liked_at,
        # comment_generated, comment_id, comment_tone, ollama_model, validation_score, ...}]}
        posts = []
        for e in self.engagements:
            posts.append({
                "post_url": e.get("post_url"),
                "text": e.get("post_text") or e.get("text") or "",
                "author": e.get("author"),  # could be string or dict
                "author_url": e.get("author_url"),
                "date_label": e.get("date_label"),
                "engagement": e.get("engagement") or {"likes": 0, "comments": 0},
                "liked": e.get("liked", False),
                "liked_at": e.get("liked_at") or (e.get("engaged_at", "")[:19] if e.get("liked") else None),
                "commented": e.get("commented", False),
                "comment_id": e.get("comment_id"),
                "comment_generated": e.get("comment_text"),
                "comment_tone": e.get("comment_tone"),
                "ollama_model": e.get("ollama_model"),
                "claude_validation_score": e.get("validation_score"),
                "claude_validation_note": e.get("validation_note"),
                "generation_attempts": e.get("generation_attempts", 1),
            })
        return {
            "type": "linkedin_engager",
            "liked": liked,
            "commented": commented,
            "posts": posts,
            "rate_limiter_stats": self.limiter.get_stats(),
        }

    async def _cleanup(self):
        if self.page:
            try:
                await close_stealth_browser(self.page)
            except Exception:
                pass

        if self.engagements:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            result_path = DATA_DIR / f"linkedin_engagements_{ts}.json"
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(self.engagements, f, ensure_ascii=False, indent=2)


def _expand_keywords(keywords: List[str], industries: List[str]) -> List[str]:
    """Expand keyword list with industry context for broader search."""
    terms = list(keywords)
    # add hashtag variants
    for kw in keywords[:3]:
        if not kw.startswith("#"):
            terms.append(f"#{kw.replace(' ', '')}")
    # add industry combos
    for ind in industries[:2]:
        for kw in keywords[:2]:
            terms.append(f"{kw} {ind}")
    return terms[:10]  # cap at 10 search terms
