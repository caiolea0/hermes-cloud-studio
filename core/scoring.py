"""H2-F4 — Score 0-100 "needs-our-services" para qualificar leads pra Vuecra/Geronimo.

Função pura, determinística, testável. NÚCLEO da fase F4.

Pesos canônicos (HERMES-2.0-PLAN §3):
    sem website / parked / non-HTTPS .......... +30
    PSI Performance < 50 ...................... +15
    PSI SEO < 70 .............................. +10
    PSI Accessibility < 70 .................... +5
    não mobile-friendly ....................... +10
    sem schema.org / sem aggregateRating ...... +10
    social fraco/ausente ...................... +10
    rating < 4.0 OU reviews < 10 .............. +10
    site stale (wayback 2+ anos) [OPCIONAL] ... +10 low-conf
    tech DIY/desatualizada [OPCIONAL] ......... +10 low-conf
    cap em 100.

Maior score = lead mais quente pra Vuecra/Geronimo.

CONFIANÇA — REGRA DE OURO:
    Sinais ausentes por ERRO (PSI timeout, scrape falhou) NÃO penalizam nem somam.
    Marcam confidence='partial'. Caller decide se re-tenta.
    Uma fonte quebrada NUNCA corrompe o score.

OUTPUT determinístico:
    {
      "score": int 0-100,
      "breakdown": {sinal_id: pontos, ...},  # auditável
      "confidence": "high" | "partial" | "low",
      "signals_present": list[str],   # sinais aplicados
      "signals_missing": list[str],   # sinais não-aplicados por dados ausentes
    }

Casos de teste (vide docstring de compute_needs_score):
    1. Sem site → score >= 30
    2. Site polido (PSI alto + schema.org + rating bom) → score baixo
    3. Site fraco (PSI 30, sem schema, sem mobile) → score ~ 30-50
    4. PSI ausente (None) NÃO penaliza — fica fora do breakdown
"""
from __future__ import annotations

from typing import Optional


# Mapa canônico de sinais. Cada entrada: (id, peso, descrição)
# IDs estáveis pra que o frontend possa renderizar tooltips por sinal.
_SIGNAL_WEIGHTS: dict[str, tuple[int, str]] = {
    "no_website": (30, "Sem website / não-HTTPS / parked"),
    "psi_perf_low": (15, "PageSpeed Performance < 50"),
    "psi_seo_low": (10, "PageSpeed SEO < 70"),
    "psi_a11y_low": (5, "PageSpeed Accessibility < 70"),
    "not_mobile": (10, "Não mobile-friendly"),
    "no_schema_org": (10, "Sem schema.org JSON-LD"),
    "social_weak": (10, "Social ausente / fraco"),
    "rating_low": (10, "Rating < 4.0 ou < 10 avaliações"),
    "site_stale": (10, "Site sem mudança há 2+ anos (Wayback)"),
    "tech_outdated": (10, "Tech DIY / desatualizada"),
}

# Sinais low-confidence — entram como bônus mas marcam o score como "partial"
# se forem os únicos sinais positivos (heurística pra evitar overconfidence).
_LOW_CONF_SIGNALS = {"site_stale", "tech_outdated"}


def _detect_no_website(prospect: dict, web_signals: dict) -> bool:
    """True se NÃO tem website, OU site não-HTTPS, OU site inacessível."""
    has_site = bool(prospect.get("has_website") or prospect.get("website"))
    if not has_site:
        return True
    # Site existe — checa se respondeu OK e tem SSL (web_audit fields)
    wa = web_signals or {}
    if wa.get("exists") is False:
        return True
    if wa.get("ssl") is False:
        return True
    return False


def _detect_mobile(psi: dict, web_signals: dict) -> Optional[bool]:
    """True se mobile-friendly, False se não, None se sinal ausente."""
    if psi and psi.get("mobile_friendly") is not None:
        return bool(psi["mobile_friendly"])
    if web_signals and web_signals.get("has_mobile_viewport") is not None:
        return bool(web_signals["has_mobile_viewport"])
    return None


def _detect_rating_low(prospect: dict, schema: dict) -> Optional[bool]:
    """True se rating < 4.0 OU reviews < 10.

    Fonte 1 (preferida): schema.org aggregateRating (própria página do negócio).
    Fonte 2: prospect.google_rating/google_reviews (Google Maps — pode estar ausente em
             Hermes 2.0 quando dropamos Google Maps).
    None se nenhum dado disponível.
    """
    rating = None
    reviews = None
    if schema:
        agg = schema.get("aggregate_rating")
        if isinstance(agg, (int, float)):
            rating = float(agg)
        # schema.org review_count se vier
        rc = schema.get("review_count")
        if isinstance(rc, (int, float)):
            reviews = int(rc)
    if rating is None and prospect.get("aggregate_rating") is not None:
        try:
            rating = float(prospect["aggregate_rating"])
        except (TypeError, ValueError):
            rating = None
    if rating is None and prospect.get("google_rating") is not None:
        try:
            rating = float(prospect["google_rating"])
        except (TypeError, ValueError):
            rating = None
    if reviews is None and prospect.get("google_reviews") is not None:
        try:
            reviews = int(prospect["google_reviews"])
        except (TypeError, ValueError):
            reviews = None

    if rating is None and reviews is None:
        return None
    if rating is not None and rating < 4.0:
        return True
    if reviews is not None and reviews < 10:
        return True
    return False


