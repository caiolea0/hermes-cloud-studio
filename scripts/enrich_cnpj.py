"""H2-F2 — Enriquecimento CNPJ via hermes-postgres + BrasilAPI validation.

Expõe funções chamáveis de:
  - daemon/orchestrator.py (_enrich_single, via asyncio.to_thread)
  - mcps/hermes-enrich/server.py (tools cnpj_lookup + cnpj_validate)
  - CLI: python scripts/enrich_cnpj.py --name "Burger King" --bairro "Centro"

Lógica de match:
  - Trigram similarity >= 0.45 em nome_fantasia OU razao_social
  - Aceita se mesma bairro OU telefone/cep coincidem (reduz falsos positivos)
  - Ambíguo (top1-top2 sim muito próximos) → confidence='low', não sobrescreve

BrasilAPI: polite rate-limit 1s entre calls, best-effort (falha 429/timeout = skip).
"""
from __future__ import annotations

import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError
import json

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger("hermes.enrich_cnpj")

# Similarity mínima para aceitar match
SIM_THRESHOLD = 0.45
# Diferença mínima entre top1 e top2 pra não marcar como ambíguo
SIM_AMBIGUITY_DELTA = 0.08
# Cuiabá código RF (validado em load_cnpj_cuiaba.py)
# Será lido da tabela ou calculado; fallback hardcoded pra agilidade
CUIABA_RF_CODE_FALLBACK = 9067

BRASILAPI_BASE = "https://brasilapi.com.br/api/cnpj/v1"
_BRASILAPI_LAST_CALL = 0.0
BRASILAPI_MIN_INTERVAL = 1.2  # s entre chamadas (polite)


def _load_env() -> None:
    candidates = [Path.home() / ".hermes" / ".env", _ROOT / ".env"]
    for p in candidates:
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip(); v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
        break


def _pg_connect():
    import psycopg2
    host = os.environ.get("HERMES_PG_HOST", "hermes-postgres")
    port = int(os.environ.get("HERMES_PG_PORT", "5432"))
    user = os.environ.get("HERMES_PG_USER", "hermes")
    password = os.environ.get("HERMES_PG_PASSWORD", "")
    db = os.environ.get("HERMES_PG_DB", "hermes")
    # G5 fail-closed: senha vazia = config incompleta. Erro claro em vez de erro
    # psycopg2 cru (o container postgres tambem recusa subir sem senha).
    if not password:
        raise RuntimeError("HERMES_PG_PASSWORD nao configurado — enrich CNPJ abortado")
    return psycopg2.connect(
        host=host, port=port, user=user, password=password, dbname=db,
        connect_timeout=5,
    )


