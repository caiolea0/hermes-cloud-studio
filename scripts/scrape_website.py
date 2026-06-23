"""H2-F3 — Contact-Enrich via Website scraping (Tier 1: curl_cffi static).

Extrai contatos de websites de prospects:
  - Schema.org JSON-LD PRIMEIRO (LocalBusiness/Organization → telephone/email/sameAs/rating)
  - Fallback regex: telefones BR, emails, wa.me links, social hrefs

T2 (Patchright) gateado por FEATURE_SCRAPE_T2 (config.py, default off).
Roda na VPS/daemon — NUNCA em modo browser no PC.

Uso:
    python scripts/scrape_website.py --url https://exemplo.com.br
    python scripts/scrape_website.py --batch 20 --token <HERMES_VM_AUTH_TOKEN>
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import urllib.robotparser
import urllib.request
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger("hermes.scrape_website")

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

# Telefone BR: (65) 9 9999-9999 / +55 65 9999-9999 / 65999999999 etc.
_RE_PHONE_BR = re.compile(
    r"(?:\+?55\s*)?(?:\(?)(\d{2})(?:\)?)[\s\-\.]?(?:9[\s\-\.]?)?\d{4}[\s\-\.]?\d{4}(?!\d)"
)
_RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
# wa.me/5565... | api.whatsapp.com/send?phone=5565...
_RE_WA = re.compile(
    r"(?:wa\.me/|api\.whatsapp\.com/send[?][^\"'>\s]*?phone=)(\d+)", re.IGNORECASE
)
_RE_IG = re.compile(r"instagram\.com/([a-zA-Z0-9_.]{3,30})", re.IGNORECASE)
_RE_FB = re.compile(r"facebook\.com/([a-zA-Z0-9_.]{3,50})", re.IGNORECASE)

# False-positive guards — apenas endereços certamente inúteis (no-reply, placeholders)
_EMAIL_SKIP_NAMES = {"noreply", "no-reply", "donotreply", "do-not-reply",
                     "sentry", "example", "test", "email@email", "email@site"}
_EMAIL_SKIP_DOMAINS = {"sentry.io", "example.com"}
_IMG_EXTS = {".png", ".jpg", ".gif", ".svg", ".ico", ".webp", ".jpeg"}

_IG_SKIP_PATHS = {"p", "stories", "reel", "tv", "explore", "accounts", "sharer",
                  "hashtag", "direct"}
_FB_SKIP_PATHS = {"sharer", "plugins", "policy", "legal", "help", "login",
                  "dialog", "share", "photo", "pages", "events"}

# Pages to probe (relative paths, tried in order, max MAX_PAGES fetched)
_CONTACT_PATHS = ["/", "/contato", "/fale-conosco", "/sobre", "/contact", "/sobre-nos"]
TIMEOUT_SECS = 15
MAX_PAGES = 5
INTER_PAGE_DELAY = 1.0   # seconds between fetches of same domain


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_phone(raw: str) -> str:
    """Extrai apenas dígitos e normaliza para +55DDDDDDDDDDD."""
    digits = re.sub(r"\D", "", raw)
    if not digits.startswith("55") and len(digits) in (10, 11):
        digits = "55" + digits
    if len(digits) < 12 or len(digits) > 13:
        return ""
    return "+" + digits


def _clean_email(addr: str) -> Optional[str]:
    addr = addr.lower().strip()
    if "@" not in addr:
        return None
    name, domain = addr.rsplit("@", 1)
    if any(s in name for s in _EMAIL_SKIP_NAMES):
        return None
    if domain in _EMAIL_SKIP_DOMAINS:
        return None
    if Path(domain).suffix in _IMG_EXTS:
        return None
    return addr


# ---------------------------------------------------------------------------
# Schema.org JSON-LD extractor
# ---------------------------------------------------------------------------

def _extract_schema_org(html: str) -> dict:
    """Parse todos os blocos JSON-LD. Retorna campos de contato encontrados.

    Prioriza LocalBusiness/Organization mas aceita qualquer @type com telephone.
    Primeiro campo encontrado por tipo ganha (sem sobrescrever).
    """
    result: dict = {}

    for block in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE,
    ):
        try:
            data = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue

        # Normaliza: lista | @graph | objeto único
        nodes: list = []
        if isinstance(data, list):
            nodes = data
        elif isinstance(data, dict):
            nodes = data.get("@graph", [data])

        for node in nodes:
            if not isinstance(node, dict):
                continue

            t = str(node.get("@type", ""))

            # telephone
            tel_raw = node.get("telephone")
            if tel_raw and not result.get("phone"):
                norm = _normalize_phone(str(tel_raw))
                if norm:
                    result["phone"] = norm
                    result["has_schema_org"] = True

            # email
            em_raw = node.get("email")
            if em_raw and not result.get("email"):
                em = _clean_email(str(em_raw))
                if em:
                    result["email"] = em
                    result["has_schema_org"] = True

            # sameAs → social + WhatsApp
            same_as = node.get("sameAs", [])
            if isinstance(same_as, str):
                same_as = [same_as]
            for su in same_as:
                su = str(su)
                if "instagram.com" in su and not result.get("social_instagram"):
                    result["social_instagram"] = su.rstrip("/")
                    result["has_schema_org"] = True
                if "facebook.com" in su and not result.get("social_facebook"):
                    result["social_facebook"] = su.rstrip("/")
                    result["has_schema_org"] = True
                m = _RE_WA.search(su)
                if m and not result.get("whatsapp"):
                    wa = _normalize_phone(m.group(1))
                    if wa:
                        result["whatsapp"] = wa
                        result["has_schema_org"] = True

            # aggregateRating
            ar = node.get("aggregateRating", {})
            if isinstance(ar, dict) and "ratingValue" in ar and result.get("aggregate_rating") is None:
                try:
                    result["aggregate_rating"] = float(ar["ratingValue"])
                    result["has_schema_org"] = True
                except (TypeError, ValueError):
                    pass

    return result


# ---------------------------------------------------------------------------
# Regex fallback extractor
# ---------------------------------------------------------------------------

def _extract_regex(html: str, base_url: str) -> dict:
    """Regex fallbacks para campos não encontrados via schema.org."""
    result: dict = {}
    base_domain = urlparse(base_url).netloc.replace("www.", "").lower()

    # Telefone — prefere celular (11 dígitos) sobre fixo (10)
    phones_all, phones_mobile = [], []
    for m in _RE_PHONE_BR.finditer(html):
        norm = _normalize_phone(m.group(0))
        if not norm:
            continue
        digits = re.sub(r"\D", "", norm)
        phones_all.append(norm)
        if len(digits) == 13:  # +55 + DDD + 9 + 8 digits
            phones_mobile.append(norm)
    if phones_all:
        result["phone"] = (phones_mobile or phones_all)[0]

    # Email
    for m in _RE_EMAIL.finditer(html):
        em = _clean_email(m.group(0))
        if em:
            result["email"] = em
            break

    # WhatsApp
    for m in _RE_WA.finditer(html):
        wa = _normalize_phone(m.group(1))
        if wa:
            result["whatsapp"] = wa
            break

    # Instagram — pula handles que são subpaths do próprio domínio
    for m in _RE_IG.finditer(html):
        handle = m.group(1).lower()
        if handle in _IG_SKIP_PATHS:
            continue
        if base_domain and handle in base_domain:
            continue
        result["social_instagram"] = f"https://instagram.com/{m.group(1)}"
        break

    # Facebook
    for m in _RE_FB.finditer(html):
        handle = m.group(1).lower()
        if handle in _FB_SKIP_PATHS:
            continue
        result["social_facebook"] = f"https://facebook.com/{m.group(1)}"
        break

    return result


# ---------------------------------------------------------------------------
# Robots.txt checker
# ---------------------------------------------------------------------------

def _can_fetch(url: str) -> bool:
    """Checa robots.txt. Permite scraping se robots.txt inacessível."""
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        req = urllib.request.Request(
            robots_url,
            headers={"User-Agent": "HermesBot/2.0 (commercial leads enrichment)"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(content.splitlines())
        return rp.can_fetch("HermesBot", url)
    except Exception:
        return True  # permitir se robots.txt inacessível


# ---------------------------------------------------------------------------
# Public API: T1 scraper
# ---------------------------------------------------------------------------

def scrape_website(url: str, *, timeout: int = TIMEOUT_SECS) -> dict:
    """Tier 1 static scrape via curl_cffi (impersonate=chrome).

    Retorna dict com:
        phone, email, whatsapp, social_instagram, social_facebook,
        has_schema_org (bool), aggregate_rating (float|None), source_tier ('T1')

    Todos os campos são opcionais / None se não encontrado.
    Graceful em caso de falha: retorna dict mínimo sem lançar exceção.
    """
    result: dict = {
        "source_tier": "T1",
        "has_schema_org": False,
        "aggregate_rating": None,
    }

    try:
        from curl_cffi import requests as cffi_requests
    except ImportError:
        logger.warning("curl_cffi não instalado — T1 scrape indisponível. pip install curl_cffi>=0.7")
        result["source_tier"] = "T1_unavailable"
        return result

    # Normaliza URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    # robots.txt check no URL base
    if not _can_fetch(base + "/"):
        logger.info("scrape_website: robots.txt bloqueia %s", base)
        result["robots_blocked"] = True
        return result

    # Determina páginas a tentar
    entry_path = parsed.path or "/"
    other_paths = [p for p in _CONTACT_PATHS if p != entry_path]
    paths_to_try = [entry_path] + other_paths

    pages_html: list[str] = []
    fetched: set[str] = set()

    for path in paths_to_try[:MAX_PAGES]:
        if path in fetched:
            continue
        fetched.add(path)
        page_url = urljoin(base, path)

        try:
            resp = cffi_requests.get(
                page_url,
                impersonate="chrome",
                timeout=timeout,
                allow_redirects=True,
                max_redirects=3,
            )
            if resp.status_code == 200:
                ct = resp.headers.get("content-type", "text/html")
                if "text/html" in ct:
                    pages_html.append(resp.text)
                    logger.debug("scrape_website OK %s (%d bytes)", page_url, len(resp.text))
        except Exception as exc:
            logger.debug("scrape_website fetch %s: %s", page_url, exc)
            if path == entry_path:
                # Página principal falhou → aborta (site provavelmente down)
                break

        # Delay polido entre páginas do mesmo domínio
        if pages_html and len(paths_to_try) > 1:
            time.sleep(INTER_PAGE_DELAY)

    if not pages_html:
        logger.debug("scrape_website: nenhuma página HTML obtida de %s", url)
        return result

    # 1. Schema.org JSON-LD (prioridade máxima)
    for html in pages_html:
        sr = _extract_schema_org(html)
        for k, v in sr.items():
            if k not in result or result[k] is None or result[k] is False:
                result[k] = v

    # 2. Regex fallback para campos ainda ausentes
    combined = "\n".join(pages_html)
    rr = _extract_regex(combined, base)
    for k, v in rr.items():
        if not result.get(k):
            result[k] = v

    logger.info(
        "scrape_website %s → phone=%s email=%s wa=%s ig=%s schema_org=%s",
        base,
        bool(result.get("phone")),
        bool(result.get("email")),
        bool(result.get("whatsapp")),
        bool(result.get("social_instagram")),
        result.get("has_schema_org"),
    )
    return result


# ---------------------------------------------------------------------------
# Tier 2 stub (Patchright, VPS-only, FEATURE_SCRAPE_T2=off default)
# ---------------------------------------------------------------------------

def scrape_website_t2(url: str) -> dict:
    """T2: Patchright headless (VPS-only). Não implementado nesta fase.

    Só chamado se FEATURE_SCRAPE_T2=on e T1 retornou sem contatos.
    Raises NotImplementedError — caller trata graciosamente.
    """
    raise NotImplementedError(
        "T2 Patchright scrape pendente. Manter FEATURE_SCRAPE_T2=off (default)."
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Hermes H2-F3 website contact scraper (T1)")
    ap.add_argument("--url", help="URL para scraping direto")
    ap.add_argument("--name", default="?", help="Nome da empresa (log)")
    ap.add_argument("--batch", type=int, default=0,
                    help="Scrape top N prospects COM website e SEM phone via VM API")
    ap.add_argument("--vm-api", default="http://localhost:8420", dest="vm_api")
    ap.add_argument("--token", default="", help="HERMES_VM_AUTH_TOKEN")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    if args.url:
        logger.info("Scraping %s (%s)…", args.url, args.name)
        r = scrape_website(args.url)
        print(json.dumps(r, indent=2, ensure_ascii=False))
        return

    if args.batch:
        import os
        token = args.token or os.environ.get("HERMES_VM_AUTH_TOKEN", "")
        req = urllib.request.Request(
            f"{args.vm_api}/api/prospects?limit={args.batch * 3}&stage=discovered",
            headers={"X-Hermes-Token": token},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())

        # Prospects com site mas sem phone/email/whatsapp
        candidates = [
            p for p in data.get("prospects", [])
            if p.get("website") and not (p.get("phone") or p.get("email"))
        ][:args.batch]

        logger.info("Scraping %d prospects…", len(candidates))
        rows = []
        for p in candidates:
            r = scrape_website(p["website"])
            rows.append({
                "id": p["id"],
                "name": p.get("business_name") or p.get("name"),
                "site": p["website"],
                **r,
            })
            time.sleep(2)  # inter-prospect polite delay

        print(json.dumps(rows, indent=2, ensure_ascii=False))
        # Summary
        with_contact = sum(1 for r in rows if r.get("phone") or r.get("email") or r.get("whatsapp"))
        schema_org = sum(1 for r in rows if r.get("has_schema_org"))
        print(f"\n=== Summary ===")
        print(f"Scraped: {len(rows)} | With contact: {with_contact} ({100*with_contact//max(len(rows),1)}%) | Schema.org: {schema_org}")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
