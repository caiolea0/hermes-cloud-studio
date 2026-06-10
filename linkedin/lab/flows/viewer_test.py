"""Flow: visita pequena de profile (lab cobaia).

Pre-requisito: login.py rodado antes (session valida).

Roteiro:
1. Reabre sessao do user_data_dir
2. Navega /feed/ + simulate_page_reading
3. Search bar -> termo
4. People filter
5. Click 1 resultado profile (selector resolvido)
6. Profile dwell via simulate_page_reading
7. Screenshot final
"""
from __future__ import annotations
import asyncio
import json
import random
from datetime import datetime
from pathlib import Path

from linkedin.lab._event_emit import emit


async def run(config, search_term: str = "designer", profile_index: int = 0) -> dict:
    from linkedin import stealth, human

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(__file__).parent.parent / "artifacts" / "viewer_test" / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    result: dict = {
        "timestamp": timestamp,
        "out_dir": str(out_dir),
        "search_term": search_term,
        "detection_signals": [],
    }

    _, browser_context, page = await stealth.launch_stealth_browser(config)
    profile = getattr(page, "_account_profile", None)
    await browser_context.tracing.start(screenshots=True, snapshots=True, sources=True)

    try:
        # 1. Feed warm-up
        print("[lab/viewer] /feed/...")
        emit("step_progress", step="navigate_feed", status="started")
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
        if _is_authwall(page.url):
            result["detection_signals"].append(f"authwall_at_feed:{page.url}")
            print(f"[lab/viewer] !! AUTHWALL no feed: {page.url}")
            emit("step_progress", step="navigate_feed", status="failed", message="authwall_detected")
            if profile:
                profile.check_and_burn(page.url)
            return result

        await human.random_delay(2.5, 4.5)
        await human.scroll_human(page, direction="down", amount=random.randint(400, 900))
        await human.simulate_page_reading(page, min_time=6.0, max_time=12.0)
        feed_path = str(out_dir / "01_feed.png")
        await page.screenshot(path=feed_path)
        emit("screenshot_captured", filename=feed_path, step="navigate_feed")
        emit("step_progress", step="navigate_feed", status="success")

        # 2. Search
        print(f"[lab/viewer] search '{search_term}'...")
        emit("step_progress", step="search", status="started", message=f"term={search_term}")
        search_selector = 'input[placeholder*="Search" i], input[placeholder*="Pesquisar" i]'
        try:
            await page.locator(search_selector).first.wait_for(state="visible", timeout=10000)
            await human.type_human(page, search_selector, search_term)
            await human.random_delay(0.4, 1.0)
            await page.keyboard.press("Enter")
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            await human.random_delay(2.5, 4.0)
            emit("step_progress", step="search", status="success")
        except Exception as e:
            result["detection_signals"].append(f"search_failed:{type(e).__name__}")
            print(f"[lab/viewer]   search falhou: {e}")
            emit("step_progress", step="search", status="failed", message=str(e)[:200])

        # 3. Click filter People (best effort)
        emit("step_progress", step="filter_people", status="started")
        try:
            people_selector = 'button:has-text("People"), button:has-text("Pessoas")'
            if await page.locator(people_selector).first.is_visible(timeout=3000):
                await human.click_human(page, people_selector)
                await human.random_delay(1.5, 3.0)
            emit("step_progress", step="filter_people", status="success")
        except Exception:
            emit("step_progress", step="filter_people", status="success", message="best_effort_skipped")

        search_results_path = str(out_dir / "02_search_results.png")
        await page.screenshot(path=search_results_path)
        emit("screenshot_captured", filename=search_results_path, step="search_results")

        # 4. Resolve profile #profile_index -> URL e navega
        emit("step_progress", step="resolve_profile", status="started")
        try:
            profile_links = page.locator('a[href*="/in/"]')
            count = await profile_links.count()
            if count == 0:
                result["detection_signals"].append("no_profiles_found")
                print("[lab/viewer]   nenhum profile encontrado")
                emit("step_progress", step="resolve_profile", status="failed", message="no_profiles_found")
                return result
            idx = min(profile_index, count - 1)
            target_url = await profile_links.nth(idx).get_attribute("href")
            result["target_profile"] = target_url
            print(f"[lab/viewer] visiting profile #{idx}: {target_url}")
            emit("step_progress", step="resolve_profile", status="success", message=f"idx={idx}")
            emit("step_progress", step="navigate_profile", status="started")
            # Click via JS-resolved selector (humano com selector unico)
            unique_sel = f'a[href="{target_url}"]'
            try:
                await human.click_human(page, unique_sel)
            except Exception:
                # fallback: navega direto
                full = target_url if target_url.startswith("http") else f"https://www.linkedin.com{target_url}"
                await page.goto(full, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_load_state("domcontentloaded", timeout=20000)
            await human.random_delay(2.0, 4.0)
            emit("step_progress", step="navigate_profile", status="success")
        except Exception as e:
            result["detection_signals"].append(f"profile_click_failed:{type(e).__name__}:{e}")
            emit("step_progress", step="navigate_profile", status="failed", message=str(e)[:200])
            return result

        # 5. Profile dwell
        if _is_authwall(page.url):
            result["detection_signals"].append(f"authwall_at_profile:{page.url}")
            print(f"[lab/viewer] !! AUTHWALL no profile: {page.url}")
            emit("step_progress", step="profile_dwell", status="failed", message="authwall_detected")
            if profile:
                profile.check_and_burn(page.url)
            return result

        print("[lab/viewer] dwell 12-25s...")
        emit("step_progress", step="profile_dwell", status="started")
        await human.scroll_human(page, direction="down", amount=random.randint(600, 1400))
        await human.simulate_page_reading(page, min_time=12.0, max_time=25.0)
        profile_path = str(out_dir / "03_profile.png")
        await page.screenshot(path=profile_path, full_page=True)
        emit("screenshot_captured", filename=profile_path, step="profile_dwell")
        emit("step_progress", step="profile_dwell", status="success")

        result["success"] = True
        result["final_url"] = page.url

    finally:
        trace_path = out_dir / "trace.zip"
        try:
            await browser_context.tracing.stop(path=str(trace_path))
            result["trace_path"] = str(trace_path)
        except Exception as e:
            result["trace_error"] = str(e)
        try:
            await browser_context.close()
        except Exception:
            pass

        (out_dir / "result.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(f"[lab/viewer] DONE. detection_signals={result['detection_signals']}")
        print(f"[lab/viewer] artifacts em {out_dir}")

    return result


def _is_authwall(url: str) -> bool:
    bad = ("/authwall", "/checkpoint", "/uas/login", "session-expired")
    return any(b in url for b in bad)