def _cuiaba_rf_code(conn) -> int:
    """Busca código RF de Cuiabá na tabela (ou retorna fallback)."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT municipio_rf FROM cnpj.estabelecimentos "
                "WHERE uf='MT' AND municipio_rf IS NOT NULL LIMIT 1"
            )
            row = cur.fetchone()
            if row:
                return row[0]
    except Exception:
        pass
    return CUIABA_RF_CODE_FALLBACK


def _normalize(s: str) -> str:
    """Remove acentos/caixa para comparação de bairro."""
    s = s.lower().strip()
    # remove pontuação simples
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _bairro_match(b1: Optional[str], b2: Optional[str]) -> bool:
    if not b1 or not b2:
        return False
    return _normalize(b1)[:12] == _normalize(b2)[:12]


def _phone_match(p1: Optional[str], p2: Optional[str]) -> bool:
    if not p1 or not p2:
        return False
    d1 = re.sub(r"\D", "", p1)[-8:]
    d2 = re.sub(r"\D", "", p2)[-8:]
    return bool(d1 and d2 and d1 == d2)


def cnpj_lookup(
    name: str,
    city: str = "Cuiabá",
    bairro: Optional[str] = None,
    phone: Optional[str] = None,
) -> dict:
    """Busca CNPJ no hermes-postgres via trigram similarity.

    Returns:
        {
            "cnpj": str | None,
            "razao_social": str | None,
            "cnae": str | None,
            "situacao_cadastral": str | None,
            "nome_fantasia": str | None,
            "telefone1": str | None,
            "confidence": "high" | "low" | None,
            "similarity": float,
            "candidates": list[dict],  # top-5 para debug
            "error": str | None,
        }
    """
    _load_env()
    empty = {
        "cnpj": None, "razao_social": None, "cnae": None,
        "situacao_cadastral": None, "nome_fantasia": None,
        "telefone1": None, "confidence": None, "similarity": 0.0,
        "candidates": [], "error": None,
    }
    try:
        conn = _pg_connect()
    except Exception as exc:
        return {**empty, "error": f"pg_connect falhou: {exc}"}

    try:
        cuiaba_code = _cuiaba_rf_code(conn)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    cnpj, razao_social, nome_fantasia, cnae_principal,
                    situacao_cadastral, telefone1, bairro, cep,
                    GREATEST(
                        similarity(public.immutable_unaccent(lower(nome_fantasia)),  public.immutable_unaccent(lower(%s))),
                        similarity(public.immutable_unaccent(lower(razao_social)),   public.immutable_unaccent(lower(%s)))
                    ) AS sim
                FROM cnpj.estabelecimentos
                WHERE municipio_rf = %s
                  AND (
                    public.immutable_unaccent(lower(nome_fantasia)) %% public.immutable_unaccent(lower(%s))
                    OR public.immutable_unaccent(lower(razao_social)) %% public.immutable_unaccent(lower(%s))
                  )
                ORDER BY sim DESC
                LIMIT 5
            """, (name, name, cuiaba_code, name, name))
            candidates = cur.fetchall()
    except Exception as exc:
        conn.close()
        return {**empty, "error": f"query falhou: {exc}"}
    finally:
        conn.close()

    if not candidates:
        return {**empty, "candidates": []}

    top = candidates[0]
    sim_top = float(top[8])

    cands_list = [
        {"cnpj": r[0], "razao_social": r[1], "nome_fantasia": r[2], "sim": float(r[8])}
        for r in candidates
    ]

    if sim_top < SIM_THRESHOLD:
        return {**empty, "candidates": cands_list}

    # Verifica se é ambíguo (top1 vs top2 muito próximos sem evidência corroborante)
    ambiguous = False
    if len(candidates) > 1:
        sim2 = float(candidates[1][8])
        if (sim_top - sim2) < SIM_AMBIGUITY_DELTA:
            ambiguous = True

    # Corroboração por bairro ou telefone reduz ambiguidade
    corroborated = (
        _bairro_match(bairro, top[6]) or
        _phone_match(phone, top[5])
    )

    if ambiguous and not corroborated:
        return {
            **empty,
            "confidence": "low",
            "similarity": sim_top,
            "candidates": cands_list,
            "cnpj": top[0],  # retorna o CNPJ mas com confidence=low
            "razao_social": top[1],
            "nome_fantasia": top[2],
        }

    return {
        "cnpj": top[0],
        "razao_social": top[1],
        "nome_fantasia": top[2],
        "cnae": top[3],
        "situacao_cadastral": top[4],
        "telefone1": top[5],
        "confidence": "high" if not ambiguous else "low",
        "similarity": sim_top,
        "candidates": cands_list,
        "error": None,
    }


