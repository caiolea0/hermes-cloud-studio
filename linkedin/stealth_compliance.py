"""Stealth Compliance Layer — inegociavel.

Validacao pos-launch do browser: checa fingerprint critico ANTES de tocar LinkedIn.
Auto-corrige o que da (via add_init_script). Aborta se falhar criticos.

Sinais checados (cada um com severity):

CRITICAL (failure aborta):
  - navigator.webdriver eh false na instancia E webdriver descriptor existe no prototype
  - navigator.language eh 'pt-BR' (ou comeca com 'pt')
  - timezone Intl eh America/Cuiaba (ou pelo menos -3/-4 offset)
  - chrome object presente
  - WebGL getContext nao retorna null

HIGH (failure ainda permite mas com warning):
  - plugins.length >= 3
  - userAgentData.platform coerente com UA
  - hardwareConcurrency >= 2

MEDIUM (advisory):
  - canvas getContext('2d').getImageData funciona
  - screen.width >= 1366

Uso:
    from linkedin.stealth_compliance import enforce_compliance
    compliance = await enforce_compliance(page, abort_on_critical=True)
    # compliance: {score, passed, failed, warnings, auto_corrected}
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)


class StealthComplianceError(RuntimeError):
    """Raised quando compliance critical falha. NUNCA permitir bypass em prod."""


# JS evaluate gigante — mesma estrutura do fingerprint_baseline mas focado em checks
COMPLIANCE_PROBE_JS = r"""
(() => {
    const checks = {};

    // CRITICAL: webdriver location
    const wdProto = Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver');
    const wdInst = Object.getOwnPropertyDescriptor(navigator, 'webdriver');
    checks.webdriver_proto_present = !!wdProto;
    checks.webdriver_inst_absent = !wdInst;
    checks.webdriver_value = navigator.webdriver;

    // CRITICAL: locale
    checks.lang = navigator.language;
    checks.lang_starts_pt = (navigator.language || '').toLowerCase().startsWith('pt');
    checks.languages_first_pt = (navigator.languages || [])[0]?.toLowerCase().startsWith('pt') || false;

    // CRITICAL: timezone
    try {
        checks.tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
        checks.tz_offset = new Date().getTimezoneOffset();
        checks.tz_brazilian = (checks.tz_offset === 180 || checks.tz_offset === 240);  // -3 or -4 UTC
    } catch (e) { checks.tz_error = String(e); }

    // CRITICAL: chrome obj
    checks.chrome_obj = typeof window.chrome;
    checks.chrome_loadtimes = !!(window.chrome && window.chrome.loadTimes);
    checks.chrome_runtime = !!(window.chrome && window.chrome.runtime);

    // CRITICAL: WebGL working
    try {
        const c = document.createElement('canvas');
        const gl = c.getContext('webgl') || c.getContext('experimental-webgl');
        checks.webgl_ok = !!gl;
        if (gl) {
            checks.webgl_renderer = gl.getParameter(gl.RENDERER);
            checks.webgl_vendor = gl.getParameter(gl.VENDOR);
            const ext = gl.getExtension('WEBGL_debug_renderer_info');
            checks.webgl_unmasked_renderer = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : null;
        }
    } catch (e) { checks.webgl_error = String(e); }

    // HIGH: plugins
    checks.plugins_count = navigator.plugins.length;

    // HIGH: userAgentData
    if (navigator.userAgentData) {
        checks.uaData_platform = navigator.userAgentData.platform;
        checks.uaData_mobile = navigator.userAgentData.mobile;
        checks.uaData_brands = navigator.userAgentData.brands.map(b => b.brand);
    } else {
        checks.uaData_missing = true;
    }

    // HIGH: hardware
    checks.hardwareConcurrency = navigator.hardwareConcurrency;
    checks.deviceMemory = navigator.deviceMemory;
    checks.maxTouchPoints = navigator.maxTouchPoints;

    // MEDIUM: canvas
    try {
        const c = document.createElement('canvas');
        const ctx = c.getContext('2d');
        ctx.fillRect(0, 0, 10, 10);
        const img = ctx.getImageData(0, 0, 10, 10);
        checks.canvas_2d_ok = !!img && img.data.length > 0;
    } catch (e) { checks.canvas_2d_error = String(e); }

    // MEDIUM: screen
    checks.screen_w = screen.width;
    checks.screen_h = screen.height;
    checks.viewport_w = innerWidth;
    checks.viewport_h = innerHeight;

    // platform vs UA coherence
    checks.platform = navigator.platform;
    checks.ua = navigator.userAgent;
    const uaIsLinux = /linux/i.test(navigator.userAgent);
    const platIsLinux = /linux/i.test(navigator.platform);
    checks.platform_ua_coherent = uaIsLinux === platIsLinux;

    return checks;
})()
"""


def _evaluate_compliance(probe: dict[str, Any]) -> dict[str, Any]:
    """Classifica probe dict em passed/failed/warnings + score 0-100."""
    failed_critical: list[str] = []
    failed_high: list[str] = []
    warnings: list[str] = []
    passed: list[str] = []

    def critical(name: str, ok: bool, detail: str = ""):
        (passed if ok else failed_critical).append(f"{name}{(' — ' + detail) if detail else ''}")

    def high(name: str, ok: bool, detail: str = ""):
        (passed if ok else failed_high).append(f"{name}{(' — ' + detail) if detail else ''}")

    def warn(name: str, ok: bool, detail: str = ""):
        (passed if ok else warnings).append(f"{name}{(' — ' + detail) if detail else ''}")

    # CRITICAL
    critical("webdriver_proto_present", probe.get("webdriver_proto_present", False))
    critical("webdriver_inst_absent", probe.get("webdriver_inst_absent", False))
    critical("webdriver_value_false", probe.get("webdriver_value") is False)
    critical(
        "lang_pt_BR",
        probe.get("lang_starts_pt") or probe.get("languages_first_pt"),
        f"got lang={probe.get('lang')!r}",
    )
    critical(
        "tz_brazilian",
        probe.get("tz_brazilian", False),
        f"got tz={probe.get('tz')!r} offset={probe.get('tz_offset')}",
    )
    critical("chrome_obj_present", probe.get("chrome_obj") == "object")
    critical("chrome_loadtimes_present", probe.get("chrome_loadtimes", False))
    critical("webgl_context_ok", probe.get("webgl_ok", False), probe.get("webgl_error", ""))
    critical("platform_ua_coherent", probe.get("platform_ua_coherent", True))

    # HIGH
    high("plugins_>=3", probe.get("plugins_count", 0) >= 3, f"count={probe.get('plugins_count')}")
    high("uaData_present", not probe.get("uaData_missing", False))
    high("hardware_>=2", probe.get("hardwareConcurrency", 0) >= 2)

    # MEDIUM
    warn("canvas_2d_ok", probe.get("canvas_2d_ok", False))
    warn("screen_>=1366", probe.get("screen_w", 0) >= 1366, f"w={probe.get('screen_w')}")

    # Score: critical 6pts cada, high 2pts, medium 1pt
    crit_count = 9
    high_count = 3
    med_count = 2
    score = 0
    for p in passed:
        # peso por categoria (deduzido pela classificacao acima — simplificado: 100/N)
        pass
    # Recalcular mais explicito:
    crit_passed = sum(1 for x in passed if any(x.startswith(k) for k in [
        "webdriver_proto", "webdriver_inst", "webdriver_value", "lang_pt", "tz_braz",
        "chrome_obj", "chrome_load", "webgl_context", "platform_ua",
    ]))
    high_passed = sum(1 for x in passed if any(x.startswith(k) for k in [
        "plugins_", "uaData_", "hardware_",
    ]))
    med_passed = sum(1 for x in passed if any(x.startswith(k) for k in [
        "canvas_", "screen_",
    ]))
    score = round(
        (crit_passed / crit_count) * 70
        + (high_passed / high_count) * 20
        + (med_passed / med_count) * 10
    )

    return {
        "score": score,
        "passed": passed,
        "failed_critical": failed_critical,
        "failed_high": failed_high,
        "warnings": warnings,
        "probe": probe,
    }


# JS de auto-correcao — aplicado se compliance falhar e auto_correct=True
AUTO_CORRECT_JS = r"""
(() => {
    // Lang/languages override (caso locale launch_kwargs nao tenha pegado)
    try {
        Object.defineProperty(navigator, 'language', { get: () => 'pt-BR', configurable: true });
        Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en-US', 'en'], configurable: true });
    } catch (e) {}

    // chrome.loadTimes minimal stub se faltando
    if (window.chrome && !window.chrome.loadTimes) {
        try {
            const t0 = performance.timeOrigin || Date.now();
            const stub = () => ({
                requestTime: t0 / 1000,
                startLoadTime: t0 / 1000,
                commitLoadTime: t0 / 1000 + 0.05,
                finishDocumentLoadTime: t0 / 1000 + 0.5,
                finishLoadTime: t0 / 1000 + 0.8,
                firstPaintTime: t0 / 1000 + 0.3,
                navigationType: 'Other',
                wasFetchedViaSpdy: true,
                wasNpnNegotiated: false,
                wasAlpnNegotiated: true,
                alpnNegotiatedProtocol: 'h2',
                connectionInfo: 'h2',
            });
            window.chrome.loadTimes = stub;
        } catch (e) {}
    }
    return true;
})()
"""


async def probe_compliance(page) -> dict[str, Any]:
    """Run probe JS no page, retorna avaliacao completa."""
    probe = await page.evaluate(COMPLIANCE_PROBE_JS)
    return _evaluate_compliance(probe)


async def enforce_compliance(
    page,
    abort_on_critical: bool = True,
    auto_correct: bool = True,
    min_score: int = 70,
) -> dict[str, Any]:
    """Validacao pos-launch. Auto-corrige se permitido. Aborta se critical falha.

    Args:
        page: Playwright/Patchright Page apos navegacao inicial (idealmente about:blank).
        abort_on_critical: se True, raise StealthComplianceError em critical fail.
        auto_correct: aplica AUTO_CORRECT_JS se algum critical falhar.
        min_score: score minimo aceitavel.

    Returns:
        dict com score, passed, failed_*, warnings, auto_corrected (bool)
    """
    result = await probe_compliance(page)
    result["auto_corrected"] = False

    if result["failed_critical"] and auto_correct:
        logger.warning(f"compliance critical fails — tentando auto-correct: {result['failed_critical']}")
        try:
            await page.evaluate(AUTO_CORRECT_JS)
            # re-probe
            result_v2 = await probe_compliance(page)
            result_v2["auto_corrected"] = True
            result_v2["pre_correct_score"] = result["score"]
            result_v2["pre_correct_failed"] = result["failed_critical"]
            result = result_v2
            logger.info(f"compliance pos-correcao score={result['score']}")
        except Exception as e:
            logger.error(f"auto_correct falhou: {e}")
            result["auto_correct_error"] = str(e)

    if result["score"] < min_score or result["failed_critical"]:
        msg = (
            f"compliance FAIL score={result['score']}/100 "
            f"critical={result['failed_critical']} high={result['failed_high']}"
        )
        if abort_on_critical:
            logger.error(msg)
            raise StealthComplianceError(msg)
        else:
            logger.warning(msg)
    else:
        logger.info(f"compliance OK score={result['score']}/100")

    return result
