"""Tests H2-F4 — core/scoring.compute_needs_score determinism + edge cases."""
from __future__ import annotations

import pytest

from core.scoring import compute_needs_score, score_to_stage


# ---------- Determinismo ----------

def test_determinism_same_input_same_output():
    p = {"has_website": False, "business_name": "X"}
    a = compute_needs_score(p)
    b = compute_needs_score(p)
    assert a == b


# ---------- Casos canônicos ----------

def test_no_website_scores_high():
    r = compute_needs_score({"has_website": False, "business_name": "X"})
    assert r["score"] >= 30
    assert "no_website" in r["breakdown"]
    assert r["breakdown"]["no_website"] == 30


def test_polished_site_scores_low():
    r = compute_needs_score(
        {"has_website": True, "website": "https://ok.com",
         "social_instagram": "https://instagram.com/ok",
         "social_facebook": "https://facebook.com/ok"},
        web_signals={"exists": True, "ssl": True, "has_mobile_viewport": True},
        psi={"psi_performance": 92, "psi_seo": 95, "psi_accessibility": 92,
             "psi_best_practices": 95, "mobile_friendly": True, "low_confidence": False},
        schema={"has_schema_org": True, "aggregate_rating": 4.7, "review_count": 50},
    )
    assert r["score"] < 20
    assert r["confidence"] == "high"


def test_weak_site_mid_score():
    r = compute_needs_score(
        {"has_website": True, "website": "https://weak.com"},
        web_signals={"exists": True, "ssl": True, "has_mobile_viewport": False},
        psi={"psi_performance": 30, "psi_seo": 60, "psi_accessibility": 55,
             "psi_best_practices": 70, "mobile_friendly": False, "low_confidence": False},
        schema={"has_schema_org": False},
    )
    # PSI baixo (15+10+5) + not_mobile (10) + no_schema (10) + social_weak (10) = 60
    assert 50 <= r["score"] <= 75


def test_non_https_triggers_no_website():
    r = compute_needs_score(
        {"has_website": True, "website": "http://x.com"},
        web_signals={"exists": True, "ssl": False},
    )
    assert "no_website" in r["breakdown"]


# ---------- Confidence behavior ----------

def test_missing_psi_does_not_corrupt_score():
    """Sinal PSI ausente NÃO penaliza nem soma — caller decide se re-tenta."""
    r_with_psi = compute_needs_score(
        {"has_website": True, "website": "https://x.com"},
        web_signals={"exists": True, "ssl": True, "has_mobile_viewport": True},
        psi={"psi_performance": 80, "psi_seo": 80, "psi_accessibility": 80,
             "psi_best_practices": 80, "mobile_friendly": True, "low_confidence": False},
        schema={"has_schema_org": True, "aggregate_rating": 4.5},
    )
    r_no_psi = compute_needs_score(
        {"has_website": True, "website": "https://x.com"},
        web_signals={"exists": True, "ssl": True, "has_mobile_viewport": True},
        psi=None,
        schema={"has_schema_org": True, "aggregate_rating": 4.5},
    )
    # Quando PSI está ausente, sinais PSI viram missing — score igual (não somam nem subtraem)
    assert r_no_psi["score"] == r_with_psi["score"]
    # Mas confidence cai
    assert r_no_psi["confidence"] in ("partial", "high")


def test_psi_low_confidence_signals_missing():
    r = compute_needs_score(
        {"has_website": True, "website": "https://x.com"},
        web_signals={"exists": True, "ssl": True, "has_mobile_viewport": True},
        psi={"low_confidence": True, "reason": "quota"},
    )
    # PSI marcado low-conf → sinais PSI tratados como missing
    assert "psi_perf_low" in r["signals_missing"]


def test_no_website_psi_signals_na_not_missing():
    """Sem website, PSI é NA (não-aplicável) — confidence preserva."""
    r = compute_needs_score({"has_website": False, "business_name": "X"})
    assert "psi_perf_low" in r["signals_na"]
    assert "psi_perf_low" not in r["signals_missing"]


# ---------- Stage mapping ----------

def test_score_to_stage_thresholds():
    assert score_to_stage(0) == "discovered"
    assert score_to_stage(49) == "discovered"
    assert score_to_stage(50) == "qualified"
    assert score_to_stage(69) == "qualified"
    assert score_to_stage(70) == "audited"
    assert score_to_stage(100) == "audited"


def test_score_to_stage_low_confidence_downgrades():
    """Confidence='low' não promove pra 'audited' mesmo com score alto."""
    assert score_to_stage(85, "low") == "qualified"
    assert score_to_stage(85, "high") == "audited"


# ---------- Cap ----------

def test_score_capped_at_100():
    r = compute_needs_score(
        {"has_website": False},
        web_signals={"site_stale_2yr": True, "tech_outdated": True},
    )
    assert r["score"] <= 100


# ---------- Rating logic ----------

def test_rating_low_from_schema_org():
    r = compute_needs_score(
        {"has_website": True, "website": "https://x.com"},
        web_signals={"exists": True, "ssl": True, "has_mobile_viewport": True},
        psi={"psi_performance": 80, "psi_seo": 80, "psi_accessibility": 80,
             "psi_best_practices": 80, "mobile_friendly": True, "low_confidence": False},
        schema={"has_schema_org": True, "aggregate_rating": 3.2, "review_count": 25},
    )
    assert "rating_low" in r["breakdown"]


def test_rating_missing_is_missing_not_zero():
    r = compute_needs_score(
        {"has_website": True, "website": "https://x.com"},
        web_signals={"exists": True, "ssl": True, "has_mobile_viewport": True},
        psi={"psi_performance": 80, "psi_seo": 80, "psi_accessibility": 80,
             "psi_best_practices": 80, "mobile_friendly": True, "low_confidence": False},
        schema={"has_schema_org": True},  # sem aggregate_rating
    )
    assert "rating_low" not in r["breakdown"]
    assert "rating_low" in r["signals_missing"]


# ---------- Breakdown explainability ----------

def test_breakdown_is_dict_with_int_values():
    r = compute_needs_score({"has_website": False})
    assert isinstance(r["breakdown"], dict)
    assert all(isinstance(v, int) for v in r["breakdown"].values())


def test_sum_breakdown_equals_score():
    r = compute_needs_score(
        {"has_website": True, "website": "https://weak.com"},
        web_signals={"exists": True, "ssl": True, "has_mobile_viewport": False},
        psi={"psi_performance": 30, "psi_seo": 60, "psi_accessibility": 55,
             "psi_best_practices": 70, "mobile_friendly": False, "low_confidence": False},
        schema={"has_schema_org": False},
    )
    assert sum(r["breakdown"].values()) == r["score"]
