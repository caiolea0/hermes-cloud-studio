"""Tests H2-F4 — scripts.classify_prospect rule-based determinism + ICP signals."""
from __future__ import annotations

from scripts.classify_prospect import (
    classify_prospect,
    _match_cnae,
    _match_osm_category,
    _normalize_cnae,
    _adjust_icp_by_signals,
)


# ---------- Determinismo ----------

def test_classify_deterministic_no_ollama():
    p = {"cnae": "5611201", "business_name": "Restaurante X"}
    a = classify_prospect(p, use_ollama=False)
    b = classify_prospect(p, use_ollama=False)
    assert a == b


# ---------- CNAE prefix matching ----------

def test_cnae_full_match_specific_subcategory():
    """CNAE 8630501 (odontologia) deve bater sub-category exato, não fallback /86."""
    r = _match_cnae("8630501")
    assert r is not None
    industry, sub, _ = r
    assert industry == "saude"
    assert sub == "odontologia"


def test_cnae_partial_match_falls_back_to_prefix():
    """CNAE 8690000 (saúde outros) deve bater no prefixo /86."""
    r = _match_cnae("8690000")
    assert r is not None
    industry, _, _ = r
    assert industry == "saude"


def test_cnae_normalize_strips_punctuation():
    assert _normalize_cnae("86.10-1/01") == "8610101"
    assert _normalize_cnae(None) == ""
    assert _normalize_cnae("") == ""


def test_cnae_no_match_returns_none():
    assert _match_cnae("9999999") is None


def test_classify_restaurante_high_icp():
    r = classify_prospect(
        {"cnae": "5611201", "business_name": "Restaurante X"},
        use_ollama=False,
    )
    assert r["industry"] == "alimentacao"
    assert r["sub_category"] == "restaurante"
    assert r["icp_fit"] == "high"
    assert r["source"] == "rule_cnae"


def test_classify_hospital_low_icp():
    r = classify_prospect(
        {"cnae": "8610000", "business_name": "Hospital Y"},
        use_ollama=False,
    )
    assert r["icp_fit"] == "low"
    assert r["industry"] == "saude"


# ---------- OSM category fallback ----------

def test_osm_category_match_without_cnae():
    r = classify_prospect(
        {"cnae": "", "category": "restaurant", "business_name": "X"},
        use_ollama=False,
    )
    assert r["source"] == "rule_category"
    assert r["industry"] == "alimentacao"
    assert r["icp_fit"] == "high"


def test_osm_category_dentist():
    r = classify_prospect(
        {"category": "dentist", "business_name": "Clinica X"},
        use_ollama=False,
    )
    assert r["sub_category"] == "odontologia"


def test_osm_low_icp_category_townhall():
    r = classify_prospect(
        {"category": "townhall", "business_name": "Prefeitura"},
        use_ollama=False,
    )
    assert r["icp_fit"] == "low"
    assert r["industry"] == "publico"


# ---------- ICP signal adjustments ----------

def test_no_website_boosts_medium_to_high():
    # CNAE 4754 (móveis/decoração) é "high"; testando com algo "medium" — supermercado (4711)
    r = classify_prospect(
        {"cnae": "4711300", "business_name": "Mercadinho X"},
        use_ollama=False,
    )
    # Supermercado = medium por default; sem website empurra pra high
    assert r["icp_fit"] == "high"


def test_situacao_baixada_forces_low():
    icp = _adjust_icp_by_signals("high", {"situacao_cadastral": "BAIXADA"})
    assert icp == "low"


def test_sa_corporation_downgrades():
    icp = _adjust_icp_by_signals("high", {"razao_social": "EMPRESA GRANDE S.A."})
    assert icp == "medium"
    icp_low = _adjust_icp_by_signals("low", {"razao_social": "OUTRA S/A"})
    assert icp_low == "low"


# ---------- Fallback ----------

def test_fallback_returns_outros_when_no_signals():
    r = classify_prospect({"business_name": "Negócio Sem Dados"}, use_ollama=False)
    assert r["source"] == "fallback"
    assert r["industry"] == "outros"
    assert r["icp_fit"] == "medium"  # neutro até PSI/sinais


# ---------- Output schema ----------

def test_output_has_required_fields():
    r = classify_prospect({"cnae": "5611201"}, use_ollama=False)
    for k in ("industry", "sub_category", "icp_fit", "rationale", "source"):
        assert k in r, f"missing key: {k}"
    assert r["icp_fit"] in ("high", "medium", "low")
