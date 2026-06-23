"""H2-F4 — Categorize + ICP fit (rule-based CNAE prefix + Ollama fallback ambíguo).

Dado um prospect (cnae + business_name + category OSM), retorna:
    {
      "industry": str,        # ex: "saude", "alimentacao", "varejo"
      "sub_category": str,    # ex: "odontologia", "restaurante", "loja_roupas"
      "icp_fit": str,         # "high" | "medium" | "low"
      "rationale": str,       # 1 frase explicando a decisão (auditoria)
      "source": str,          # "rule_cnae" | "rule_category" | "ollama" | "fallback"
    }

ICP = Ideal Customer Profile do ecossistema Vuecra/Geronimo:
    - PME local (não multinacional) que precisa de site/design/marketing.
    - Sinais "high": sem website / site fraco; pequena/média escala; categoria com
      ROI claro pra Vuecra (clínica, restaurante, varejo, serviço local).
    - Sinais "low": grande corporação, órgão público, atividade não-comercial
      (sindicato, religião), ou setor onde site = irrelevante (ambulante, MEI puro).

Lógica:
    1. Mapa de prefixos CNAE (Receita Federal) → industry+sub. Determinístico.
    2. Se CNAE ausente OU mapa não cobre → tenta categoria OSM.
    3. Se ainda ambíguo → Ollama (classify task, temp=0, JSON-schema-strict).
       Se Ollama down/timeout/JSON inválido → fallback "outros" + icp_fit="medium" low-confidence.

JSON schema do Ollama (output esperado):
    {"industry": str, "sub_category": str, "icp_fit": "high"|"medium"|"low",
     "rationale": str}

Uso:
    from scripts.classify_prospect import classify_prospect
    result = classify_prospect({
        "cnae": "5611201",
        "business_name": "Restaurante do João",
        "category": "restaurant",
    })

CLI:
    python scripts/classify_prospect.py --cnae 8630501 --name "Clinica X"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger("hermes.classify_prospect")


# ---------------------------------------------------------------------------
# Mapa CNAE → (industry, sub_category, default_icp_fit)
#
# CNAE 2.3 — só prefixos suficientes pra desambiguar.
# Match: maior prefixo bate primeiro. NÃO sobrescreve sub_category mais específico.
# Fontes: Receita Federal classe CNAE + alinhado a ICP Vuecra (PME local sem/com site fraco).
# ---------------------------------------------------------------------------

# Estrutura: prefixo_cnae → (industry, sub_category, icp_fit_default)
_CNAE_MAP: tuple[tuple[str, str, str, str], ...] = (
    # === Saúde ===
    ("8610", "saude", "hospital", "low"),       # hospital grande — raramente ICP
    ("86301", "saude", "clinica", "high"),      # ativ médica ambulatorial
    ("86304", "saude", "fisioterapia", "high"),
    ("86305", "saude", "psicologia", "high"),
    ("86306", "saude", "fonoaudiologia", "high"),
    ("8630501", "saude", "odontologia", "high"),
    ("8630502", "saude", "odontologia_especializada", "high"),
    ("86", "saude", "outros", "high"),

    # === Alimentação ===
    ("5611201", "alimentacao", "restaurante", "high"),
    ("5611202", "alimentacao", "churrascaria", "high"),
    ("5611203", "alimentacao", "lanchonete", "high"),
    ("5611204", "alimentacao", "bar", "medium"),
    ("5611205", "alimentacao", "restaurante_self_service", "high"),
    ("5612", "alimentacao", "ambulante", "low"),
    ("5620", "alimentacao", "buffet_catering", "high"),
    ("56", "alimentacao", "outros", "high"),

    # === Varejo ===
    ("4711", "varejo", "supermercado", "medium"),
    ("4721", "varejo", "padaria", "high"),
    ("4729", "varejo", "alimentos_outros", "high"),
    ("4751", "varejo", "informatica", "high"),
    ("4754", "varejo", "moveis_decoracao", "high"),
    ("4755", "varejo", "tecidos", "medium"),
    ("4761", "varejo", "livraria_papelaria", "high"),
    ("4763", "varejo", "brinquedos_jogos", "high"),
    ("4771", "varejo", "farmacia", "high"),
    ("4772", "varejo", "cosmeticos", "high"),
    ("4774", "varejo", "otica", "high"),
    ("4781", "varejo", "roupas_acessorios", "high"),
    ("4782", "varejo", "calcados", "high"),
    ("4783", "varejo", "joalheria_relojoaria", "high"),
    ("4789", "varejo", "outros", "high"),
    ("47", "varejo", "outros", "high"),

    # === Veículos / Automotivo ===
    ("4511", "automotivo", "concessionaria", "medium"),
    ("4520", "automotivo", "oficina_mecanica", "high"),
    ("4530", "automotivo", "auto_pecas", "high"),
    ("4541", "automotivo", "motocicletas", "medium"),
    ("45", "automotivo", "outros", "high"),

    # === Beleza & Estética ===
    ("9602", "beleza", "salao_barbearia", "high"),
    ("9609", "beleza", "estetica_spa", "high"),

    # === Educação ===
    ("8511", "educacao", "infantil_fundamental", "medium"),
    ("8513", "educacao", "ensino_medio", "medium"),
    ("8520", "educacao", "tecnico_profissionalizante", "high"),
    ("8531", "educacao", "ensino_superior", "low"),
    ("8550", "educacao", "atividades_apoio_educacao", "high"),
    ("8591", "educacao", "cursos_livres", "high"),
    ("8592", "educacao", "cultural_arte", "high"),
    ("8593", "educacao", "idiomas", "high"),
    ("8599", "educacao", "outros", "high"),
    ("85", "educacao", "outros", "medium"),

    # === Serviços Profissionais B2B ===
    ("6911", "servicos", "advocacia", "high"),
    ("6912", "servicos", "cartorio", "low"),
    ("6920", "servicos", "contabilidade", "high"),
    ("7020", "servicos", "consultoria_gestao", "high"),
    ("7110", "servicos", "engenharia_arquitetura", "high"),
    ("7111", "servicos", "arquitetura", "high"),
    ("7112", "servicos", "engenharia", "high"),
    ("7311", "servicos", "publicidade_propaganda", "high"),
    ("7410", "servicos", "design_especializado", "high"),
    ("7420", "servicos", "fotografia", "high"),
    ("7490", "servicos", "tecnico_outros", "high"),

    # === Construção / Imobiliário ===
    ("4110", "imobiliario", "incorporacao", "medium"),
    ("4120", "construcao", "construcao_edificios", "medium"),
    ("4399", "construcao", "obras_outros", "high"),
    ("6810", "imobiliario", "compra_venda_aluguel", "high"),
    ("6821", "imobiliario", "intermediacao", "high"),
    ("41", "construcao", "outros", "medium"),
    ("43", "construcao", "outros", "high"),

    # === Pet ===
    ("4789004", "pet", "pet_shop", "high"),
    ("7500", "pet", "veterinaria", "high"),

    # === Esporte/Lazer ===
    ("9311", "lazer", "academia_esporte", "high"),
    ("9312", "lazer", "clube_esportivo", "high"),
    ("9319", "lazer", "esportivo_outros", "high"),
    ("9329", "lazer", "outros", "medium"),

    # === Hospedagem ===
    ("5510", "hospedagem", "hotel", "high"),
    ("5590", "hospedagem", "outros", "high"),

    # === Indústria / Atacado (geralmente low ICP — B2B já tem cadeia) ===
    ("10", "industria", "alimentos", "low"),
    ("13", "industria", "textil", "low"),
    ("14", "industria", "vestuario", "low"),
    ("25", "industria", "metalurgia", "low"),
    ("46", "atacado", "outros", "low"),

    # === Setor público / sindical (não-ICP) ===
    ("84", "publico", "administracao_publica", "low"),
    ("94", "associativo", "sindicato_associacao", "low"),
    ("9491", "associativo", "religioso", "low"),

    # === Agropecuária ===
    ("01", "agro", "agricultura_pecuaria", "medium"),
    ("02", "agro", "florestal", "low"),
)


# Categoria OSM (`amenity`/`shop`/`craft`) → fallback quando CNAE não disponível
_OSM_CATEGORY_MAP: dict[str, tuple[str, str, str]] = {
    # Alimentação
    "restaurant": ("alimentacao", "restaurante", "high"),
    "fast_food": ("alimentacao", "lanchonete", "high"),
    "cafe": ("alimentacao", "cafeteria", "high"),
    "bar": ("alimentacao", "bar", "medium"),
    "pub": ("alimentacao", "bar", "medium"),
    "ice_cream": ("alimentacao", "sorveteria", "high"),
    "bakery": ("varejo", "padaria", "high"),
    # Saúde
    "clinic": ("saude", "clinica", "high"),
    "doctors": ("saude", "consultorio_medico", "high"),
    "dentist": ("saude", "odontologia", "high"),
    "veterinary": ("pet", "veterinaria", "high"),
    "pharmacy": ("varejo", "farmacia", "high"),
    "hospital": ("saude", "hospital", "low"),
    # Varejo
    "clothes": ("varejo", "roupas_acessorios", "high"),
    "shoes": ("varejo", "calcados", "high"),
    "jewelry": ("varejo", "joalheria_relojoaria", "high"),
    "optician": ("varejo", "otica", "high"),
    "books": ("varejo", "livraria_papelaria", "high"),
    "stationery": ("varejo", "livraria_papelaria", "high"),
    "toys": ("varejo", "brinquedos_jogos", "high"),
    "cosmetics": ("varejo", "cosmeticos", "high"),
    "supermarket": ("varejo", "supermercado", "medium"),
    "convenience": ("varejo", "conveniencia", "high"),
    "computer": ("varejo", "informatica", "high"),
    "furniture": ("varejo", "moveis_decoracao", "high"),
    # Beleza
    "hairdresser": ("beleza", "salao_barbearia", "high"),
    "beauty": ("beleza", "estetica_spa", "high"),
    "massage": ("beleza", "estetica_spa", "high"),
    # Automotivo
    "car_repair": ("automotivo", "oficina_mecanica", "high"),
    "car_parts": ("automotivo", "auto_pecas", "high"),
    "car": ("automotivo", "concessionaria", "medium"),
    "tyres": ("automotivo", "pneus", "high"),
    # Pet
    "pet": ("pet", "pet_shop", "high"),
    # Hospedagem
    "hotel": ("hospedagem", "hotel", "high"),
    "guest_house": ("hospedagem", "pousada", "high"),
    "hostel": ("hospedagem", "hostel", "high"),
    # Esporte
    "fitness_centre": ("lazer", "academia_esporte", "high"),
    "gym": ("lazer", "academia_esporte", "high"),
    # Educação
    "school": ("educacao", "infantil_fundamental", "medium"),
    "kindergarten": ("educacao", "infantil_fundamental", "high"),
    "language_school": ("educacao", "idiomas", "high"),
    "music_school": ("educacao", "cursos_livres", "high"),
    # Profissionais
    "lawyer": ("servicos", "advocacia", "high"),
    "accountant": ("servicos", "contabilidade", "high"),
    "estate_agent": ("imobiliario", "intermediacao", "high"),
    "architect": ("servicos", "arquitetura", "high"),
    # Setor público (low ICP)
    "townhall": ("publico", "administracao_publica", "low"),
    "police": ("publico", "seguranca", "low"),
    "fire_station": ("publico", "seguranca", "low"),
    "courthouse": ("publico", "justica", "low"),
    "place_of_worship": ("associativo", "religioso", "low"),
}


def _normalize_cnae(cnae: Optional[str]) -> str:
    """Remove pontuação, mantém só dígitos. Retorna string vazia se inválido."""
    if not cnae:
        return ""
    return re.sub(r"\D", "", str(cnae))


def _match_cnae(cnae_clean: str) -> Optional[tuple[str, str, str]]:
    """Retorna (industry, sub_category, default_icp) do maior prefixo CNAE que bate."""
    if not cnae_clean:
        return None
    # Itera ordenado pelo tamanho descendente do prefixo → match mais específico ganha
    sorted_map = sorted(_CNAE_MAP, key=lambda x: -len(x[0]))
    for prefix, industry, sub, icp in sorted_map:
        if cnae_clean.startswith(prefix):
            return (industry, sub, icp)
    return None


def _match_osm_category(category: Optional[str]) -> Optional[tuple[str, str, str]]:
    """Retorna (industry, sub_category, default_icp) baseado no tag OSM amenity/shop/craft."""
    if not category:
        return None
    cat_clean = category.strip().lower()
    return _OSM_CATEGORY_MAP.get(cat_clean)


def _adjust_icp_by_signals(default_icp: str, prospect: dict) -> str:
    """Ajusta icp_fit baseado em sinais de PME local (sem site = high, grande = low).

    Sinais positivos (high boost):
      - sem website (E-commerce/serviço online ausente)
    Sinais negativos (low push):
      - razão social com 'S.A.', 'SA ', 'LTDA' grande não é sinal forte (LTDA é PME comum no BR);
      - 'S.A.' OU situação 'BAIXADA'/'SUSPENSA' = empresa morta/grande corp.

    Mantém conservador — não rebaixa high pra low sem evidência forte.
    """
    icp = default_icp
    has_website = bool(prospect.get("website") or prospect.get("has_website"))
    razao = (prospect.get("razao_social") or "").upper()
    situacao = (prospect.get("situacao_cadastral") or "").upper()

    # Sinais negativos fortes — empresa fora do ICP de PME ativa
    if situacao in ("BAIXADA", "SUSPENSA", "INAPTA", "NULA"):
        return "low"
    if " S.A" in razao or "S/A" in razao or "SOCIEDADE ANONIMA" in razao:
        # S.A. costuma ser empresa grande — rebaixa apenas se default não era já high
        if icp == "high":
            return "medium"
        return "low"

    # Sinal positivo: sem website é exatamente o lead pra Vuecra
    if not has_website and icp == "medium":
        return "high"

    return icp


def classify_prospect(prospect: dict, *, use_ollama: bool = True) -> dict:
    """Classifica industry/sub_category/icp_fit. Sempre retorna dict válido (graceful).

    Args:
        prospect: dict com {cnae, business_name, category, website, razao_social, ...}
        use_ollama: se False, pula fallback LLM (testes determinísticos).

    Returns:
        {industry, sub_category, icp_fit, rationale, source}
    """
    cnae_clean = _normalize_cnae(prospect.get("cnae"))
    cnae_match = _match_cnae(cnae_clean)

    if cnae_match:
        industry, sub, default_icp = cnae_match
        icp = _adjust_icp_by_signals(default_icp, prospect)
        return {
            "industry": industry,
            "sub_category": sub,
            "icp_fit": icp,
            "rationale": f"CNAE {cnae_clean[:7]} → {industry}/{sub}; ajuste sinais={icp}",
            "source": "rule_cnae",
        }

    osm_match = _match_osm_category(prospect.get("category"))
    if osm_match:
        industry, sub, default_icp = osm_match
        icp = _adjust_icp_by_signals(default_icp, prospect)
        return {
            "industry": industry,
            "sub_category": sub,
            "icp_fit": icp,
            "rationale": f"OSM cat={prospect.get('category')} → {industry}/{sub}",
            "source": "rule_category",
        }

    # Ambíguo — tenta Ollama (sync wrapper p/ ser callable de qualquer contexto)
    if use_ollama:
        ollama_result = _classify_via_ollama(prospect)
        if ollama_result:
            return ollama_result

    # Fallback final
    return {
        "industry": "outros",
        "sub_category": "indefinido",
        "icp_fit": "medium",
        "rationale": "sem CNAE / sem categoria OSM / Ollama indisponível",
        "source": "fallback",
    }


_PROMPT_TEMPLATE = """Classifique este negócio brasileiro. RESPONDA SÓ JSON, sem texto antes/depois.

