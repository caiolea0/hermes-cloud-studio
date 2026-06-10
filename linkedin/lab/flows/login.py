"""Flow: login manual headful no LinkedIn (lab account).

Primeira execucao:
- Abre browser Patchright headful
- Navega pra linkedin.com/login
- Preenche email/senha SOZINHO via type_human (lento, humano)
- Espera 2FA / email verify se aparecer (usuario completa manualmente)
- Apos login, navega pra /feed/, captura li_at do cookie
- Salva user_data_dir + session_file pra reuso

Execucoes seguintes:
- Patchright detecta is_fresh_profile=False
- Reusa user_data_dir → ja logado
- Apenas valida /feed/ acessivel
"""
from __future__ import annotations
import asyncio
import json
from datetime import datetime
from pathlib import Path

from linkedin.lab._event_emit import emit


async def run(config, manual_password: bool = False) -> dict:
    """Login flow no LinkedIn.

    Args:
        config: LinkedInConfig com account_email + password (via os.environ).
        manual_password: True = pausa pra usuario digitar senha; False = autopreenche.

    Returns:
        dict {logged_in, li_at_present, redirect_chain, fingerprint_post_login}
    """
    import os
    from linkedin import stealth, human

    email = config.account_email
    password = os.environ.get("LINKEDIN_LAB_PASSWORD", "")
    if not email:
        raise ValueError("config.account_email vazio")
    if not password and not manual_password:
        raise ValueError("LINKEDIN_LAB_PASSWORD vazio no env (ou use manual_password=True)")

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(__file__).parent.parent / "artifacts" / "login" / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    result: dict = {
        "timestamp": timestamp,
        "out_dir": str(out_dir),
        "email": email,
        "redirect_chain": [],
    }

    _, browser_context, page = await stealth.launch_stealth_browser(config)
    profile = getattr(page, "_account_profile", None)
    try:
        # Detecta se ja logado: navega direto pra /feed/, se nao redirecionar -> ok
        print("[lab/login] Tentando /feed/ direto (caso ja logado em sessao anterior)...")
        emit("step_progress", step="check_session_reuse", status="started")
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        url_now = page.url
        result["redirect_chain"].append(url_now)
        print(f"[lab/login]   URL pos /feed/: {url_now}")

        if "/feed" in url_now and "/login" not in url_now and "/checkpoint" not in url_now:
            print("[lab/login] JA LOGADO. Capturando li_at e exit.")
            result["logged_in"] = True
            result["path"] = "session_reuse"
            emit("step_progress", step="check_session_reuse", status="success", message="already_logged_in")
        else:
            print("[lab/login] Nao logado. Fazendo login fresh...")
            emit("step_progress", step="check_session_reuse", status="success", message="needs_fresh_login")
            emit("step_progress", step="navigate_login_page", status="started")
            await page.goto("https://www.linkedin.com/uas/login", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            # Debug screenshot pre-login pra inspecionar layout LinkedIn
            login_screenshot = str(out_dir / "00_login_page.png")
            await page.screenshot(path=login_screenshot, full_page=False)
            emit("screenshot_captured", filename=login_screenshot, step="navigate_login_page")
            (out_dir / "00_login_url.txt").write_text(page.url, encoding="utf-8")

            # SDUI 2026: LinkedIn re-renderizou login com React IDs randomicos.
            # Targeting estavel agora via type + autocomplete (testado em milgrauz.exe 2026-06-07).
            USERNAME_SELECTORS = [
                'input[type="email"][autocomplete*="username"]:visible',
                'input[type="email"][autocomplete*="username"]',
                'input[autocomplete*="username"]',
                'input#username',
                'input[name="session_key"]',
                'input[type="email"]',
            ]
            PASSWORD_SELECTORS = [
                'input[type="password"][autocomplete="current-password"]:visible',
                'input[type="password"][autocomplete="current-password"]',
                'input[autocomplete="current-password"]',
                'input#password',
                'input[name="session_password"]',
                'input[type="password"]',
            ]
            SUBMIT_SELECTORS = [
                'button[type="submit"]:visible',
                'button[type="submit"]',
                'button:has-text("Entrar")',
                'button:has-text("Sign in")',
                'button[aria-label*="Entrar"]',
                'button[aria-label*="Sign in"]',
            ]

            async def first_visible(selectors, timeout_each=4000):
                for sel in selectors:
                    try:
                        loc = page.locator(sel).first
                        await loc.wait_for(state="visible", timeout=timeout_each)
                        return sel
                    except Exception:
                        continue
                return None

            # SDUI demora pra renderizar — primeiro selector ganha timeout maior
            user_sel = await first_visible(USERNAME_SELECTORS, timeout_each=6000)
            if not user_sel:
                result["error"] = "username field NOT FOUND — saving page snapshot"
                await page.screenshot(path=str(out_dir / "00_no_username.png"), full_page=True)
                (out_dir / "00_page.html").write_text(await page.content(), encoding="utf-8")
                result["page_url"] = page.url
                print(f"[lab/login] FAIL username selector. URL={page.url} HTML salvo.")
                return result

            print(f"[lab/login] username selector: {user_sel}")
            emit("step_progress", step="navigate_login_page", status="success", message="form_visible")
            emit("step_progress", step="type_username", status="started")
            await human.type_human(page, user_sel, email)
            await human.random_delay(0.5, 1.5)
            emit("step_progress", step="type_username", status="success")

            # Type password
            if manual_password:
                print("[lab/login] >>> DIGITE A SENHA MANUALMENTE NO BROWSER E PRESSIONE Enter <<<")
                print("[lab/login] (60s timeout)")
                emit("step_progress", step="manual_password_wait", status="started")
                try:
                    await page.wait_for_url(lambda u: "/login" not in u and "/uas/login" not in u, timeout=60000)
                    emit("step_progress", step="manual_password_wait", status="success")
                except Exception:
                    emit("step_progress", step="manual_password_wait", status="failed", message="timeout_60s")
            else:
                emit("step_progress", step="type_password", status="started")
                pw_sel = await first_visible(PASSWORD_SELECTORS, timeout_each=3000)
                if not pw_sel:
                    result["error"] = "password field NOT FOUND"
                    no_pw_path = str(out_dir / "00_no_password.png")
                    await page.screenshot(path=no_pw_path, full_page=True)
                    emit("screenshot_captured", filename=no_pw_path, step="type_password")
                    print(f"[lab/login] FAIL password selector")
                    emit("step_progress", step="type_password", status="failed", message="selector_not_found")
                    return result
                print(f"[lab/login] password selector: {pw_sel}")
                await human.type_human(page, pw_sel, password)
                await human.random_delay(0.5, 1.5)
                emit("step_progress", step="type_password", status="success")
                # Submit
                emit("step_progress", step="submit_login", status="started")
                submit_sel = await first_visible(SUBMIT_SELECTORS, timeout_each=2000)
                if submit_sel:
                    print(f"[lab/login] submit selector: {submit_sel}")
                    await human.click_human(page, submit_sel)
                    emit("step_progress", step="submit_login", status="success", message="button_click")
                else:
                    # Fallback: Enter no campo de senha
                    print("[lab/login] sem submit button visivel — Enter no password")
                    await page.keyboard.press("Enter")
                    emit("step_progress", step="submit_login", status="success", message="enter_fallback")

            # Aguarda redirecionamento
            print("[lab/login] Aguardando redirect pos-login (ate 90s)...")
            emit("step_progress", step="wait_redirect", status="started")
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
            await asyncio.sleep(5)
            url_after = page.url
            result["redirect_chain"].append(url_after)
            print(f"[lab/login]   URL pos-submit: {url_after}")

            emit("step_progress", step="wait_redirect", status="success", message=url_after)

            if "/checkpoint" in url_after or "challenge" in url_after:
                if profile:
                    profile.record_challenge()
                print("[lab/login] !! CHALLENGE detectado. Esperando 180s usuario resolver manualmente...")
                emit("step_progress", step="challenge_resolve", status="started", message="awaiting_manual_180s")
                try:
                    await page.wait_for_url(lambda u: "/checkpoint" not in u and "challenge" not in u, timeout=180000)
                    print("[lab/login]   Challenge resolvido.")
                    emit("step_progress", step="challenge_resolve", status="success")
                except Exception:
                    print("[lab/login]   Timeout 180s. Verificar manualmente.")
                    emit("step_progress", step="challenge_resolve", status="failed", message="timeout_180s")
                await asyncio.sleep(3)
                result["redirect_chain"].append(page.url)

            result["logged_in"] = "/feed" in page.url and "/login" not in page.url
            result["path"] = "fresh_login"
            if profile and result["logged_in"]:
                profile.record_login()

        # Captura cookies
        cookies = await browser_context.cookies("https://www.linkedin.com")
        li_at = next((c for c in cookies if c["name"] == "li_at"), None)
        result["li_at_present"] = li_at is not None
        result["cookies_count"] = len(cookies)
        result["cookies_names"] = [c["name"] for c in cookies]
        if li_at:
            result["li_at_expires"] = li_at.get("expires")
            print(f"[lab/login] li_at capturado, expires={li_at.get('expires')}")

        # Salva cookies em session_file
        if config.session_file:
            session_data = {"cookies": cookies}
            Path(config.session_file).parent.mkdir(parents=True, exist_ok=True)
            Path(config.session_file).write_text(json.dumps(session_data, indent=2, default=str), encoding="utf-8")
            print(f"[lab/login] Session salva em {config.session_file}")

        # Screenshot final
        post_login_path = str(out_dir / "post_login.png")
        await page.screenshot(path=post_login_path, full_page=True)
        emit("screenshot_captured", filename=post_login_path, step="post_login")

        # Save result
        (out_dir / "result.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(f"[lab/login] DONE. logged_in={result.get('logged_in')} li_at={result.get('li_at_present')}")

    finally:
        try:
            await browser_context.close()
        except Exception:
            pass

    return result
