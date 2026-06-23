"""H2-F4 — Google PageSpeed Insights (PSI) API qualifier.

Free tier: 25k requests/dia, 240/min. Sem custo. Sem precisar de OAuth (apenas API key).
Doc: https://developers.google.com/speed/docs/insights/v5/get-started

Retorna scores 0-100 de Performance/SEO/Accessibility/Best-Practices + flag mobile-friendly
+ Core Web Vitals (LCP, CLS) — sinais que alimentam compute_needs_score.

Graceful: sem API key OU quota estourada OU timeout retorna {} + low_confidence=True.
Caller (core/scoring) NUNCA é derrubado por PSI ausente — sinal vira ausente, score recalcula.

Cache em memória + opcional SQLite p/ persistir entre runs (chave: URL canonicalizada).

Uso:
    from scripts.pagespeed import pagespeed_audit
    r = pagespeed_audit("https://exemplo.com.br")
    # → {"psi_performance": 42, "psi_seo": 88, ..., "mobile_friendly": True, "low_confidence": False}

CLI:
    HERMES_PAGESPEED_KEY=AIza... python scripts/pagespeed.py --url https://exemplo.com.br
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger("hermes.pagespeed")

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
PSI_CATEGORIES = ("performance", "seo", "accessibility", "best-practices")
PSI_STRATEGY_MOBILE = "mobile"

# Rate limit: 240 req/min — guard local de 4 req/segundo médio (240/60)
_PSI_RPM_LIMIT = 240
_PSI_REQUEST_LOG: deque[float] = deque(maxlen=_PSI_RPM_LIMIT)
_PSI_LOCK = threading.Lock()

# Cache em memória: URL → (result_dict, expires_at_unix)
_PSI_CACHE: dict[str, tuple[dict, float]] = {}
_PSI_CACHE_TTL = 24 * 3600  # 24h — site não muda perf score várias vezes/dia


def _canonicalize_url(url: str) -> str:
    """Normaliza URL pra chave de cache: lowercase host, drop fragment, drop trailing slash."""
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    p = urlparse(url)
    host = (p.netloc or "").lower().lstrip("www.")
    path = (p.path or "/").rstrip("/")
    return f"{p.scheme}://{host}{path or '/'}"


def _rate_limit_acquire() -> None:
    """Bloqueia se já fizemos 240 reqs nos últimos 60s (rolling window)."""
    with _PSI_LOCK:
        now = time.time()
        # Limpa requests > 60s
        while _PSI_REQUEST_LOG and now - _PSI_REQUEST_LOG[0] > 60:
            _PSI_REQUEST_LOG.popleft()
        if len(_PSI_REQUEST_LOG) >= _PSI_RPM_LIMIT:
            wait = 60 - (now - _PSI_REQUEST_LOG[0]) + 0.5
            logger.info("PSI rate limit cap (240/min) — waiting %.1fs", wait)
            time.sleep(max(wait, 0.1))
        _PSI_REQUEST_LOG.append(time.time())


def _api_key() -> str:
    """Lê HERMES_PAGESPEED_KEY ou settings.pagespeed_key. Pode retornar vazio."""
    import os
    k = os.environ.get("HERMES_PAGESPEED_KEY", "").strip()
    if k:
        return k
    try:
        from config import settings
        return (getattr(settings, "pagespeed_key", "") or "").strip()
    except Exception:
        return ""


def _empty_result(reason: str) -> dict:
    """Resultado low-confidence padrão (PSI indisponível) — caller NÃO penaliza."""
    return {
        "psi_performance": None,
        "psi_seo": None,
        "psi_accessibility": None,
        "psi_best_practices": None,
        "mobile_friendly": None,
        "lcp": None,
        "cls": None,
        "low_confidence": True,
        "reason": reason,
    }


def pagespeed_audit(
    url: str,
    *,
    timeout: float = 30.0,
    use_cache: bool = True,
    api_key: Optional[str] = None,
) -> dict:
    """Chama PSI API mobile + performance/seo/a11y/best-practices.

    Retorna dict:
        {
          "psi_performance": int 0-100 | None,
          "psi_seo": int 0-100 | None,
          "psi_accessibility": int 0-100 | None,
          "psi_best_practices": int 0-100 | None,
          "mobile_friendly": bool | None,
          "lcp": float (segundos) | None,
          "cls": float | None,
          "low_confidence": bool,
          "reason": str | None,   # "ok" | "no_api_key" | "timeout" | "quota" | "invalid_response"
        }

    Graceful em CADA branch: nunca lança exceção pra fora.
    """
    canon = _canonicalize_url(url)
    if not canon:
        return _empty_result("invalid_url")

    # Cache hit?
    if use_cache:
        cached = _PSI_CACHE.get(canon)
        if cached and cached[1] > time.time():
            logger.debug("PSI cache hit %s", canon)
            return dict(cached[0])  # cópia defensiva

    key = api_key or _api_key()
    if not key:
        return _empty_result("no_api_key")

    _rate_limit_acquire()

    # Monta query (categories=cat1&categories=cat2 — múltiplos pares)
    try:
        import httpx
    except ImportError:
        return _empty_result("httpx_missing")

    params: list[tuple[str, str]] = [
        ("url", canon),
        ("key", key),
        ("strategy", PSI_STRATEGY_MOBILE),
    ]
    for cat in PSI_CATEGORIES:
        params.append(("category", cat))

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(PSI_ENDPOINT, params=params)
    except httpx.TimeoutException:
        logger.info("PSI timeout %s", canon)
        return _empty_result("timeout")
    except Exception as exc:
        logger.warning("PSI request error %s: %s", canon, exc)
        return _empty_result(f"request_error:{type(exc).__name__}")

    if resp.status_code == 429:
        logger.warning("PSI quota exceeded (HTTP 429)")
        return _empty_result("quota")
    if resp.status_code >= 400:
        logger.warning("PSI HTTP %d %s — body=%s", resp.status_code, canon, resp.text[:200])
        return _empty_result(f"http_{resp.status_code}")

    try:
        body = resp.json()
    except Exception:
        return _empty_result("invalid_response")

    result = _parse_psi(body)
    result["reason"] = "ok"

    if use_cache and not result["low_confidence"]:
        _PSI_CACHE[canon] = (dict(result), time.time() + _PSI_CACHE_TTL)

    return result


def _parse_psi(body: dict) -> dict:
    """Extrai scores e Core Web Vitals do response JSON da PSI API."""
    result = _empty_result("ok")
    result["low_confidence"] = False

    lhr = body.get("lighthouseResult", {}) or {}
    categories = lhr.get("categories", {}) or {}

    def _score(cat_key: str) -> Optional[int]:
        c = categories.get(cat_key, {}) or {}
        s = c.get("score")
        if s is None:
            return None
        try:
            return int(round(float(s) * 100))
        except (TypeError, ValueError):
            return None

    result["psi_performance"] = _score("performance")
    result["psi_seo"] = _score("seo")
    result["psi_accessibility"] = _score("accessibility")
    result["psi_best_practices"] = _score("best-practices")

    # Mobile-friendly: deriva do best-practices viewport audit + responsive design.
    # PSI não tem "mobile_friendly" direto; usamos heurística viewport audit.
    audits = lhr.get("audits", {}) or {}
    viewport_audit = audits.get("viewport", {}) or {}
    vp_score = viewport_audit.get("score")
    if vp_score is not None:
        result["mobile_friendly"] = bool(vp_score >= 0.9)

    # LCP (Largest Contentful Paint) em segundos
    lcp_audit = audits.get("largest-contentful-paint", {}) or {}
    lcp_value = lcp_audit.get("numericValue")
    if isinstance(lcp_value, (int, float)):
        result["lcp"] = round(lcp_value / 1000.0, 2)  # ms → s

    # CLS (Cumulative Layout Shift)
    cls_audit = audits.get("cumulative-layout-shift", {}) or {}
    cls_value = cls_audit.get("numericValue")
    if isinstance(cls_value, (int, float)):
        result["cls"] = round(float(cls_value), 3)

    # Se TODAS as scores vieram None → response bagunçado, marca low-conf
    if all(result[k] is None for k in ("psi_performance", "psi_seo", "psi_accessibility", "psi_best_practices")):
        result["low_confidence"] = True
        result["reason"] = "all_scores_none"

    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="PageSpeed Insights audit (H2-F4)")
    ap.add_argument("--url", required=True, help="URL pra auditar")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    r = pagespeed_audit(args.url, use_cache=not args.no_cache)
    print(json.dumps(r, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
