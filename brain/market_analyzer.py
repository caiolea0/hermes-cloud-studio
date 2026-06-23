"""H2-F7 — Market Analyzer.

Aggregates CNAE density, churn velocity, new-registration velocity and
opportunity scores over cnpj.estabelecimentos (hermes-postgres).
Writes results to cnpj.market_signals (UPSERT, idempotent).

RF situacao_cadastral codes: '02'=ATIVA '03'=SUSPENSA '04'=INAPTA '08'=BAIXADA.
Churn  = situacao ∈ ('03','04','08') AND data_situacao >= now-24mo.
New-reg = data_abertura >= now-12mo AND situacao='02'.

Deterministic: no randomness, no side-effects besides market_signals writes.
All SQL is parametrized. Running twice produces identical rows (truncate-replace).

LLM labels: optional, gated by HERMES_MARKET_LLM=1 (default off = rule-based only).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger("hermes.market_analyzer")

# RF code for Cuiabá (confirmed in H2-F2)
CUIABA_RF_CODE = "9067"

# Situações que indicam encerramento / problema
CHURN_SITUACOES = ["03", "04", "08"]

# Opportunity score weights (rule-based formula, documented)
#  new_reg (growth signal)  → most positive weight
#  density low (whitespace) → reward: 1 - norm_density
#  churn (ambiguous)        → lower weight (can mean need OR risk)
#  icp_bonus               → vertical fit in Cuiabá services market
_W_NEW_REG = 2.0
_W_DENSITY_LOW = 1.5
_W_CHURN = 0.8

# ICP-fit bonus by CNAE 2-digit prefix (Cuiabá services market focus)
_ICP_CNAE_PREFIXES: Dict[str, int] = {
    "56": 15,   # Alimentacao (restaurantes, lanchonetes)
    "47": 10,   # Comercio varejista
    "86": 12,   # Saude (clinicas, consultorios)
    "55": 10,   # Alojamento (hoteis, pousadas)
    "96": 8,    # Servicos pessoais (salao, clinica estetica)
    "43": 8,    # Servicos de construcao especializados
    "45": 8,    # Comercio e reparacao veiculos
    "49": 8,    # Transporte terrestre
    "74": 5,    # Atividades profissionais, cientificas
    "73": 5,    # Publicidade e pesquisa de mercado
    "85": 5,    # Educacao
}


# ---------------------------------------------------------------------------
# Connection helper (mirrors scripts/enrich_cnpj.py pattern)
# ---------------------------------------------------------------------------

def _pg_connect():
    import psycopg2
    host = os.environ.get("HERMES_PG_HOST", "hermes-postgres")
    port = int(os.environ.get("HERMES_PG_PORT", "5432"))
    user = os.environ.get("HERMES_PG_USER", "hermes")
    password = os.environ.get("HERMES_PG_PASSWORD", "")
    db = os.environ.get("HERMES_PG_DB", "hermes")
    if not password:
        raise RuntimeError(
            "HERMES_PG_PASSWORD nao configurado — market_analyzer abortado"
        )
    return psycopg2.connect(
        host=host, port=port, user=user, password=password, dbname=db,
        connect_timeout=5,
    )


# ---------------------------------------------------------------------------
# Schema bootstrap (idempotent)
# ---------------------------------------------------------------------------

def _ensure_market_signals_table(conn) -> None:
    """Create cnpj.market_signals if not exists. Idempotent."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cnpj.market_signals (
                id         SERIAL PRIMARY KEY,
                signal_type TEXT NOT NULL,
                cnae        CHAR(7),
                cnae_label  TEXT,
                region      TEXT,
                metric_value NUMERIC,
                rank        INT,
                meta        JSONB,
                computed_at TIMESTAMPTZ DEFAULT now()
            )
        """)
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_market_signals_type_cnae_region
            ON cnpj.market_signals(signal_type, COALESCE(cnae,''), COALESCE(region,''))
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_market_signals_type_rank
            ON cnpj.market_signals(signal_type, rank)
        """)
    conn.commit()


