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
import random
from pathlib import Path
from typing import Optional

from .config import LinkedInConfig

logger = logging.getLogger("hermes.linkedin.stealth")

# JS patches injected into every page context
_STEALTH_SCRIPTS = [
    # 1. navigator.webdriver = false
    """Object.defineProperty(navigator, 'webdriver', {get: () => false});""",

    # 2. window.chrome runtime object (missing in headless)
    """
    if (!window.chrome) {
        window.chrome = {
            runtime: {id: undefined, connect: () => {}, sendMessage: () => {}},
            loadTimes: () => ({commitLoadTime: Date.now()/1000, connectionInfo: "http/1.1",
                finishDocumentLoadTime: Date.now()/1000, finishLoadTime: Date.now()/1000,
                firstPaintAfterLoadTime: 0, firstPaintTime: Date.now()/1000,
                navigationType: "Other", npnNegotiatedProtocol: "unknown",
                requestTime: Date.now()/1000, startLoadTime: Date.now()/1000,
                wasAlternateProtocolAvailable: false, wasFetchedViaSpdy: false,
                wasNpnNegotiated: true}),
            csi: () => ({onloadT: Date.now(), startE: Date.now(), pageT: Date.now()}),
            app: {isInstalled: false, InstallState: {DISABLED: "disabled", INSTALLED: "installed", NOT_INSTALLED: "not_installed"},
                  RunningState: {CANNOT_RUN: "cannot_run", READY_TO_RUN: "ready_to_run", RUNNING: "running"}},
        };
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
    """Launch browser with maximum anti-detection.

    Returns (browser, context, page) tuple.
    Tries Patchright first, falls back to Playwright + stealth patches.
    """
    use_patchright = False
    pw = None

    try:
        from patchright.async_api import async_playwright
        use_patchright = True
        logger.info("Using Patchright (Runtime.enable patched)")
    except ImportError:
        try:
            from playwright.async_api import async_playwright
            logger.warning("Patchright not available, using Playwright with JS stealth patches")
        except ImportError:
            raise RuntimeError("Neither patchright nor playwright installed. Run: pip install patchright")

    pw_instance = await async_playwright().__aenter__()

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--disable-infobars",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-sync",
        "--disable-translate",
        "--metrics-recording-only",
        "--no-service-autorun",
        "--password-store=basic",
    ]

    if config.headless:
        launch_args.append("--headless=new")

    launch_kwargs = {
        "args": launch_args,
        "headless": False,  # we pass --headless=new manually for stealth
        "ignore_default_args": ["--enable-automation"],
    }

    if config.use_system_chrome:
        launch_kwargs["channel"] = "chrome"

    if config.proxy_server:
        launch_kwargs["proxy"] = {
            "server": config.proxy_server,
        }
        if config.proxy_username:
            launch_kwargs["proxy"]["username"] = config.proxy_username
        if config.proxy_password:
            launch_kwargs["proxy"]["password"] = config.proxy_password

    context_kwargs = {
        "viewport": {"width": config.viewport_width, "height": config.viewport_height},
        "locale": config.locale,
        "timezone_id": config.timezone,
        "geolocation": config.geolocation,
        "permissions": ["geolocation"],
        "user_agent": _random_user_agent(),
        "color_scheme": "light",
        "screen": {"width": 1920, "height": 1080},
    }

    # try persistent context first (reuses cookies/cache like real user)
    session_exists = config.session_file and Path(config.session_file).exists()
    if config.reuse_session and session_exists:
        context_kwargs["storage_state"] = config.session_file
        logger.info(f"Reusing session from {config.session_file}")

    browser = await pw_instance.chromium.launch(**launch_kwargs)
    context = await browser.new_context(**context_kwargs)

    if not use_patchright:
        combined = "\n".join(_STEALTH_SCRIPTS)
        await context.add_init_script(combined)
        logger.info(f"Injected {len(_STEALTH_SCRIPTS)} stealth patches")

    context.set_default_timeout(30000)
    context.set_default_navigation_timeout(60000)

    page = await context.new_page()

    page._pw_instance = pw_instance
    page._browser = browser
    page._context = context

    return browser, context, page


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
            await context.close()
        if browser:
            await browser.close()
        if pw_instance:
            await pw_instance.__aexit__(None, None, None)
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