def _detect_social_weak(prospect: dict, scrape: dict) -> bool:
    """True se zero ou só 1 link social. Combina prospect + scrape (H2-F3)."""
    ig = prospect.get("social_instagram") or (scrape or {}).get("social_instagram")
    fb = prospect.get("social_facebook") or (scrape or {}).get("social_facebook")
    count = bool(ig) + bool(fb)
    return count < 2


def compute_needs_score(
    prospect: dict,
    web_signals: Optional[dict] = None,
    psi: Optional[dict] = None,
    social: Optional[dict] = None,
    schema: Optional[dict] = None,
) -> dict:
    """Computa score 0-100 "needs-our-services" + breakdown explicável.

    Args:
        prospect: dict do prospect (has_website, website, aggregate_rating, social_*, ...)
        web_signals: output de scripts.web_audit.audit_website (ssl, has_mobile_viewport, ...)
        psi: output de scripts.pagespeed.pagespeed_audit (psi_*, mobile_friendly, lcp, cls)
        social: output de scripts.web_audit.search_social_media (instagram_guess, ...)
        schema: output schema.org de scripts.scrape_website (aggregate_rating, has_schema_org, ...)

    Returns:
        {
          "score": int 0-100,
          "breakdown": {signal_id: points, ...},
          "confidence": "high" | "partial" | "low",
          "signals_present": [...],
          "signals_missing": [...],
        }

    Casos canônicos:
        >>> r = compute_needs_score({"has_website": False, "business_name": "X"})
        >>> r["score"] >= 30 and "no_website" in r["breakdown"]
        True

        >>> r = compute_needs_score(
        ...     {"has_website": True, "website": "https://x.com"},
        ...     web_signals={"exists": True, "ssl": True, "has_mobile_viewport": True},
        ...     psi={"psi_performance": 92, "psi_seo": 95, "psi_accessibility": 92,
        ...          "psi_best_practices": 95, "mobile_friendly": True, "low_confidence": False},
        ...     schema={"has_schema_org": True, "aggregate_rating": 4.7, "review_count": 50},
        ... )
        >>> r["score"] < 20
        True

    Determinístico: mesmo input → mesmo output. Pure function (sem I/O).
    """
    web_signals = web_signals or {}
    psi = psi or {}
    social = social or {}
    schema = schema or {}

    breakdown: dict[str, int] = {}
    signals_missing: list[str] = []
    signals_na: list[str] = []   # not-applicable (não conta contra confidence)

    # --- 1. Website (sinal mais forte) ---
    if _detect_no_website(prospect, web_signals):
        breakdown["no_website"] = _SIGNAL_WEIGHTS["no_website"][0]
        # Se não tem website, PSI/schema/mobile NÃO se aplicam (não-existência ≠ baixo)
        # Reportamos como NA (não missing por erro) — confidence preserva.
        signals_na.extend(["psi_perf_low", "psi_seo_low", "psi_a11y_low",
                           "not_mobile", "no_schema_org"])
        # social ainda relevante (negócio pode ter só Instagram)
        if _detect_social_weak(prospect, schema):
            breakdown["social_weak"] = _SIGNAL_WEIGHTS["social_weak"][0]
        # rating ainda relevante (Google Maps)
        rl = _detect_rating_low(prospect, schema)
        if rl is True:
            breakdown["rating_low"] = _SIGNAL_WEIGHTS["rating_low"][0]
        elif rl is None:
            signals_missing.append("rating_low")
    else:
        # Site existe — agora avalia qualidade
        # --- 2. PageSpeed Insights ---
        if psi and not psi.get("low_confidence", True):
            perf = psi.get("psi_performance")
            seo = psi.get("psi_seo")
            a11y = psi.get("psi_accessibility")
            if isinstance(perf, int) and perf < 50:
                breakdown["psi_perf_low"] = _SIGNAL_WEIGHTS["psi_perf_low"][0]
            elif perf is None:
                signals_missing.append("psi_perf_low")
            if isinstance(seo, int) and seo < 70:
                breakdown["psi_seo_low"] = _SIGNAL_WEIGHTS["psi_seo_low"][0]
            elif seo is None:
                signals_missing.append("psi_seo_low")
            if isinstance(a11y, int) and a11y < 70:
                breakdown["psi_a11y_low"] = _SIGNAL_WEIGHTS["psi_a11y_low"][0]
            elif a11y is None:
                signals_missing.append("psi_a11y_low")
        else:
            signals_missing.extend(["psi_perf_low", "psi_seo_low", "psi_a11y_low"])

        # --- 3. Mobile-friendly ---
        is_mobile = _detect_mobile(psi, web_signals)
        if is_mobile is False:
            breakdown["not_mobile"] = _SIGNAL_WEIGHTS["not_mobile"][0]
        elif is_mobile is None:
            signals_missing.append("not_mobile")

        # --- 4. schema.org ---
        has_schema = bool(schema.get("has_schema_org"))
        # Se TIVEMOS scrape (mesmo retornando sem schema) → sinal vale.
        # Se scrape NÃO rodou (schema={}), sinal é missing.
        if schema:  # scrape rodou
            if not has_schema:
                breakdown["no_schema_org"] = _SIGNAL_WEIGHTS["no_schema_org"][0]
        else:
            signals_missing.append("no_schema_org")

        # --- 5. Social ---
        if _detect_social_weak(prospect, schema):
            breakdown["social_weak"] = _SIGNAL_WEIGHTS["social_weak"][0]

        # --- 6. Rating ---
        rl = _detect_rating_low(prospect, schema)
        if rl is True:
            breakdown["rating_low"] = _SIGNAL_WEIGHTS["rating_low"][0]
        elif rl is None:
            signals_missing.append("rating_low")

    # --- 7. Sinais low-conf opcionais (entram só se caller mandou explicitamente) ---
    if web_signals.get("site_stale_2yr") is True:
        breakdown["site_stale"] = _SIGNAL_WEIGHTS["site_stale"][0]
    elif web_signals.get("site_stale_2yr") is None:
        signals_missing.append("site_stale")

    if web_signals.get("tech_outdated") is True:
        breakdown["tech_outdated"] = _SIGNAL_WEIGHTS["tech_outdated"][0]
    elif web_signals.get("tech_outdated") is None:
        signals_missing.append("tech_outdated")

    # --- Soma + cap ---
    raw_score = sum(breakdown.values())
    score = min(100, max(0, raw_score))

    # --- Confidence ---
    # Avaliáveis = total - NA. Cobertura = (presentes + avaliados-negativos) / avaliáveis.
    # high: ≥70% dos avaliáveis foram cobertos, ≤2 missing (por erro de coleta)
    # partial: 40-70% cobertos OU 3-4 missing
    # low: <40% cobertos OU só sinais low-conf bateram
    total_signals = len(_SIGNAL_WEIGHTS)
    evaluable = total_signals - len(signals_na)
    covered_evaluable = evaluable - len(signals_missing)
    coverage_ratio = (covered_evaluable / evaluable) if evaluable > 0 else 1.0

    only_lowconf_signals = bool(breakdown) and all(k in _LOW_CONF_SIGNALS for k in breakdown.keys())

    if only_lowconf_signals:
        confidence = "low"
    elif coverage_ratio >= 0.7 and len(signals_missing) <= 2:
        confidence = "high"
    elif coverage_ratio >= 0.4:
        confidence = "partial"
    else:
        confidence = "low"

    return {
        "score": score,
        "breakdown": breakdown,
        "confidence": confidence,
        "signals_present": list(breakdown.keys()),
        "signals_missing": signals_missing,
        "signals_na": signals_na,
    }