# ---------------------------------------------------------------------------
# Signal computations (pure SQL, parametrized, deterministic)
# ---------------------------------------------------------------------------

def compute_density(conn, limit: int = 50) -> List[Dict]:
    """Top CNAEs by ATIVAS count in Cuiabá (mercado vivo, não defuntos).

    Rankeia por estabelecimentos ATIVOS (situacao='02') — o RF dump tem ~44%
    baixadas/inaptas que NÃO são mercado real pra prospecção. Exclui CNAE
    placeholder '8888888' (sem CNAE definido). `total` fica no meta p/ referência.
    High density (ativas) = saturado (competição). Low = whitespace = oportunidade.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                cnae_principal                                        AS cnae,
                COUNT(*) FILTER (WHERE situacao_cadastral = '02')    AS ativas,
                COUNT(*)                                              AS total,
                RANK() OVER (
                    ORDER BY COUNT(*) FILTER (WHERE situacao_cadastral = '02') DESC
                )::int                                                AS rank
            FROM cnpj.estabelecimentos
            WHERE municipio_rf = %s
              AND cnae_principal IS NOT NULL
              AND cnae_principal NOT IN ('0000000', '8888888')
            GROUP BY cnae_principal
            ORDER BY ativas DESC
            LIMIT %s
        """, (CUIABA_RF_CODE, limit))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def compute_churn_velocity(conn, months: int = 24, limit: int = 50) -> List[Dict]:
    """Top CNAEs by churn count (situacao ∈ 03/04/08) in last N months.

    High churn = vertical em declínio OU negócios que precisam de ajuda urgente.
    data_situacao is stored as CHAR(8) 'YYYYMMDD' in RF CSV.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=30 * months)
    cutoff_str = cutoff.strftime("%Y%m%d")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                cnae_principal                            AS cnae,
                COUNT(*)                                  AS churn_count,
                RANK() OVER (ORDER BY COUNT(*) DESC)::int AS rank
            FROM cnpj.estabelecimentos
            WHERE municipio_rf = %s
              AND cnae_principal IS NOT NULL
              AND cnae_principal NOT IN ('0000000', '8888888')
              AND situacao_cadastral = ANY(%s)
              AND data_situacao >= %s
            GROUP BY cnae_principal
            ORDER BY churn_count DESC
            LIMIT %s
        """, (CUIABA_RF_CODE, CHURN_SITUACOES, cutoff_str, limit))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def compute_new_reg_velocity(conn, months: int = 12, limit: int = 50) -> List[Dict]:
    """Top CNAEs by new active registrations in last N months.

    High velocity = vertical em crescimento → novas empresas precisam de
    site/marketing = lead quente para Vuecra.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=30 * months)
    cutoff_str = cutoff.strftime("%Y%m%d")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                cnae_principal                            AS cnae,
                COUNT(*)                                  AS new_count,
                RANK() OVER (ORDER BY COUNT(*) DESC)::int AS rank
            FROM cnpj.estabelecimentos
            WHERE municipio_rf = %s
              AND cnae_principal IS NOT NULL
              AND cnae_principal NOT IN ('0000000', '8888888')
              AND situacao_cadastral = '02'
              AND data_abertura >= %s
            GROUP BY cnae_principal
            ORDER BY new_count DESC
            LIMIT %s
        """, (CUIABA_RF_CODE, cutoff_str, limit))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def compute_heatmap(conn) -> List[Dict]:
    """CNAE × bairro density matrix for heatmap visualization.

    Top 20 CNAEs (by total count) × all bairros with ≥1 estabelecimento.
    Returns flat list; caller pivots to matrix as needed.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT cnae_principal FROM cnpj.estabelecimentos
            WHERE municipio_rf = %s
              AND cnae_principal IS NOT NULL
              AND cnae_principal NOT IN ('0000000', '8888888')
              AND situacao_cadastral = '02'
            GROUP BY cnae_principal
            ORDER BY COUNT(*) DESC
            LIMIT 20
        """, (CUIABA_RF_CODE,))
        top_cnaes = [r[0] for r in cur.fetchall()]

        if not top_cnaes:
            return []

        cur.execute("""
            SELECT cnae_principal AS cnae,
                   bairro,
                   COUNT(*) AS count
            FROM cnpj.estabelecimentos
            WHERE municipio_rf = %s
              AND cnae_principal = ANY(%s)
              AND situacao_cadastral = '02'
              AND bairro IS NOT NULL
              AND bairro <> ''
            GROUP BY cnae_principal, bairro
            ORDER BY count DESC
        """, (CUIABA_RF_CODE, top_cnaes))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Opportunity score (rule-based, deterministic)