Negócio: {business_name}
Categoria OSM (se houver): {category}
CNAE (se houver): {cnae}
Razão social (se houver): {razao_social}
Cidade: {city}

Schema da resposta:
{{"industry": "saude|alimentacao|varejo|servicos|beleza|automotivo|educacao|hospedagem|lazer|pet|construcao|imobiliario|industria|atacado|publico|associativo|agro|outros",
 "sub_category": "<string snake_case curto>",
 "icp_fit": "high|medium|low",
 "rationale": "<1 frase curta>"}}

ICP "high" = PME local que precisa de site/design/marketing.
ICP "low" = grande corporação, órgão público, ou setor onde site é irrelevante.

JSON:"""


def _classify_via_ollama(prospect: dict) -> Optional[dict]:
    """Chama Ollama (qwen2.5:3b classify task) via linkedin/ollama_router.

    Retorna None se Ollama down/timeout/JSON inválido (caller usa fallback).
    Determinístico: temp=0.
    """
    try:
        from linkedin.ollama_router import router as ollama_router, OllamaUnavailable
    except Exception as exc:
        logger.debug("classify_via_ollama: ollama_router import falhou: %s", exc)
        return None

    prompt = _PROMPT_TEMPLATE.format(
        business_name=prospect.get("business_name") or prospect.get("name") or "?",
        category=prospect.get("category") or "?",
        cnae=prospect.get("cnae") or "?",
        razao_social=prospect.get("razao_social") or "?",
        city=prospect.get("city") or "Cuiabá",
    )

    try:
        # Executa sync em event loop dedicado (callable de thread / from-CLI / from-asyncio.to_thread)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Já em loop — só pode rodar via asyncio.to_thread no caller
                logger.debug("classify_via_ollama chamado em loop ativo — caller deve usar wrapper async")
                return None
        except RuntimeError:
            pass
        raw = asyncio.run(_ollama_call(prompt))
    except OllamaUnavailable as exc:
        logger.info("classify_via_ollama: ollama indisponível: %s", exc)
        return None
    except Exception as exc:
        logger.warning("classify_via_ollama: erro inesperado: %s", exc)
        return None

    return _parse_ollama_response(raw)


async def _ollama_call(prompt: str) -> str:
    from linkedin.ollama_router import router as ollama_router
    return await ollama_router.route(
        "classify", prompt,
        options={"temperature": 0.0, "num_predict": 200},
    )


def _parse_ollama_response(raw: str) -> Optional[dict]:
    """Extrai JSON da resposta do Ollama. Rejeita se schema inválido."""
    if not raw:
        return None
    # Tenta extrair primeiro bloco JSON (Ollama às vezes preâmbulo)
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None

    industry = (data.get("industry") or "").strip().lower()
    sub = (data.get("sub_category") or "").strip().lower()
    icp = (data.get("icp_fit") or "").strip().lower()
    rationale = (data.get("rationale") or "").strip()[:200]

    if not industry or not sub or icp not in ("high", "medium", "low"):
        return None

    return {
        "industry": industry,
        "sub_category": sub,
        "icp_fit": icp,
        "rationale": rationale or "via ollama",
        "source": "ollama",
    }


async def classify_prospect_async(prospect: dict) -> dict:
    """Versão async pra ser chamada do daemon (event loop ativo).

    Mesmo fluxo: rule-based primeiro, Ollama só se ambíguo.
    """
    cnae_clean = _normalize_cnae(prospect.get("cnae"))
    cnae_match = _match_cnae(cnae_clean)
    if cnae_match:
        industry, sub, default_icp = cnae_match
        icp = _adjust_icp_by_signals(default_icp, prospect)
        return {
            "industry": industry, "sub_category": sub, "icp_fit": icp,
            "rationale": f"CNAE {cnae_clean[:7]} → {industry}/{sub}",
            "source": "rule_cnae",
        }

    osm_match = _match_osm_category(prospect.get("category"))
    if osm_match:
        industry, sub, default_icp = osm_match
        icp = _adjust_icp_by_signals(default_icp, prospect)
        return {
            "industry": industry, "sub_category": sub, "icp_fit": icp,
            "rationale": f"OSM cat={prospect.get('category')} → {industry}/{sub}",
            "source": "rule_category",
        }

    prompt = _PROMPT_TEMPLATE.format(
        business_name=prospect.get("business_name") or prospect.get("name") or "?",
        category=prospect.get("category") or "?",
        cnae=prospect.get("cnae") or "?",
        razao_social=prospect.get("razao_social") or "?",
        city=prospect.get("city") or "Cuiabá",
    )
    try:
        raw = await _ollama_call(prompt)
        parsed = _parse_ollama_response(raw)
        if parsed:
            return parsed
    except Exception as exc:
        logger.info("classify_prospect_async: ollama indisponível: %s", exc)

    return {
        "industry": "outros", "sub_category": "indefinido", "icp_fit": "medium",
        "rationale": "sem CNAE / sem categoria OSM / Ollama indisponível",
        "source": "fallback",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Classifica industry/sub_category/icp_fit")
    ap.add_argument("--cnae", default="", help="CNAE do prospect (com ou sem pontuação)")
    ap.add_argument("--name", default="?", help="Nome do negócio")
    ap.add_argument("--category", default="", help="Categoria OSM (restaurant, clinic, ...)")
    ap.add_argument("--website", default="", help="Website (presença vira sinal ICP)")
    ap.add_argument("--razao-social", default="", dest="razao_social")
    ap.add_argument("--no-ollama", action="store_true", help="Pula fallback Ollama (rule-only)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    prospect = {
        "cnae": args.cnae,
        "business_name": args.name,
        "category": args.category,
        "website": args.website,
        "razao_social": args.razao_social,
    }
    result = classify_prospect(prospect, use_ollama=not args.no_ollama)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
