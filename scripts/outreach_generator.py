"""Outreach Message Generator — Hermes Pipeline Stage 4.

Generates personalized outreach messages in Portuguese for prospects
based on their audit results and business category.

Uses templates + dynamic fields. In production, Claude Code will
refine messages via `claude -p` for maximum personalization.
"""
import json
import sys
from datetime import datetime, timezone


SERVICES = {
    "site": "criação de site profissional e responsivo",
    "logo": "design de logo e identidade visual",
    "branding": "estratégia de branding completa",
    "marketing": "marketing digital estratégico",
    "social": "gestão de redes sociais com conteúdo IA",
    "catalogo": "catálogo digital de produtos com fotos IA",
    "seo": "otimização para Google (SEO local)",
    "ads": "criativos para anúncios (Meta/Google Ads)",
}

CATEGORY_SERVICES = {
    "restaurante": ["site", "catalogo", "social", "ads"],
    "salão de beleza": ["site", "social", "ads", "branding"],
    "barbearia": ["site", "social", "branding"],
    "clínica": ["site", "seo", "social", "marketing"],
    "odonto": ["site", "seo", "social", "marketing"],
    "pet shop": ["site", "catalogo", "social", "ads"],
    "academia": ["site", "social", "ads", "marketing"],
    "advocacia": ["site", "seo", "branding"],
    "contabil": ["site", "seo", "branding"],
    "imobiliária": ["site", "seo", "catalogo", "ads"],
    "construtora": ["site", "seo", "branding"],
    "oficina": ["site", "seo", "social"],
    "buffet": ["site", "catalogo", "social", "ads"],
    "fotograf": ["site", "catalogo", "branding"],
    "confeitaria": ["site", "catalogo", "social", "ads"],
    "loja": ["site", "catalogo", "social", "ads"],
    "escola": ["site", "seo", "marketing", "social"],
    "hotel": ["site", "seo", "catalogo", "marketing"],
    "pousada": ["site", "seo", "catalogo", "marketing"],
}


def get_recommended_services(category: str) -> list:
    """Get recommended services based on business category."""
    cat_lower = (category or "").lower()
    for key, services in CATEGORY_SERVICES.items():
        if key in cat_lower:
            return services
    return ["site", "social", "branding"]


def generate_whatsapp_message(prospect: dict, audit: dict = None) -> str:
    """Generate a personalized WhatsApp outreach message."""
    name = prospect.get("business_name") or prospect.get("name", "")
    category = prospect.get("category", "")
    city = prospect.get("city", "Cuiabá")
    has_website = prospect.get("has_website") or (audit and audit.get("website_audit", {}).get("exists"))
    rating = prospect.get("google_rating")
    reviews = prospect.get("google_reviews", 0)

    services = get_recommended_services(category)
    service_list = ", ".join(SERVICES[s] for s in services[:3])

    if not has_website:
        msg = f"""Olá! Tudo bem? Me chamo Caio Leão, sou designer e estrategista digital aqui em {city}.

Encontrei o(a) *{name}* no Google Maps"""

        if rating and rating >= 4.0:
            msg += f" e vi que vocês têm uma avaliação excelente ({rating}/5 com {reviews} avaliações)! Parabéns pelo trabalho"

        msg += f""".

Notei que vocês ainda não têm um site profissional — e isso é uma grande oportunidade! Hoje, mais de 80% dos clientes pesquisam online antes de visitar um negócio.

Trabalho com {service_list}, e acredito que posso ajudar o(a) {name} a:

- Aparecer no topo do Google quando clientes buscarem "{category.lower()} em {city}"
- Ter uma presença digital profissional que transmite confiança
- Converter mais visitantes em clientes com um site moderno

Posso enviar alguns exemplos do meu trabalho? Sem compromisso, claro!

Caio Leão
Designer & Estrategista Digital
{city}, MT"""

    else:
        issues = []
        if audit:
            wa = audit.get("website_audit", {})
            if not wa.get("ssl"):
                issues.append("sem certificado de segurança (SSL)")
            if not wa.get("has_mobile_viewport"):
                issues.append("não está otimizado para celular")
            if (wa.get("response_time_ms") or 0) > 3000:
                issues.append("está um pouco lento para carregar")

        msg = f"""Olá! Me chamo Caio Leão, sou designer e estrategista digital em {city}.

Estive analisando a presença digital do(a) *{name}* e identifiquei algumas oportunidades de melhoria"""

        if issues:
            msg += f" — notei que o site atual {', '.join(issues)}"

        msg += f""".

Trabalho com {service_list} e posso ajudar a modernizar a presença online do(a) {name}, trazendo mais clientes e transmitindo mais profissionalismo.

Posso compartilhar uma análise gratuita e sem compromisso?

Caio Leão
Designer & Estrategista Digital
{city}, MT"""

    return msg


def generate_email_message(prospect: dict, audit: dict = None) -> str:
    """Generate a personalized email outreach message."""
    name = prospect.get("business_name") or prospect.get("name", "")
    category = prospect.get("category", "")
    city = prospect.get("city", "Cuiabá")
    has_website = prospect.get("has_website")

    services = get_recommended_services(category)

    if not has_website:
        subject = f"Oportunidade digital para {name}"
        body = f"""Prezado(a) responsável pelo(a) {name},

Me chamo Caio Leão e sou designer e estrategista digital em {city}. Encontrei o(a) {name} durante uma pesquisa sobre {category.lower()}s na região e fiquei impressionado com o trabalho de vocês.

Notei que vocês ainda não possuem um site profissional, e gostaria de oferecer uma consultoria gratuita sobre como uma presença digital pode impulsionar seus resultados.

Nossos serviços incluem:
{chr(10).join(f'  • {SERVICES[s].capitalize()}' for s in services[:4])}

Mais de 80% dos consumidores pesquisam online antes de visitar um negócio local. Um site profissional e otimizado pode ser o diferencial para atrair novos clientes.

Posso agendar uma conversa rápida de 15 minutos para apresentar algumas ideias?

Atenciosamente,
Caio Leão
Designer & Estrategista Digital
{city}, MT
"""
    else:
        subject = f"Análise digital gratuita para {name}"
        body = f"""Prezado(a) responsável pelo(a) {name},

Me chamo Caio Leão, designer e estrategista digital em {city}. Realizei uma análise preliminar da presença digital do(a) {name} e identifiquei oportunidades de melhoria que podem aumentar sua visibilidade e conversões.

Gostaria de compartilhar essa análise gratuitamente e sem compromisso. Trabalho com:
{chr(10).join(f'  • {SERVICES[s].capitalize()}' for s in services[:4])}

Posso enviar o relatório completo?

Atenciosamente,
Caio Leão
Designer & Estrategista Digital
{city}, MT
"""

    return f"Assunto: {subject}\n\n{body}"


def generate_outreach(prospect: dict, audit: dict = None) -> dict:
    """Generate all outreach messages for a prospect."""
    return {
        "prospect_id": prospect.get("id"),
        "business_name": prospect.get("business_name") or prospect.get("name"),
        "whatsapp_message": generate_whatsapp_message(prospect, audit),
        "email_message": generate_email_message(prospect, audit),
        "recommended_services": get_recommended_services(prospect.get("category", "")),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        data = json.loads(sys.argv[1])
    else:
        data = json.load(sys.stdin)

    prospect = data.get("prospect", data)
    audit = data.get("audit")

    result = generate_outreach(prospect, audit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
