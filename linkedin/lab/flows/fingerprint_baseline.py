"""Flow: capturar baseline de fingerprint via sites publicos de teste.

Roda Patchright no perfil lab, visita N sites de fingerprint, captura:
- Screenshot full page
- HTML do body
- Console messages (se houver)
- Dump de fingerprint extraido via JS

Output: lab/artifacts/fingerprint_baseline/{site}_{timestamp}/

NAO toca LinkedIn. Validacao antes de qualquer login real.
"""
from __future__ import annotations
import asyncio
import json
from datetime import datetime
from pathlib import Path

SITES = [
    {"name": "creepjs", "url": "https://abrahamjuliot.github.io/creepjs/", "wait": 8.0},
    {"name": "browserleaks_webgl", "url": "https://browserleaks.com/webgl", "wait": 5.0},
    {"name": "browserleaks_canvas", "url": "https://browserleaks.com/canvas", "wait": 5.0},
    {"name": "tls_peet", "url": "https://tls.peet.ws/api/all", "wait": 3.0},
    {"name": "bot_sannysoft", "url": "https://bot.sannysoft.com/", "wait": 5.0},
    {"name": "fingerprint_pro_demo", "url": "https://fingerprint.com/products/bot-detection/", "wait": 4.0},
    {"name": "amiunique", "url": "https://amiunique.org/fingerprint", "wait": 6.0},
]

FINGERPRINT_DUMP_JS = r"""
(() => {
    const fp = {
        userAgent: navigator.userAgent,
        platform: navigator.platform,
        vendor: navigator.vendor,
        language: navigator.language,
        languages: navigator.languages,
        hardwareConcurrency: navigator.hardwareConcurrency,
        deviceMemory: navigator.deviceMemory,
        maxTouchPoints: navigator.maxTouchPoints,
        webdriver: navigator.webdriver,
        webdriver_proto: Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver') ? 'present' : 'absent',
        webdriver_instance: Object.getOwnPropertyDescriptor(navigator, 'webdriver') ? 'present' : 'absent',
        plugins_count: navigator.plugins.length,
        plugins: Array.from(navigator.plugins).map(p => p.name),
        screen: {w: screen.width, h: screen.height, depth: screen.colorDepth, pr: window.devicePixelRatio},
        viewport: {w: innerWidth, h: innerHeight},
        timezone_offset: new Date().getTimezoneOffset(),
        timezone_intl: Intl.DateTimeFormat().resolvedOptions().timeZone,
        chrome_object: typeof window.chrome,
        chrome_loadtimes: window.chrome && window.chrome.loadTimes ? 'present' : 'absent',
        userAgentData: navigator.userAgentData ? {
            mobile: navigator.userAgentData.mobile,
            platform: navigator.userAgentData.platform,
            brands: navigator.userAgentData.brands,
        } : null,
    };

    // WebGL
    try {
        const canvas = document.createElement('canvas');
        const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
        if (gl) {
            const dbg = gl.getExtension('WEBGL_debug_renderer_info');
            fp.webgl = {
                vendor: gl.getParameter(gl.VENDOR),
                renderer: gl.getParameter(gl.RENDERER),
                unmasked_vendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : null,
                unmasked_renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null,
                max_texture_size: gl.getParameter(gl.MAX_TEXTURE_SIZE),
                max_viewport_dims: Array.from(gl.getParameter(gl.MAX_VIEWPORT_DIMS)),
                extensions: gl.getSupportedExtensions(),
            };
        }
    } catch (e) { fp.webgl_error = String(e); }

    // Canvas hash
    try {
        const canvas = document.createElement('canvas');
        canvas.width = 200; canvas.height = 50;
        const ctx = canvas.getContext('2d');
        ctx.textBaseline = 'top';
        ctx.font = '14px Arial';
        ctx.fillStyle = '#f60';
        ctx.fillRect(125, 1, 62, 20);
        ctx.fillStyle = '#069';
        ctx.fillText('Hermes-Lab-Fingerprint', 2, 15);
        fp.canvas_hash = canvas.toDataURL().slice(-50);
    } catch (e) { fp.canvas_error = String(e); }

    return fp;
})()
"""


async def run(config, headful: bool = True, sites: list | None = None) -> dict:
    """Run fingerprint baseline capture.

    Args:
        config: LinkedInConfig lab.
        headful: visivel (sempre True em lab).
        sites: lista subset de SITES por name; None = todos.

    Returns:
        dict {site_name: {fingerprint_dump, screenshot_path, html_path}}
    """
    # Lazy import — evita carregar stealth se nao precisar
    from linkedin import stealth

    target_sites = SITES if sites is None else [s for s in SITES if s["name"] in sites]
    if not target_sites:
        raise ValueError(f"Nenhum site valido. Disponiveis: {[s['name'] for s in SITES]}")

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(__file__).parent.parent / "artifacts" / "fingerprint_baseline" / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    results: dict = {"timestamp": timestamp, "out_dir": str(out_dir), "sites": {}}

    _, browser_context, page = await stealth.launch_stealth_browser(config)
    try:
        for site in target_sites:
            name = site["name"]
            print(f"[lab/fp] visiting {name} -> {site['url']}")
            site_dir = out_dir / name
            site_dir.mkdir(exist_ok=True)
            try:
                await page.goto(site["url"], wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(site["wait"])
                # Screenshot
                await page.screenshot(path=str(site_dir / "screenshot.png"), full_page=True)
                # HTML
                html = await page.content()
                (site_dir / "body.html").write_text(html, encoding="utf-8")
                # Fingerprint dump
                fp = await page.evaluate(FINGERPRINT_DUMP_JS)
                (site_dir / "fingerprint.json").write_text(json.dumps(fp, indent=2, default=str), encoding="utf-8")
                results["sites"][name] = {
                    "ok": True,
                    "fingerprint": fp,
                    "screenshot": str(site_dir / "screenshot.png"),
                }
                print(f"[lab/fp]   OK ({name})")
            except Exception as e:
                results["sites"][name] = {"ok": False, "error": str(e)}
                print(f"[lab/fp]   FAIL ({name}): {e}")

        # Salva resumo
        (out_dir / "summary.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        print(f"\n[lab/fp] DONE. Artifacts em {out_dir}")
    finally:
        try:
            await browser_context.close()
        except Exception:
            pass

    return results
