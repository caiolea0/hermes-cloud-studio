"""Web Audit Script — Hermes Pipeline Stage 3.

Audits a business's digital presence:
- Website existence & basic checks (SSL, mobile, speed)
- Social media presence (Instagram, Facebook)
- Google rating & reviews analysis
- Generates audit summary + score adjustment

Input: prospect dict (from DB or JSON)
Output: audit result dict with findings + recommended score
"""
import json
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

TIMEOUT = 10
USER_AGENT = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/130.0.0.0 Mobile Safari/537.36"


def audit_website(url: str) -> dict:
    """Check if website exists, SSL, response time, basic content analysis."""
    result = {
        "exists": False,
        "ssl": False,
        "response_time_ms": None,
        "status_code": None,
        "has_mobile_viewport": False,
        "has_whatsapp": False,
        "title": None,
        "issues": [],
    }

    if not url:
        result["issues"].append("Sem website")
        return result

    if not url.startswith("http"):
        url = "https://" + url

    try:
        start = time.monotonic()
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True, verify=False) as client:
            r = client.get(url, headers={"User-Agent": USER_AGENT})
        elapsed = round((time.monotonic() - start) * 1000)

        result["exists"] = True
        result["status_code"] = r.status_code
        result["response_time_ms"] = elapsed
        result["ssl"] = r.url.scheme == "https"

        html = r.text[:50000]

        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if title_match:
            result["title"] = title_match.group(1).strip()[:200]

        result["has_mobile_viewport"] = bool(re.search(r'<meta[^>]*viewport[^>]*width=device-width', html, re.IGNORECASE))
        result["has_whatsapp"] = bool(re.search(r'wa\.me|whatsapp|api\.whatsapp', html, re.IGNORECASE))

        if not result["ssl"]:
            result["issues"].append("Sem HTTPS/SSL")
        if elapsed > 3000:
            result["issues"].append(f"Site lento ({elapsed}ms)")
        if not result["has_mobile_viewport"]:
            result["issues"].append("Sem viewport mobile")
        if r.status_code >= 400:
            result["issues"].append(f"Erro HTTP {r.status_code}")

    except httpx.ConnectError:
        result["issues"].append("Site inacessível (conexão recusada)")
    except httpx.TimeoutException:
        result["issues"].append("Site inacessível (timeout)")
    except Exception as e:
        result["issues"].append(f"Erro ao acessar site: {type(e).__name__}")

    return result


def check_instagram(handle: str) -> dict:
    """Check if Instagram profile exists and is active."""
    result = {"exists": False, "url": None}
    if not handle:
        return result

    handle = handle.strip().lstrip("@").split("/")[-1].split("?")[0]
    url = f"https://www.instagram.com/{handle}/"

    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            r = client.get(url, headers={"User-Agent": USER_AGENT})
        if r.status_code == 200 and "login" not in str(r.url):
            result["exists"] = True
            result["url"] = url
    except Exception:
        pass

    return result


def check_facebook(handle: str) -> dict:
    """Check if Facebook page exists."""
    result = {"exists": False, "url": None}
    if not handle:
        return result

    handle = handle.strip().split("/")[-1].split("?")[0]
    url = f"https://www.facebook.com/{handle}/"

    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            r = client.get(url, headers={"User-Agent": USER_AGENT})
        if r.status_code == 200:
            result["exists"] = True
            result["url"] = url
    except Exception:
        pass

    return result


def search_social_media(business_name: str, city: str = "Cuiabá") -> dict:
    """Try to find social media by searching business name."""
    result = {"instagram_guess": None, "facebook_guess": None}

    slug = re.sub(r'[^a-z0-9]', '', business_name.lower().replace(" ", ""))

    possible_handles = [
        slug,
        slug + "oficial",
        slug + city.lower().replace("á", "a").replace(" ", ""),
    ]

    for handle in possible_handles[:2]:
        ig = check_instagram(handle)
        if ig["exists"]:
            result["instagram_guess"] = handle
            break

    return result


def calculate_score(prospect: dict, website_audit: dict, social: dict) -> int:
    """Calculate prospect score (0-100) based on digital presence gaps."""
    score = 50

    if not prospect.get("website") and not website_audit.get("exists"):
        score += 25
    elif website_audit.get("exists"):
        issues = website_audit.get("issues", [])
        score += len(issues) * 5
        if not website_audit.get("has_mobile_viewport"):
            score += 8
        if not website_audit.get("ssl"):
            score += 5
        if (website_audit.get("response_time_ms") or 0) > 3000:
            score += 5

    rating = prospect.get("google_rating") or 0
    reviews = prospect.get("google_reviews") or 0
    if rating >= 4.0 and reviews >= 10:
        score += 10
    elif rating >= 3.5:
        score += 5

    if not social.get("instagram_guess") and not prospect.get("social_instagram"):
        score += 5
    if not prospect.get("social_facebook"):
        score += 3

    high_value_categories = [
        "restaurante", "clínica", "salão", "beleza", "advocacia", "imobiliária",
        "academia", "pet", "odonto", "dentista", "médic", "constru", "arquitet",
        "contabil", "fotograf", "buffet", "escola", "cursos",
    ]
    category = (prospect.get("category") or "").lower()
    if any(kw in category for kw in high_value_categories):
        score += 8

    return min(100, max(0, score))


def generate_audit_summary(prospect: dict, website_audit: dict, social: dict, score: int) -> str:
    """Generate a human-readable audit summary in Portuguese."""
    name = prospect.get("business_name") or prospect.get("name", "Negócio")
    lines = [f"Auditoria digital: {name}"]

    if not website_audit.get("exists"):
        lines.append("- SEM WEBSITE: Oportunidade principal de venda")
    else:
        lines.append(f"- Website: {prospect.get('website', 'encontrado')}")
        for issue in website_audit.get("issues", []):
            lines.append(f"  - Problema: {issue}")

    rating = prospect.get("google_rating")
    reviews = prospect.get("google_reviews", 0)
    if rating:
        lines.append(f"- Google: {rating}/5 ({reviews} avaliações)")

    if prospect.get("social_instagram") or social.get("instagram_guess"):
        handle = prospect.get("social_instagram") or social.get("instagram_guess")
        lines.append(f"- Instagram: @{handle}")
    else:
        lines.append("- Instagram: Não encontrado")

    lines.append(f"- Score de oportunidade: {score}/100")

    if score >= 80:
        lines.append("=> ALTA PRIORIDADE: Prospect ideal para abordagem")
    elif score >= 60:
        lines.append("=> BOA OPORTUNIDADE: Vale abordagem personalizada")
    else:
        lines.append("=> BAIXA PRIORIDADE: Monitorar")

    return "\n".join(lines)


def audit_prospect(prospect: dict) -> dict:
    """Full audit pipeline for a single prospect."""
    website_audit = audit_website(prospect.get("website"))

    social = {}
    if not prospect.get("social_instagram"):
        bname = prospect.get("business_name") or prospect.get("name", "")
        social = search_social_media(bname, prospect.get("city", "Cuiabá"))

    score = calculate_score(prospect, website_audit, social)
    summary = generate_audit_summary(prospect, website_audit, social, score)

    return {
        "prospect_id": prospect.get("id"),
        "website_audit": website_audit,
        "social": social,
        "score": score,
        "audit_summary": summary,
        "audited_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        data = json.loads(sys.argv[1])
    else:
        data = json.load(sys.stdin)

    if isinstance(data, list):
        results = [audit_prospect(p) for p in data]
    else:
        results = audit_prospect(data)

    print(json.dumps(results, ensure_ascii=False, indent=2))
