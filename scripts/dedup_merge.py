"""H2-F4 — Dedup + merge golden-record por fuzzy match.

Detecta prospects que são o MESMO negócio em linhas distintas (vindos de Overpass+CNPJ+scrape)
e marca/mergeia mantendo a linha de maior completude.

Estratégia (determinística):
    1. Bucket por cidade — pares só consideram prospects da mesma city.
    2. Pra cada par no bucket:
       a. Pula se um deles tem CNPJ e o outro tem CNPJ DIFERENTE.
       b. Score de similaridade = nome (fuzzy rapidfuzz) + phone (last8 digits match)
          + address (token overlap) + cnpj (exato se ambos têm).
       c. Threshold score ≥ 75 → marca como duplicate candidate.
    3. Merge: linha "vencedora" = mais campos preenchidos (completeness count).
       Outra linha vira 'duplicate_of=winner_id' (stage='duplicate').

Uso (CLI dry-run):
    python scripts/dedup_merge.py --dry-run --city Cuiaba

Apply mode:
    python scripts/dedup_merge.py --apply --city Cuiaba --vm-api http://localhost:8420 --token <TOKEN>

Falha gracefully se rapidfuzz não instalado (fallback similaridade simples).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger("hermes.dedup_merge")

# Threshold de score combinado pra marcar como duplicata
DUP_SCORE_THRESHOLD = 75

# Pesos por sinal
W_NAME = 50
W_PHONE = 25
W_ADDRESS = 15
W_CNPJ = 30  # bônus se CNPJ exato


def _normalize_name(s: str) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    # Remove sufixos corporativos comuns que diferenciam só na forma
    for tail in (" ltda", " me", " eireli", " sa", " s a", " epp"):
        if s.endswith(tail):
            s = s[: -len(tail)].strip()
    return s


def _normalize_phone(s: str) -> str:
    if not s:
        return ""
    digits = re.sub(r"\D", "", s)
    return digits[-10:]  # DDD + 8 dígitos (cobre fixo e móvel)


def _normalize_address(s: str) -> set[str]:
    if not s:
        return set()
    tokens = re.findall(r"\w+", s.lower())
    return {t for t in tokens if len(t) >= 4}


def _name_similarity(a: str, b: str) -> float:
    """0.0 - 1.0. Usa rapidfuzz token_set_ratio se disponível; fallback sequencematcher."""
    a = _normalize_name(a)
    b = _normalize_name(b)
    if not a or not b:
        return 0.0
    try:
        from rapidfuzz import fuzz
        return fuzz.token_set_ratio(a, b) / 100.0
    except ImportError:
        from difflib import SequenceMatcher
        return SequenceMatcher(None, a, b).ratio()


def _pair_score(a: dict, b: dict) -> tuple[int, list[str]]:
    """Calcula score 0-100 de similaridade entre dois prospects + razões.

    Razões = lista curta de sinais que bateram (audit-friendly).
    """
    reasons: list[str] = []
    score = 0

    # CNPJ exato bate alto, mas se diferentes ZERA tudo (decisivo)
    cnpj_a = (a.get("cnpj") or "").strip()
    cnpj_b = (b.get("cnpj") or "").strip()
    if cnpj_a and cnpj_b:
        if cnpj_a == cnpj_b:
            score += W_CNPJ
            reasons.append("cnpj_exact")
        else:
            return (0, ["cnpj_mismatch"])

    # Nome fuzzy
    name_sim = _name_similarity(
        a.get("business_name") or a.get("name") or "",
        b.get("business_name") or b.get("name") or "",
    )
    if name_sim >= 0.85:
        score += W_NAME
        reasons.append(f"name~{name_sim:.2f}")
    elif name_sim >= 0.70:
        score += int(W_NAME * 0.6)
        reasons.append(f"name~{name_sim:.2f}")

    # Phone last10 digits
    pa, pb = _normalize_phone(a.get("phone") or ""), _normalize_phone(b.get("phone") or "")
    if pa and pb and pa == pb:
        score += W_PHONE
        reasons.append("phone_match")

    # Address token overlap
    aa, ab = _normalize_address(a.get("address") or ""), _normalize_address(b.get("address") or "")
    if aa and ab:
        overlap = len(aa & ab)
        if overlap >= 3:
            score += W_ADDRESS
            reasons.append(f"address~{overlap}tok")
        elif overlap >= 2:
            score += int(W_ADDRESS * 0.6)
            reasons.append(f"address~{overlap}tok")

    return (score, reasons)


def _completeness(p: dict) -> int:
    """Conta campos não-vazios — vencedor do merge tem mais."""
    fields = ("phone", "email", "whatsapp", "website", "cnpj", "razao_social", "cnae",
              "address", "social_instagram", "social_facebook", "industry", "icp_fit",
              "aggregate_rating", "score", "audit_summary")
    return sum(1 for f in fields if p.get(f))


def find_duplicates(db_path: str, city_filter: Optional[str] = None) -> list[dict]:
    """Query DB local + retorna lista de pares duplicate candidates.

    Returns: [{a_id, b_id, score, reasons, a_complete, b_complete, winner_id, loser_id}]
    """
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        sql = """
            SELECT id, name, business_name, city, phone, email, whatsapp, address,
                   website, cnpj, razao_social, cnae, social_instagram, social_facebook,
                   industry, icp_fit, aggregate_rating, score, audit_summary, stage
              FROM prospects
             WHERE (stage IS NULL OR stage != 'duplicate')
        """
        params: list = []
        if city_filter:
            sql += " AND lower(city) = lower(?)"
            params.append(city_filter)
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    # Bucket por cidade
    buckets: dict[str, list[dict]] = {}
    for r in rows:
        d = dict(r)
        key = (d.get("city") or "").strip().lower()
        buckets.setdefault(key, []).append(d)

    pairs: list[dict] = []
    for city, prospects in buckets.items():
        n = len(prospects)
        if n < 2:
            continue
        # Pares O(n²) — Cuiabá tem ~3k atualmente, mas só após dedup. Aceitável.
        for i in range(n):
            for j in range(i + 1, n):
                a, b = prospects[i], prospects[j]
                score, reasons = _pair_score(a, b)
                if score >= DUP_SCORE_THRESHOLD:
                    ca, cb = _completeness(a), _completeness(b)
                    winner, loser = (a, b) if ca >= cb else (b, a)
                    pairs.append({
                        "a_id": a["id"], "b_id": b["id"],
                        "a_name": a.get("business_name") or a.get("name"),
                        "b_name": b.get("business_name") or b.get("name"),
                        "score": score,
                        "reasons": reasons,
                        "a_complete": ca, "b_complete": cb,
                        "winner_id": winner["id"], "loser_id": loser["id"],
                    })
    return pairs


def apply_merge(db_path: str, pairs: list[dict]) -> int:
    """Marca os 'loser' como stage='duplicate' + notes='duplicate_of=<winner_id>'.

    Não MERGE field-by-field (conservador). Loser fica searchable mas oculto do funil.
    Returns: contagem de merges aplicados.
    """
    if not pairs:
        return 0
    conn = sqlite3.connect(db_path, timeout=10.0)
    try:
        merged = 0
        for p in pairs:
            note = f"H2-F4 dedup: duplicate_of={p['winner_id']} score={p['score']} reasons={p['reasons']}"
            conn.execute(
                "UPDATE prospects SET stage='duplicate', notes=COALESCE(notes,'') || ? "
                "WHERE id=? AND (stage IS NULL OR stage != 'duplicate')",
                (f"\n{note}", p["loser_id"]),
            )
            merged += 1
        conn.commit()
        return merged
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="H2-F4 dedup + merge golden-record")
    ap.add_argument("--db", default="hermes_local.db", help="caminho SQLite local")
    ap.add_argument("--city", default="", help="filtra por cidade (default: todas)")
    ap.add_argument("--dry-run", action="store_true", help="Lista pares mas não persiste")
    ap.add_argument("--apply", action="store_true", help="Persiste merges no DB")
    ap.add_argument("--max", type=int, default=50, help="máx de pares listados")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    if not args.dry_run and not args.apply:
        ap.error("escolha --dry-run ou --apply")

    db_path = args.db
    if not os.path.exists(db_path):
        ap.error(f"DB não encontrado: {db_path}")

    pairs = find_duplicates(db_path, city_filter=args.city or None)
    pairs.sort(key=lambda x: -x["score"])

    print(f"\n=== {len(pairs)} pares duplicate candidates encontrados ===")
    for p in pairs[: args.max]:
        print(f"  [{p['score']:>3}] {p['a_name']!r} (id={p['a_id']}, complete={p['a_complete']})")
        print(f"        ≈ {p['b_name']!r} (id={p['b_id']}, complete={p['b_complete']})")
        print(f"        reasons={p['reasons']} winner={p['winner_id']} loser={p['loser_id']}")

    if args.apply and pairs:
        merged = apply_merge(db_path, pairs)
        print(f"\n→ {merged} merges aplicados (loser → stage='duplicate')")


if __name__ == "__main__":
    main()