# ---------------------------------------------------------------------------

def _icp_bonus(cnae: str) -> int:
    """ICP-fit bonus by CNAE 2-digit prefix."""
    prefix2 = (cnae or "")[:2]
    return _ICP_CNAE_PREFIXES.get(prefix2, 0)


def compute_opportunity_scores(
    density: List[Dict],
    new_reg: List[Dict],
    churn: List[Dict],
    limit: int = 50,
) -> List[Dict]:
    """Opportunity score per CNAE (rule-based, deterministic).

    Formula:
      score = W_NEW_REG  * norm_new_reg
            + W_DENSITY_LOW * (1 - norm_density)   # reward whitespace
            + W_CHURN * norm_churn                 # churn = need signal
            + icp_bonus / 100.0                    # 0-0.15 contribution

    Normalized: rank-based inverse where rank=1 → norm=1.0, rank=N → norm≈0.
    icp_bonus: 0-15 points from _ICP_CNAE_PREFIXES (scaled to 0.0-0.15).
    """
    n_new = max(len(new_reg), 1)
    n_den = max(len(density), 1)
    n_chu = max(len(churn), 1)

    new_map = {r["cnae"]: r for r in new_reg}
    den_map = {r["cnae"]: r for r in density}
    chu_map = {r["cnae"]: r for r in churn}

    all_cnaes = set(new_map) | set(den_map) | set(chu_map)
    scores = []

    for cnae in all_cnaes:
        nr = new_map.get(cnae, {})
        de = den_map.get(cnae, {})
        ch = chu_map.get(cnae, {})

        nr_rank = int(nr.get("rank", n_new))
        de_rank = int(de.get("rank", n_den))
        ch_rank = int(ch.get("rank", n_chu))

        norm_new = 1.0 - (nr_rank - 1) / n_new
        norm_den = 1.0 - (de_rank - 1) / n_den
        norm_chu = 1.0 - (ch_rank - 1) / n_chu

        icp = _icp_bonus(cnae)
        score = (
            _W_NEW_REG * norm_new
            + _W_DENSITY_LOW * (1.0 - norm_den)
            + _W_CHURN * norm_chu
            + icp / 100.0
        )

        scores.append({
            "cnae": cnae,
            "opportunity_score": round(score, 4),
            "new_count": int(nr.get("new_count") or 0),
            "total": int(de.get("total") or 0),
            "churn_count": int(ch.get("churn_count") or 0),
            "icp_bonus": icp,
        })

    scores.sort(key=lambda x: x["opportunity_score"], reverse=True)
    for i, s in enumerate(scores, 1):
        s["rank"] = i
    return scores[:limit]


# ---------------------------------------------------------------------------
# LLM labels (optional, HERMES_MARKET_LLM=1)
# ---------------------------------------------------------------------------

