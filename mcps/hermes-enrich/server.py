"""hermes-enrich MCP — FastMCP 3.0 para CNPJ lookup + validação.

H2-F2: expõe scripts/enrich_cnpj.py como tools MCP atrás do gateway.

Tools (2):
  1. cnpj_lookup(name, city, bairro?, phone?)
       → busca em cnpj.estabelecimentos via pg_trgm similarity
       → retorna {cnpj, razao_social, cnae, situacao_cadastral, confidence, similarity}
  2. cnpj_validate(cnpj)
       → valida CNPJ via BrasilAPI (no-key, best-effort)
       → retorna {razao_social, situacao_cadastral, cnae_fiscal, data_abertura, uf, municipio}

Run: python mcps/hermes-enrich/server.py  (cwd = repo root)
Port: 8802 (HERMES_ENRICH_PORT env para override)
Atrás do gateway (mcps/gateway) — NÃO expor diretamente.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_env_canonical() -> None:
    candidates = [Path.home() / ".hermes" / ".env", _REPO_ROOT / ".env"]
    for p in candidates:
        if not p.exists():
            continue
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip(); v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
            break
        except Exception:
            pass


_load_env_canonical()

import fastmcp  # noqa: E402

logger = logging.getLogger("hermes.mcp.enrich")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

mcp = fastmcp.FastMCP(
    name="hermes-enrich",
    version="1.0.0",
    description="CNPJ authority lookup e validação para prospects Hermes (Cuiabá/MT).",
)


@mcp.tool()
def cnpj_lookup(
    name: str,
    city: str = "Cuiabá",
    bairro: Optional[str] = None,
    phone: Optional[str] = None,
) -> dict:
    """Busca CNPJ na base Receita Federal (Cuiabá) via trigram similarity.

    Usa pg_trgm para fuzzy match em nome_fantasia + razao_social.
    Corrobora match via bairro ou telefone para reduzir falsos positivos.

    Returns:
        cnpj: CNPJ com 14 dígitos (sem pontuação) ou None
        razao_social: razão social oficial RF
        nome_fantasia: nome fantasia RF
        cnae: CNAE principal (7 dígitos)
        situacao_cadastral: '02'=Ativa, '08'=Baixada, etc.
        telefone1: telefone RF (formato +5565XXXXXXXX)
        confidence: 'high' (aceitar) | 'low' (não sobrescrever) | None (sem match)
        similarity: score 0.0-1.0
        candidates: top-5 candidatos para debug
    """
    from scripts.enrich_cnpj import cnpj_lookup as _lookup
    return _lookup(name=name, city=city, bairro=bairro, phone=phone)


@mcp.tool()
def cnpj_validate(cnpj: str) -> dict:
    """Valida e atualiza CNPJ via BrasilAPI (gratuito, sem chave).

    Retorna dados frescos da situação cadastral diretamente da Receita Federal.
    Rate-limit polite: mínimo 1.2s entre chamadas. 429/timeout = skip gracioso.

    Returns:
        cnpj: CNPJ normalizado 14 dígitos
        razao_social: razão social atual
        situacao_cadastral: texto da situação (ex: 'ATIVA', 'BAIXADA')
        cnae_fiscal: CNAE principal atual
        data_abertura: data de abertura (YYYY-MM-DD)
        municipio: município de registro
        uf: UF de registro
        ok: True se chamada bem-sucedida
        error: mensagem de erro se ok=False
    """
    from scripts.enrich_cnpj import cnpj_validate as _validate
    return _validate(cnpj=cnpj)


if __name__ == "__main__":
    port = int(os.environ.get("HERMES_ENRICH_PORT", "8802"))
    logger.info("hermes-enrich MCP iniciando na porta %d", port)
    mcp.run(transport="streamable-http", host="127.0.0.1", port=port)
