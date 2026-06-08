"""Stealth browser launcher — full anti-detection setup.

Priority stack (best to worst):
1. Patchright with channel="chrome" (fixes Runtime.enable + TLS fingerprint)
2. Playwright with stealth patches (JS-level, less robust)
3. Fallback error if neither available

Detection vectors addressed:
- navigator.webdriver flag
- Runtime.enable CDP leak (Patchright)
- TLS/JA3/JA4 fingerprint (system Chrome)
- WebGL/Canvas/AudioContext fingerprinting
- navigator.plugins/languages/platform
- window.chrome object
- Automation command-line flags
- Timezone/locale/geolocation consistency
"""
import json
import logging
import os
import random
import shutil
from pathlib import Path
from typing import Optional

from .config import LinkedInConfig


def _detect_chrome_path() -> Optional[str]:
    """Find Google Chrome stable binary on the host.
    Returns absolute path, or None if not installed.
    """
    # 1. shutil.which (respects PATH)
    for name in ("google-chrome-stable", "google-chrome", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    # 2. Common hardcoded paths per OS
    candidates = [
        "/usr/bin/google-chrome-stable",
        "/usr/bin/google-chrome",
        "/opt/google/chrome/google-chrome",
        "/opt/google/chrome/chrome",
        # user-local install (no-sudo extraction) — typical Hermes VM setup
        os.path.expanduser("~/.local/bin/google-chrome-stable"),
        os.path.expanduser("~/.local/bin/google-chrome"),
        os.path.expanduser("~/chrome-extract/opt/google/chrome/google-chrome"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return None

logger = logging.getLogger("hermes.linkedin.stealth")

# JS patches injected into every page context
_STEALTH_SCRIPTS = [
    # 1. navigator.webdriver = false
    """Object.defineProperty(navigator, 'webdriver', {get: () => false});""",

    # 2. window.chrome stub completo (PATCH-013 — corrigido conforme 3 lentes).
    # Diferencas vs versao antiga:
    # - loadTimes/csi CONGELADOS apos primeiro call (Chrome real: requestTime===requestTime)
    # - timeOrigin lazy (NAO Date.now() em cada call)
    # - wasAlpnNegotiated=true alpnNegotiatedProtocol='h2' (ALPN moderno, NAO NPN)
    # - runtime.connect retorna Port com onDisconnect async + lastError (Chrome real
    #   sem extension valida NUNCA lanca TypeError sync — sketch original errado)
    # - toString hardening por funcao (Function.prototype.toString.call retorna native code)
    # - Object.keys(chrome.runtime) na ordem realista
    """
    if (!window.chrome) {
        const _native = (name) => 'function ' + name + '() { [native code] }';

        // t0 lazy: snapshot no primeiro call apos DOMContentLoaded (NAO no init)
        let _t0Cache = null;
        const t0 = () => {
            if (_t0Cache !== null) return _t0Cache;
            _t0Cache = (performance && performance.timeOrigin) ? performance.timeOrigin / 1000 : Date.now() / 1000;
            return _t0Cache;
        };

        let _loadTimesCache = null;
        function loadTimes() {
            if (_loadTimesCache) return _loadTimesCache;
            const base = t0();
            _loadTimesCache = Object.freeze({
                requestTime: base,
                startLoadTime: base + 0.0001,
                commitLoadTime: base + 0.05,
                finishDocumentLoadTime: base + 0.5,
                finishLoadTime: base + 0.8,
                firstPaintTime: base + 0.3,
                firstPaintAfterLoadTime: 0,
                navigationType: 'Other',
                wasFetchedViaSpdy: true,
                wasNpnNegotiated: false,
                wasAlpnNegotiated: true,
                alpnNegotiatedProtocol: 'h2',
                connectionInfo: 'h2',
                wasAlternateProtocolAvailable: false,
            });
            return _loadTimesCache;
        }
        Object.defineProperty(loadTimes, 'toString', { value: () => _native('loadTimes'), writable: false });

        let _csiCache = null;
        function csi() {
            if (_csiCache) return _csiCache;
            const start = Math.floor(t0() * 1000);
            _csiCache = Object.freeze({
                startE: start,
                onloadT: start + 800,
                pageT: 800,
                tran: 15,
            });
            return _csiCache;
        }
        Object.defineProperty(csi, 'toString', { value: () => _native('csi'), writable: false });

        // runtime.connect — Chrome real retorna Port que fires onDisconnect async com lastError.
        // NUNCA lanca sync (sketch original do PATCH-013 estava errado).
        const _runtimeConnect = function(...args) {
            const port = {
                name: args[1]?.name || '',
                onDisconnect: {
                    addListener: (fn) => setTimeout(() => {
                        window.chrome.runtime.lastError = { message: "Could not establish connection. Receiving end does not exist." };
                        try { fn(); } catch (e) {}
                    }, 1),
                    removeListener: () => {},
                    hasListener: () => false,
                },
                onMessage: { addListener: () => {}, removeListener: () => {}, hasListener: () => false },
                postMessage: () => {},
                disconnect: () => {},
                sender: undefined,
            };
            return port;
        };
        Object.defineProperty(_runtimeConnect, 'toString', { value: () => _native('connect'), writable: false });

        const _runtimeSendMessage = function() {
            // Chrome real: lastError + callback async se extension id invalida
            setTimeout(() => {
                window.chrome.runtime.lastError = { message: "Could not establish connection. Receiving end does not exist." };
            }, 1);
        };
        Object.defineProperty(_runtimeSendMessage, 'toString', { value: () => _native('sendMessage'), writable: false });

        // Ordem importa em Object.keys (Chrome real: id, getURL, getManifest, connect, sendMessage, onConnect, onMessage)
        const runtime = {};
        Object.defineProperty(runtime, 'id', { value: undefined, enumerable: true, configurable: false });
        Object.defineProperty(runtime, 'getURL', { value: function(path) { return 'chrome-extension://invalid/' + path; }, enumerable: true });
        Object.defineProperty(runtime, 'getManifest', { value: function() { return undefined; }, enumerable: true });
        Object.defineProperty(runtime, 'connect', { value: _runtimeConnect, enumerable: true });
        Object.defineProperty(runtime, 'sendMessage', { value: _runtimeSendMessage, enumerable: true });
        Object.defineProperty(runtime, 'onConnect', { value: { addListener: () => {}, removeListener: () => {} }, enumerable: true });
        Object.defineProperty(runtime, 'onMessage', { value: { addListener: () => {}, removeListener: () => {} }, enumerable: true });
        Object.defineProperty(runtime, 'lastError', { value: undefined, writable: true, enumerable: false });

        const app = {
            isInstalled: false,
            getDetails: function() { return null; },
            getIsInstalled: function() { return false; },
            InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
            RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
        };
        Object.defineProperty(app.getDetails, 'toString', { value: () => _native('getDetails'), writable: false });
        Object.defineProperty(app.getIsInstalled, 'toString', { value: () => _native('getIsInstalled'), writable: false });

        window.chrome = { loadTimes, csi, runtime, app };
    }
    """,

    # 3. Plugins array (headless returns empty)
    """
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const plugins = [
                {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
                {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''},
                {name: 'Native Client', filename: 'internal-nacl-plugin', description: ''},
            ];
            plugins.length = 3;
            plugins.item = i => plugins[i];
            plugins.namedItem = n => plugins.find(p => p.name === n);
            plugins.refresh = () => {};
            return plugins;
        }
    });
    """,

    # 4. Languages
    """
    Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR', 'pt', 'en-US', 'en']});
    Object.defineProperty(navigator, 'language', {get: () => 'pt-BR'});
    """,

    # 5. Platform
    """Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});""",

    # 6. Hardware concurrency + device memory
    """
    Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
    Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
    """,

    # 7. Permissions API (automation returns inconsistent)
    """
    const _origQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = (params) => {
        if (params.name === 'notifications') {
            return Promise.resolve({state: Notification.permission});
        }
        return _origQuery(params);
    };
    """,

    # 8. WebGL vendor/renderer spoofing
    """
    const _getParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {
        if (param === 37445) return 'Google Inc. (NVIDIA)';
        if (param === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)';
        return _getParam.call(this, param);
    };
    const _getParam2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function(param) {
        if (param === 37445) return 'Google Inc. (NVIDIA)';
        if (param === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)';
        return _getParam2.call(this, param);
    };
    """,

    # 9. Canvas fingerprint noise
    """
    const _toDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type) {
        if (this.width > 16 && this.height > 16) {
            const ctx = this.getContext('2d');
            if (ctx) {
                const imgData = ctx.getImageData(0, 0, Math.min(this.width, 4), Math.min(this.height, 4));
                for (let i = 0; i < imgData.data.length; i += 4) {
                    imgData.data[i] = imgData.data[i] ^ (Math.random() < 0.1 ? 1 : 0);
                }
                ctx.putImageData(imgData, 0, 0);
            }
        }
        return _toDataURL.apply(this, arguments);
    };
    """,

    # 10. Prevent WebRTC IP leak
    """
    const _RTCPeerConnection = window.RTCPeerConnection || window.webkitRTCPeerConnection;
    if (_RTCPeerConnection) {
        const _origCreate = _RTCPeerConnection.prototype.createDataChannel;
        window.RTCPeerConnection = function(...args) {
            const config = args[0] || {};
            config.iceServers = [];
            return new _RTCPeerConnection(config);
        };
        window.RTCPeerConnection.prototype = _RTCPeerConnection.prototype;
    }
    """,

    # 11. Protect patched functions from toString detection
    """
    const _nativeToString = Function.prototype.toString;
    const _patchedFns = new Set();
    const _origToString = function() {
        if (_patchedFns.has(this)) {
            return 'function ' + (this.name || '') + '() { [native code] }';
        }
        return _nativeToString.call(this);
    };
    Function.prototype.toString = _origToString;
    _patchedFns.add(Function.prototype.toString);
    """,
]


async def launch_stealth_browser(config: LinkedInConfig):
    """Launch browser with maximum anti-detection — patchright official pattern.

    Returns (browser, context, page) tuple.
    `browser` is None when persistent context is used (the recommended path).

    This implementation follows the verbatim Patchright README "Best Practice":
        launch_persistent_context(
            user_data_dir, channel='chrome',
            headless=False, no_viewport=True,
        )  # do NOT pass custom headers or user_agent
    Anything else (launch+new_context, headless=True, custom UA, fixed viewport)
    leaks automation signals that LinkedIn detects → ERR_TOO_MANY_REDIRECTS.

    On Linux servers without a display, wrap the parent process with `xvfb-run`
    so headless=False still works (DISPLAY=:99 from xvfb-run).

    PREFLIGHT GATE inegociavel:
    - Verifica proxy SOCKS5 reverse PC via curl
    - Aborta se egress for datacenter (NUNCA permite IP direto VM)
    - Setar HERMES_SKIP_PREFLIGHT=1 SO em testes locais, NUNCA em prod LinkedIn
    """
    # === PREFLIGHT GATE ===
    if os.environ.get("HERMES_SKIP_PREFLIGHT") != "1":
        from linkedin.preflight import assert_tunnel_healthy, ProxyHealthError
        try:
            egress_ip = assert_tunnel_healthy(config.proxy_server)
            logger.info(f"preflight OK — egress {egress_ip}")
        except ProxyHealthError as e:
            logger.error(f"preflight FAIL — abortando: {e}")
            raise

    # === ACCOUNT BURN GATE (PATCH-008 reduzido) ===
    # Se este account_id ja foi marcado burned em sessao anterior, NAO subir browser.
    account_profile = None
    if config.account_email and os.environ.get("HERMES_SKIP_BURN_CHECK") != "1":
        from linkedin.account_profile import assert_not_burned
        account_profile = assert_not_burned(config.account_email)
        logger.info(
            f"account_profile {config.account_email}: "
            f"sticky={account_profile.proxy_sticky_id} logins={account_profile.login_count} "
            f"challenges={account_profile.challenge_count}"
        )

    use_patchright = False
    try:
        from patchright.async_api import async_playwright
        use_patchright = True
        logger.info("Using Patchright (Runtime.enable patched)")
    except ImportError:
        try:
            from playwright.async_api import async_playwright
            logger.warning("Patchright not available — Playwright with JS stealth patches")
        except ImportError:
            raise RuntimeError("Neither patchright nor playwright installed. Run: pip install patchright")

    pw_instance = await async_playwright().__aenter__()

    # Detect Chrome stable — REQUIRED for real TLS/JA3 fingerprint
    engine_used = "chromium_bundled"
    chrome_path = None
    if config.use_system_chrome:
        chrome_path = _detect_chrome_path()
        if chrome_path:
            engine_used = "chrome_stable"
            logger.info(f"Chrome real detectado: {chrome_path}")
        else:
            logger.warning(
                "Chrome stable NÃO instalado — caindo no Chromium bundled. "
                "TLS fingerprint pior. Instale: apt install google-chrome-stable"
            )

    # ── Args: minimize — patchright already handles automation flags ──────
    launch_args = [
        # WebRTC leak prevention (SOCKS5 doesn't relay UDP → would expose VM IP)
        "--webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--disable-features=WebRtcHideLocalIpsWithMdns",
        # WebGL via Mesa llvmpipe — sem isso, Chromium em xvfb headless retorna gl=null
        # (LinkedIn checa gl.getContext('webgl') !== null como anti-bot).
        # angle = caminho que mapeia pra GLX/EGL nativo do Xvfb+Mesa.
        "--use-gl=angle",
        "--use-angle=swiftshader",
        "--enable-features=Vulkan",
    ]

    # Per-account persistent profile dir — preserves cookies/cache/local storage
    # across runs, makes the session look like a returning user instead of a
    # fresh login every time.
    user_data_dir = config.user_data_dir
    Path(user_data_dir).mkdir(parents=True, exist_ok=True)
    is_fresh_profile = not (Path(user_data_dir) / "Default" / "Cookies").exists()

    launch_kwargs: dict = {
        "user_data_dir": user_data_dir,
        # CRITICAL per patchright docs: NOT True. Use xvfb-run on headless servers.
        "headless": False,
        # CRITICAL per patchright docs: no fixed viewport.
        "no_viewport": True,
        "args": launch_args,
        "ignore_default_args": ["--enable-automation"],
        # Geo/locale/timezone are allowed — they're inherent to the proxy egress.
        "timezone_id": config.timezone,
        "geolocation": config.geolocation,
        "permissions": ["geolocation"],
        # Locale pt-BR EXIGIDO (coerencia com timezone America/Cuiaba). Sem isso,
        # navigator.language vira "en-US" do default Chrome Linux + timezone BR
        # = mismatch flagrante = red flag pro LinkedIn.
        "locale": config.locale,
        # Do NOT pass user_agent, viewport, color_scheme — eles forcam fingerprint
        # diferente do Chrome real default.
    }

    if chrome_path:
        # Standard install paths can use channel='chrome'; user-local needs executable_path.
        standard_paths = ("/usr/bin/google-chrome", "/opt/google/chrome", r"C:\Program Files")
        if any(chrome_path.startswith(p) for p in standard_paths):
            launch_kwargs["channel"] = "chrome"
        else:
            launch_kwargs["executable_path"] = chrome_path

    if config.proxy_server:
        launch_kwargs["proxy"] = {"server": config.proxy_server}
        if config.proxy_username:
            launch_kwargs["proxy"]["username"] = config.proxy_username
        if config.proxy_password:
            launch_kwargs["proxy"]["password"] = config.proxy_password

    context = await pw_instance.chromium.launch_persistent_context(**launch_kwargs)

    # Defense-in-depth WebRTC patch (Patchright doesn't strip ICE servers).
    webrtc_patch = """
    (() => {
        const _RTC = window.RTCPeerConnection || window.webkitRTCPeerConnection;
        if (!_RTC) return;
        const Patched = function(...args) {
            const cfg = args[0] || {};
            cfg.iceServers = [];
            return new _RTC(cfg);
        };
        Patched.prototype = _RTC.prototype;
        window.RTCPeerConnection = Patched;
        window.webkitRTCPeerConnection = Patched;
    })();
    """
    await context.add_init_script(webrtc_patch)

    # JS-level patches only when using vanilla Playwright (Patchright handles these natively)
    if not use_patchright:
        combined = "\n".join(_STEALTH_SCRIPTS)
        await context.add_init_script(combined)
        logger.info(f"Injected {len(_STEALTH_SCRIPTS)} stealth patches")

    # ── Cookie seeding strategy (CRITICAL for avoiding redirect loops) ───
    # Two problems we must NOT trigger:
    # 1) Seeding STALE session cookies (JSESSIONID, lidc, bscookie) — these
    #    are short-lived (minutes/hours). If we restore an expired one,
    #    LinkedIn sees "session exists but expired" → redirect to refresh,
    #    which conflicts with li_at → infinite redirect loop.
    # 2) Using STALE li_at from session_file when env LI_AT is fresher.
    #    The Chrome extension keeps env LI_AT up to date; session_file may
    #    be days old. Env always wins.
    #
    # Strategy: seed ONLY long-lived identity cookies + use freshest li_at.
    if is_fresh_profile:
        import os as _os
        li_at_env = _os.environ.get("LI_AT", "").strip()

        # MINIMAL seed: env LI_AT only. Everything else (bcookie, JSESSIONID,
        # lidc, bscookie) gets issued fresh by LinkedIn on first request.
        # Reason: when we seed a stale bcookie tied to a different session,
        # LinkedIn sees inconsistency between bcookie identity and li_at issuance
        # → redirect to /uas/login or feed-loop. Safer to start clean and let
        # LinkedIn build a coherent identity around our env li_at.
        DURABLE_COOKIES = {"li_at"}

        seeded = []
        if config.session_file and Path(config.session_file).exists():
            try:
                with open(config.session_file) as f:
                    state = json.load(f)
                for c in state.get("cookies", []):
                    name = c.get("name")
                    if name not in DURABLE_COOKIES:
                        continue
                    if name == "li_at" and li_at_env:
                        # env always overrides — extension keeps it fresher
                        continue
                    cc = {k: v for k, v in c.items() if k in (
                        "name", "value", "domain", "path", "expires",
                        "httpOnly", "secure", "sameSite",
                    )}
                    ss = cc.get("sameSite")
                    if isinstance(ss, str):
                        s = ss.lower()
                        cc["sameSite"] = "Lax" if s == "lax" else "Strict" if s == "strict" else "None"
                    else:
                        cc.pop("sameSite", None)
                    seeded.append(cc)
            except Exception as e:
                logger.warning(f"session_file read failed: {e}")

        # Always prefer env LI_AT (freshest) — extension feeds it
        if li_at_env:
            seeded.append({
                "name": "li_at",
                "value": li_at_env,
                "domain": ".linkedin.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "None",
            })

        if seeded:
            try:
                await context.add_cookies(seeded)
                names = sorted({c["name"] for c in seeded})
                logger.info(f"Seeded {len(seeded)} durable cookies into fresh profile: {names}")
            except Exception as e:
                logger.warning(f"Cookie seeding failed: {e}")

    context.set_default_timeout(30000)
    context.set_default_navigation_timeout(60000)

    # launch_persistent_context returns a BrowserContext; pages auto-created.
    # Reuse the first page if present, else open a new one.
    pages = context.pages
    page = pages[0] if pages else await context.new_page()

    page._pw_instance = pw_instance
    page._browser = None  # persistent context — no separate browser object
    page._context = context
    page._engine_used = engine_used
    page._account_profile = account_profile  # disponivel pra flows usarem check_and_burn

    # === STEALTH COMPLIANCE GATE ===
    # Valida fingerprint critico antes de qualquer navegacao LinkedIn.
    # Auto-corrige lang/chrome.loadTimes se faltarem. Aborta se critical fail.
    if os.environ.get("HERMES_SKIP_COMPLIANCE") != "1":
        from linkedin.stealth_compliance import enforce_compliance, StealthComplianceError
        try:
            # Navega data: URL com canvas init pra forcar GL pipeline.
            # about:blank nao trigger WebGL init no Chromium — falsos negativos.
            await page.goto(
                "data:text/html,<html><body><canvas id=g></canvas><script>"
                "document.getElementById('g').getContext('webgl');"
                "</script></body></html>",
                wait_until="domcontentloaded", timeout=10000,
            )
            compliance = await enforce_compliance(
                page,
                abort_on_critical=os.environ.get("HERMES_COMPLIANCE_STRICT", "1") == "1",
                auto_correct=True,
                min_score=int(os.environ.get("HERMES_COMPLIANCE_MIN_SCORE", "70")),
            )
            page._compliance = compliance
            logger.info(
                f"compliance: score={compliance['score']} "
                f"failed_crit={len(compliance['failed_critical'])} "
                f"auto_corrected={compliance.get('auto_corrected', False)}"
            )
        except StealthComplianceError:
            try:
                await context.close()
            except Exception:
                pass
            raise
    page._patchright_active = use_patchright
    page._user_data_dir = user_data_dir
    page._fresh_profile = is_fresh_profile

    return None, context, page


async def save_session(context, config: LinkedInConfig):
    """Save browser session (cookies + localStorage) for reuse."""
    if config.session_file:
        state = await context.storage_state()
        Path(config.session_file).parent.mkdir(parents=True, exist_ok=True)
        with open(config.session_file, "w") as f:
            json.dump(state, f)
        logger.info(f"Session saved to {config.session_file}")


async def close_stealth_browser(page):
    """Clean shutdown of browser, context, and playwright."""
    try:
        context = getattr(page, "_context", None)
        browser = getattr(page, "_browser", None)
        pw_instance = getattr(page, "_pw_instance", None)
        if context:
            try:
                await context.close()
            except Exception as e:
                logger.warning(f"context.close: {e}")
        if browser:
            try:
                await browser.close()
            except Exception as e:
                logger.warning(f"browser.close: {e}")
        if pw_instance:
            # Patchright/Playwright async API uses .stop() on the instance, not __aexit__.
            # __aexit__ exists only on the context manager wrapper.
            try:
                if hasattr(pw_instance, "stop"):
                    await pw_instance.stop()
                elif hasattr(pw_instance, "__aexit__"):
                    await pw_instance.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"pw_instance.stop: {e}")
    except Exception as e:
        logger.warning(f"Error closing browser: {e}")


def _random_user_agent() -> str:
    """Generate realistic Chrome UA string matching current versions."""
    chrome_versions = [
        "135.0.6998.89", "135.0.6998.118", "136.0.7103.49",
        "136.0.7103.93", "137.0.7151.40", "137.0.7151.68",
    ]
    os_strings = [
        "Windows NT 10.0; Win64; x64",
        "Windows NT 10.0; Win64; x64",
        "Macintosh; Intel Mac OS X 10_15_7",
        "X11; Linux x86_64",
    ]
    cv = random.choice(chrome_versions)
    os_str = random.choice(os_strings)
    return f"Mozilla/5.0 ({os_str}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{cv} Safari/537.36"