def _try_label_signal(cnae: str, signal_type: str, metric_value: float) -> str:
    """Generate human-readable label via Ollama (gated). Returns empty string if off/unavailable."""
    if os.environ.get("HERMES_MARKET_LLM", "0") != "1":
        return ""
    try:
        from linkedin.ollama_router import router as ollama_router
        import asyncio

        prompt = (
            f"CNAE {cnae} — vertical de negócios. "
            f"Sinal: {signal_type}, valor: {metric_value:.1f}. "
            "Gere um rótulo em PT-BR de 1 linha descrevendo o vertical e o sinal. "
            "Máximo 80 caracteres. Responda APENAS o rótulo, sem aspas."
        )

        loop = asyncio.new_event_loop()
        label = loop.run_until_complete(
            ollama_router.route("classify", prompt, options={"temperature": 0, "num_predict": 60})
        )
        loop.close()
        return str(label).strip()[:120]
    except Exception as exc:
        logger.debug("_try_label_signal skipped (LLM unavailable): %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Persistence helper
# ---------------------------------------------------------------------------

def _upsert_signals(conn, rows: List[Dict], signal_type: str, metric_key: str) -> int:
    """Truncate-replace signal_type rows and reinsert. Returns count written."""
    if not rows:
        return 0

    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM cnpj.market_signals WHERE signal_type = %s",
            (signal_type,),
        )
        for r in rows:
            cnae = r.get("cnae") or ""
            metric_value = float(r.get(metric_key) or 0)
            rank = int(r.get("rank") or 0)
            region = r.get("region", "cuiaba") or "cuiaba"

            cnae_label = _try_label_signal(cnae, signal_type, metric_value)

            # Build meta without large redundant keys
            meta = {
                k: (float(v) if hasattr(v, "__float__") and not isinstance(v, (int, float)) else v)
                for k, v in r.items()
                if k not in ("cnae", "region", "rank")
            }

            cur.execute("""
                INSERT INTO cnpj.market_signals
                    (signal_type, cnae, cnae_label, region, metric_value, rank, meta, computed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, now())
            """, (
                signal_type,
                cnae or None,
                cnae_label or None,
                region,
                metric_value,
                rank,
                json.dumps(meta),
            ))

    conn.commit()
    return len(rows)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_market_analysis(limit_per_signal: int = 50) -> Dict[str, Any]:
    """Full market analysis pipeline. Deterministic, idempotent.

    Connects to hermes-postgres → computes 4 signals → writes to cnpj.market_signals.
    Returns summary dict.

    Raises on PG connection failure (caller must handle gracefully).
    """
    conn = _pg_connect()
    try:
        _ensure_market_signals_table(conn)

        density = compute_density(conn, limit=limit_per_signal)
        churn = compute_churn_velocity(conn, limit=limit_per_signal)
        new_reg = compute_new_reg_velocity(conn, limit=limit_per_signal)
        opportunity = compute_opportunity_scores(density, new_reg, churn, limit=limit_per_signal)

        n_den = _upsert_signals(conn, density, "density", "ativas")
        n_chu = _upsert_signals(conn, churn, "churn_velocity", "churn_count")
        n_new = _upsert_signals(conn, new_reg, "new_reg_velocity", "new_count")
        n_opp = _upsert_signals(conn, opportunity, "opportunity", "opportunity_score")

        total = n_den + n_chu + n_new + n_opp
        logger.info(
            "market_analyzer done: density=%d churn=%d new_reg=%d opportunity=%d total=%d",
            n_den, n_chu, n_new, n_opp, total,
        )

        return {
            "total_signals": total,
            "density_count": n_den,
            "churn_velocity_count": n_chu,
            "new_reg_velocity_count": n_new,
            "opportunity_count": n_opp,
            "top5_density": density[:5],
            "top5_churn": churn[:5],
            "top5_new_reg": new_reg[:5],
            "top5_opportunity": opportunity[:5],
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os as _os
    from pathlib import Path as _Path

    _env = _Path.home() / ".hermes" / ".env"
    if _env.exists():
        for _line in _env.read_text().splitlines():
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _v = _line.split("=", 1)
            _k = _k.strip(); _v = _v.strip().strip('"').strip("'")
            if _k and _k not in _os.environ:
                _os.environ[_k] = _v

    logging.basicConfig(level=logging.INFO)
    import pprint
    result = run_market_analysis()
    pprint.pprint(result)