def cnpj_validate(cnpj: str) -> dict:
    """Valida/atualiza situação cadastral via BrasilAPI (no-key, polite rate-limit).

    Returns:
        {
            "cnpj": str,
            "razao_social": str | None,
            "situacao_cadastral": str | None,
            "cnae_fiscal": str | None,
            "data_abertura": str | None,
            "municipio": str | None,
            "uf": str | None,
            "ok": bool,
            "error": str | None,
        }
    """
    global _BRASILAPI_LAST_CALL
    cnpj_clean = re.sub(r"\D", "", cnpj)
    if len(cnpj_clean) != 14:
        return {"cnpj": cnpj, "ok": False, "error": "CNPJ inválido (deve ter 14 dígitos)"}

    # Rate-limit polite
    since = time.time() - _BRASILAPI_LAST_CALL
    if since < BRASILAPI_MIN_INTERVAL:
        time.sleep(BRASILAPI_MIN_INTERVAL - since)

    url = f"{BRASILAPI_BASE}/{cnpj_clean}"
    try:
        req = Request(url, headers={"User-Agent": "HermesBot/2.0"})
        _BRASILAPI_LAST_CALL = time.time()
        with urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except URLError as exc:
        # 429 ou timeout — best-effort
        logger.info("BrasilAPI %s: %s (best-effort skip)", cnpj_clean, exc)
        return {"cnpj": cnpj_clean, "ok": False, "error": str(exc)}

    situacao = body.get("descricao_situacao_cadastral") or body.get("situacao_cadastral")
    return {
        "cnpj": cnpj_clean,
        "razao_social": body.get("razao_social"),
        "situacao_cadastral": situacao,
        "cnae_fiscal": body.get("cnae_fiscal_principal", {}).get("codigo") if isinstance(body.get("cnae_fiscal_principal"), dict) else body.get("cnae_fiscal_principal"),
        "data_abertura": body.get("data_inicio_atividade"),
        "municipio": body.get("municipio"),
        "uf": body.get("uf"),
        "ok": True,
        "error": None,
    }


def enrich_prospect_cnpj(prospect: dict) -> dict:
    """Enriquece um prospect com CNPJ via lookup + BrasilAPI.

    Retorna campos para PATCH em prospects:
        {"cnpj", "razao_social", "cnae", "situacao_cadastral",
         "cnpj_match_confidence", "fields_filled"}

    Confiança 'low' → retorna cnpj/razao_social mas NÃO sobrescreve outros campos.
    """
    name = prospect.get("business_name") or prospect.get("name", "")
    bairro = None
    phone = prospect.get("phone")
    address = prospect.get("address", "")
    if address:
        # Extrai bairro simples do endereço (após última vírgula)
        parts = address.split(",")
        if len(parts) >= 2:
            bairro = parts[-1].strip()

    if not name:
        return {"fields_filled": 0, "code": 400, "reason": "sem nome"}

    result = cnpj_lookup(name=name, bairro=bairro, phone=phone)

    if result.get("error"):
        return {"fields_filled": 0, "code": 503, "reason": result["error"]}

    if not result.get("cnpj"):
        return {"fields_filled": 0, "code": 204, "reason": "sem match"}

    confidence = result.get("confidence")
    cnpj = result["cnpj"]

    patch: dict = {
        "cnpj": cnpj,
        "cnpj_match_confidence": confidence,
    }

    # confidence='low' → apenas cnpj + confidence (não sobrescreve dados substantivos)
    if confidence == "high":
        if result.get("razao_social"):
            patch["razao_social"] = result["razao_social"]
        if result.get("cnae"):
            patch["cnae"] = result["cnae"]
        if result.get("situacao_cadastral"):
            patch["situacao_cadastral"] = result["situacao_cadastral"]

        # BrasilAPI: atualiza situação cadastral em tempo real (best-effort)
        try:
            validated = cnpj_validate(cnpj)
            if validated.get("ok") and validated.get("situacao_cadastral"):
                patch["situacao_cadastral"] = validated["situacao_cadastral"]
        except Exception as exc:
            logger.debug("BrasilAPI skip para %s: %s", cnpj, exc)

    return {**patch, "fields_filled": len(patch) - 1}  # -1: não conta cnpj_match_confidence


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enriquecimento CNPJ de um prospect")
    parser.add_argument("--name", required=True, help="Nome do negócio")
    parser.add_argument("--bairro", default="", help="Bairro para corroborar match")
    parser.add_argument("--phone", default="", help="Telefone para corroborar match")
    parser.add_argument("--validate-cnpj", default="", help="Valida CNPJ específico via BrasilAPI")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.validate_cnpj:
        result = cnpj_validate(args.validate_cnpj)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        result = cnpj_lookup(name=args.name, bairro=args.bairro or None, phone=args.phone or None)
        print(json.dumps({k: v for k, v in result.items() if k != "candidates"}, indent=2, ensure_ascii=False))
        if result["candidates"]:
            print("\nTop candidatos:")
            for c in result["candidates"]:
                print(f"  {c['cnpj']} | {c['razao_social'] or c['nome_fantasia']} | sim={c['sim']:.3f}")