def score_to_stage(score: int, confidence: str = "high") -> str:
    """Mapeia score → stage do funil. Default: ≥70 audited, ≥50 qualified, < 50 discovered.

    Confidence 'low' rebaixa o limiar superior (não promove pra audited só com fraca evidência).
    """
    if confidence == "low" and score >= 70:
        return "qualified"  # rebaixa: não promove com confiança baixa
    if score >= 70:
        return "audited"
    if score >= 50:
        return "qualified"
    return "discovered"


# CLI quick check
if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        cases = [
            ("Sem website", {"has_website": False, "business_name": "A"}, {}, {}, {}, {}),
            ("Site polido", {"has_website": True, "website": "https://ok.com"},
             {"exists": True, "ssl": True, "has_mobile_viewport": True},
             {"psi_performance": 92, "psi_seo": 95, "psi_accessibility": 92,
              "psi_best_practices": 95, "mobile_friendly": True, "low_confidence": False},
             {}, {"has_schema_org": True, "aggregate_rating": 4.7, "review_count": 50}),
            ("Site fraco", {"has_website": True, "website": "https://weak.com"},
             {"exists": True, "ssl": True, "has_mobile_viewport": False},
             {"psi_performance": 30, "psi_seo": 60, "psi_accessibility": 55,
              "psi_best_practices": 70, "mobile_friendly": False, "low_confidence": False},
             {}, {"has_schema_org": False}),
        ]
        for name, prospect, web, psi, soc, sch in cases:
            r = compute_needs_score(prospect, web_signals=web, psi=psi, social=soc, schema=sch)
            print(f"\n=== {name} ===")
            print(json.dumps(r, indent=2, ensure_ascii=False))
    else:
        print("Usage: python core/scoring.py demo")
