"""Hermes Night Scraper — Massive Google Maps Discovery.

Runs ALL categories across Cuiaba + neighboring cities.
Flags businesses WITH websites for Claude Code audit tasks.
Flags businesses WITHOUT websites as high-priority outreach targets.

Usage:
    python night_scraper.py                    # Full run: Cuiaba + neighbors
    python night_scraper.py --city "Cuiaba"    # Single city
    python night_scraper.py --resume           # Resume from last checkpoint
"""
import argparse
import json
import os
import sys
import time
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone
from pathlib import Path

import httpx

API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")
BASE_URL = "https://places.googleapis.com/v1/places:searchText"
HERMES_API = os.environ.get("HERMES_API_URL", "http://localhost:8420")

FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.websiteUri",
    "places.googleMapsUri",
    "places.rating",
    "places.userRatingCount",
    "places.types",
    "places.primaryType",
    "places.location",
    "places.photos",
])

CATEGORIES = [
    # Servicos pessoais
    "salao de beleza", "barbearia", "estetica", "spa", "manicure",
    "cabeleireiro", "depilacao", "sobrancelha",
    # Saude
    "clinica medica", "clinica odontologica", "dentista", "psicologo",
    "fisioterapia", "nutricionista", "veterinaria", "clinica veterinaria",
    "laboratorio de analises", "otica",
    # Alimentacao
    "restaurante", "pizzaria", "hamburgueria", "lanchonete", "padaria",
    "confeitaria", "sorveteria", "acai", "cafeteria", "bar",
    "churrascaria", "comida japonesa", "pastelaria", "food truck",
    # Comercio
    "loja de roupas", "boutique", "loja de calcados", "loja de celular",
    "pet shop", "loja de materiais de construcao", "papelaria",
    "loja de informatica", "loja de moveis", "floricultura",
    "joalheria", "relojoaria", "loja de presentes",
    "loja de cosmeticos", "farmacia", "drogaria",
    # Servicos profissionais
    "escritorio de advocacia", "advogado", "escritorio de contabilidade",
    "contador", "imobiliaria", "corretor de imoveis",
    "escritorio de arquitetura", "engenharia civil",
    "consultoria empresarial", "despachante",
    # Automotivo
    "oficina mecanica", "auto eletrica", "borracharia", "lava jato",
    "funilaria e pintura", "auto pecas", "concessionaria",
    # Educacao
    "escola de idiomas", "curso preparatorio", "escola particular",
    "autoescola", "escola de musica", "escola de danca",
    "aula particular", "reforco escolar",
    # Eventos e lazer
    "buffet infantil", "buffet", "casa de festas", "decoracao de festas",
    "fotografo", "estudio fotografico", "filmagem",
    # Fitness
    "academia", "crossfit", "pilates", "yoga", "personal trainer",
    "estudio de musculacao",
    # Construcao
    "construtora", "empreiteira", "marmoraria", "vidracaria",
    "serralheria", "marcenaria", "eletricista", "encanador",
    "pintor", "gesso e drywall",
    # Tecnologia
    "assistencia tecnica celular", "assistencia tecnica informatica",
    "provedor de internet", "seguranca eletronica",
    # Hospedagem
    "hotel", "pousada",
    # Outros servicos
    "lavanderia", "costureira", "chaveiro", "dedetizadora",
    "mudanca e frete", "grafica", "coworking",
    "energia solar", "ar condicionado",
]

CITIES = [
    ("Cuiaba", "MT"),
    ("Varzea Grande", "MT"),
    ("Rondonopolis", "MT"),
    ("Sinop", "MT"),
    ("Tangara da Serra", "MT"),
    ("Caceres", "MT"),
    ("Sorriso", "MT"),
    ("Lucas do Rio Verde", "MT"),
    ("Primavera do Leste", "MT"),
    ("Barra do Garcas", "MT"),
    ("Nova Mutum", "MT"),
    ("Campo Verde", "MT"),
    ("Chapada dos Guimaraes", "MT"),
    ("Pocone", "MT"),
    ("Nossa Senhora do Livramento", "MT"),
    ("Santo Antonio de Leverger", "MT"),
]

CHECKPOINT_FILE = Path.home() / ".hermes" / "data" / "night_scraper_checkpoint.json"
LAST_RUN_FILE = Path.home() / ".hermes" / "data" / "night_scraper_last_run.json"
LOG_DIR = Path.home() / ".hermes" / "logs"


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = "[{}] {}".format(ts, msg)
    print(line, file=sys.stderr)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "night_scraper_{}.log".format(datetime.now(timezone.utc).strftime("%Y%m%d"))
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def save_checkpoint(city, category_idx, stats):
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "city": city,
        "category_idx": category_idx,
        "stats": stats,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    CHECKPOINT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_checkpoint():
    if CHECKPOINT_FILE.exists():
        return json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
    return None


def api_call(method, endpoint, data=None):
    try:
        with httpx.Client(timeout=10) as client:
            url = "{}{}".format(HERMES_API, endpoint)
            if method == "GET":
                r = client.get(url)
            elif method == "POST":
                r = client.post(url, json=data)
            elif method == "PATCH":
                r = client.patch(url, json=data)
            else:
                return {"error": "Unknown method {}".format(method)}
            r.raise_for_status()
            return r.json()
    except Exception as e:
        return {"error": str(e)}


def search_places(query, city, state, page_token=None):
    if not API_KEY:
        return {"error": "GOOGLE_PLACES_API_KEY not set"}

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELD_MASK,
    }

    body = {
        "textQuery": "{} em {}, {}".format(query, city, state),
        "languageCode": "pt-BR",
        "maxResultCount": 20,
    }

    if page_token:
        body["pageToken"] = page_token

    try:
        with httpx.Client(timeout=15) as client:
            r = client.post(BASE_URL, json=body, headers=headers)
            if r.status_code == 429:
                log("  RATE LIMIT! Esperando 60s...")
                time.sleep(60)
                r = client.post(BASE_URL, json=body, headers=headers)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        return {"error": "API {}: {}".format(e.response.status_code, e.response.text[:200])}
    except Exception as e:
        return {"error": str(e)}


def get_existing_keys():
    result = api_call("GET", "/api/prospects?limit=5000")
    if "error" in result:
        return set()
    return {
        (p.get("business_name", "").lower().strip(), p.get("city", "").lower().strip())
        for p in result.get("prospects", [])
    }


def extract_and_save(api_response, category, city, state, existing_keys, stats, only_no_site=False):
    places = api_response.get("places", [])
    new_count = 0

    for place in places:
        display_name = place.get("displayName", {})
        name = display_name.get("text", "Desconhecido")
        website = place.get("websiteUri", "")
        has_website = bool(website)

        if only_no_site and has_website:
            continue

        key = (name.lower().strip(), city.lower().strip())
        if key in existing_keys:
            stats["skipped_dupes"] += 1
            continue

        existing_keys.add(key)

        photo_ref = None
        photos = place.get("photos", [])
        if photos:
            photo_ref = photos[0].get("name", "")

        prospect_data = {
            "name": name,
            "business_name": name,
            "category": category,
            "phone": place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber"),
            "address": place.get("formattedAddress", ""),
            "city": city,
            "state": state,
            "website": website if website else None,
            "google_maps_url": place.get("googleMapsUri", ""),
            "google_rating": place.get("rating"),
            "google_reviews": place.get("userRatingCount", 0),
            "photo_ref": photo_ref,
            "source": "google_maps",
        }

        resp = api_call("POST", "/api/prospects", prospect_data)
        if "id" not in resp:
            stats["api_errors"] += 1
            continue

        prospect_id = resp["id"]
        new_count += 1

        if has_website:
            stats["with_website"] += 1
            api_call("POST", "/api/tasks", {
                "title": "Auditar site: {}".format(name),
                "description": json.dumps({
                    "prospect_id": prospect_id,
                    "business_name": name,
                    "website": website,
                    "city": city,
                    "category": category,
                    "action": "full_audit",
                    "google_rating": place.get("rating"),
                    "google_reviews": place.get("userRatingCount", 0),
                    "photo_ref": photo_ref,
                }, ensure_ascii=False),
                "priority": "high" if (place.get("rating") or 0) >= 4.0 else "medium",
                "assigned_to": "claude_code",
                "created_by": "night_scraper",
            })
            stats["audit_tasks_created"] += 1
        else:
            stats["without_website"] += 1
            audit_text = "SEM WEBSITE - Oportunidade principal. {} em {}. Google: {}/5 ({} avaliacoes). Contato: {}.".format(
                category, city,
                place.get("rating", "N/A"),
                place.get("userRatingCount", 0),
                prospect_data.get("phone", "sem telefone"),
            )
            api_call("PATCH", "/api/prospects/{}".format(prospect_id), {
                "score": 70,
                "stage": "qualified",
                "audit_summary": audit_text,
            })
            api_call("POST", "/api/tasks", {
                "title": "Outreach prioritario: {} (SEM SITE)".format(name),
                "description": json.dumps({
                    "prospect_id": prospect_id,
                    "business_name": name,
                    "city": city,
                    "category": category,
                    "action": "generate_outreach",
                    "priority_reason": "no_website",
                    "google_rating": place.get("rating"),
                    "phone": prospect_data.get("phone"),
                }, ensure_ascii=False),
                "priority": "high",
                "assigned_to": "claude_code",
                "created_by": "night_scraper",
            })
            stats["outreach_tasks_created"] += 1

    return new_count


def scrape_city(city, state, categories, existing_keys, stats, start_cat_idx=0, only_no_site=False):
    log("")
    log("=" * 60)
    log("CIDADE: {}, {} - {} categorias".format(city, state, len(categories)))
    log("=" * 60)

    api_call("POST", "/api/activities", {
        "type": "discovery",
        "title": "Night Scraper: iniciando {}".format(city),
        "description": "{} categorias a buscar".format(len(categories)),
    })

    city_new = 0

    for i, category in enumerate(categories):
        if i < start_cat_idx:
            continue

        log("  [{}/{}] {}...".format(i + 1, len(categories), category))
        save_checkpoint(city, i, stats)

        response = search_places(category, city, state)
        if "error" in response:
            log("    ERRO: {}".format(response["error"]))
            stats["errors"].append("{}/{}: {}".format(city, category, response["error"]))
            time.sleep(2)
            continue

        new = extract_and_save(response, category, city, state, existing_keys, stats, only_no_site)
        city_new += new

        next_token = response.get("nextPageToken")
        page = 1
        while next_token and page < 5:
            time.sleep(2)
            page += 1
            response2 = search_places(category, city, state, page_token=next_token)
            if "error" in response2:
                break
            new2 = extract_and_save(response2, category, city, state, existing_keys, stats, only_no_site)
            city_new += new2
            next_token = response2.get("nextPageToken")

        if new > 0:
            log("    +{} novos prospects".format(new))

        time.sleep(1.5)

    stats["cities_completed"].append(city)
    log("  TOTAL {}: +{} novos prospects".format(city, city_new))

    api_call("POST", "/api/activities", {
        "type": "discovery",
        "title": "Night Scraper: {} concluido - {} novos".format(city, city_new),
        "description": "Com site: {} | Sem site: {}".format(stats["with_website"], stats["without_website"]),
    })

    return city_new


def send_summary_email(stats):
    email_from = os.environ.get("EMAIL_FROM", "")
    email_to = os.environ.get("EMAIL_TO", "")
    email_pass = os.environ.get("EMAIL_APP_PASSWORD", "")

    if not all([email_from, email_to, email_pass]):
        log("Email nao configurado, pulando envio")
        return

    elapsed_min = round(stats.get("elapsed_seconds", 0) / 60, 1)
    cities_list = "\n".join("  - " + c for c in stats.get("cities_completed", []))
    errors_text = "\n".join("  " + e for e in stats.get("errors", []))

    body = """HERMES NIGHT SCRAPER - RELATORIO

Executado em: {}
Duracao: {} minutos

RESULTADOS:
  Total novos prospects: {}
  COM website (para auditoria): {}
  SEM website (oportunidade direta): {}
  Duplicados ignorados: {}

TASKS CRIADAS:
  Tasks de auditoria (Claude Code): {}
  Tasks de outreach (Claude Code): {}

CIDADES COMPLETADAS:
{}

{}

---
Hermes Command Center - Prospeccao Automatizada
""".format(
        datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC"),
        elapsed_min,
        stats.get("total_new", 0),
        stats.get("with_website", 0),
        stats.get("without_website", 0),
        stats.get("skipped_dupes", 0),
        stats.get("audit_tasks_created", 0),
        stats.get("outreach_tasks_created", 0),
        cities_list,
        "ERROS:\n" + errors_text if stats.get("errors") else "Sem erros!",
    )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = "Hermes Night Scraper - {} novos prospects".format(stats.get("total_new", 0))
    msg["From"] = email_from
    msg["To"] = email_to

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(email_from, email_pass)
            server.send_message(msg)
        log("Email de relatorio enviado!")
    except Exception as e:
        log("Erro ao enviar email: {}".format(e))


def send_telegram_summary(stats):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", os.environ.get("TELEGRAM_HOME_CHANNEL", ""))

    if not bot_token or not chat_id:
        log("Telegram nao configurado, pulando")
        return

    elapsed_min = round(stats.get("elapsed_seconds", 0) / 60, 1)
    cities_str = ", ".join(stats.get("cities_completed", []))
    errors_count = len(stats.get("errors", []))

    text = (
        "*Hermes Night Scraper - Relatorio*\n\n"
        "Duracao: {} min\n\n"
        "*Resultados:*\n"
        "- Novos prospects: *{}*\n"
        "- COM site (auditoria): {}\n"
        "- SEM site (oportunidade): {}\n"
        "- Duplicados: {}\n\n"
        "*Tasks para Claude Code:*\n"
        "- Auditorias: {}\n"
        "- Outreach: {}\n\n"
        "Cidades: {}\n"
        "{}"
    ).format(
        elapsed_min,
        stats.get("total_new", 0),
        stats.get("with_website", 0),
        stats.get("without_website", 0),
        stats.get("skipped_dupes", 0),
        stats.get("audit_tasks_created", 0),
        stats.get("outreach_tasks_created", 0),
        cities_str,
        "{} erros".format(errors_count) if errors_count else "Sem erros",
    )

    try:
        httpx.post(
            "https://api.telegram.org/bot{}/sendMessage".format(bot_token),
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        log("Telegram summary enviado!")
    except Exception as e:
        log("Erro Telegram: {}".format(e))


def run_night_scraper(cities=None, categories=None, resume=False, only_no_site=False):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    start_time = time.monotonic()

    stats = {
        "total_new": 0,
        "with_website": 0,
        "without_website": 0,
        "skipped_dupes": 0,
        "api_errors": 0,
        "audit_tasks_created": 0,
        "outreach_tasks_created": 0,
        "cities_completed": [],
        "errors": [],
    }

    start_city_idx = 0
    start_cat_idx = 0

    if resume:
        cp = load_checkpoint()
        if cp:
            stats = cp.get("stats", stats)
            resume_city = cp.get("city", "")
            start_cat_idx = cp.get("category_idx", 0)
            target_cities = cities if cities else CITIES
            for idx, (c, s) in enumerate(target_cities):
                if c == resume_city:
                    start_city_idx = idx
                    break
            log("RESUMINDO de {}, categoria {}".format(resume_city, start_cat_idx))

    if not cities:
        cities = CITIES

    active_categories = categories if categories else CATEGORIES

    log("=" * 60)
    log("HERMES NIGHT SCRAPER - INICIANDO")
    if categories:
        log("MODO CUSTOM: {} termos de busca".format(len(active_categories)))
        for t in active_categories:
            log("  - {}".format(t))
    if only_no_site:
        log("FILTRO: apenas estabelecimentos SEM website")
    log("Cidades: {} | Categorias: {}".format(len(cities), len(active_categories)))
    est_seconds = len(cities) * len(active_categories) * 2
    log("Estimativa: ~{}s (~{} min)".format(est_seconds, round(est_seconds / 60)))
    log("=" * 60)

    api_call("POST", "/api/activities", {
        "type": "task",
        "title": "Night Scraper INICIADO{}".format(" (custom)" if categories else ""),
        "description": "{} cidades, {} categorias{}".format(
            len(cities), len(active_categories),
            " | apenas sem site" if only_no_site else ""),
    })

    existing_keys = get_existing_keys()
    log("Prospects existentes no DB: {}".format(len(existing_keys)))

    for i, (city, state) in enumerate(cities):
        if i < start_city_idx:
            continue

        cat_start = start_cat_idx if i == start_city_idx else 0
        new = scrape_city(city, state, active_categories, existing_keys, stats, cat_start, only_no_site)
        stats["total_new"] += new

    stats["elapsed_seconds"] = round(time.monotonic() - start_time, 1)

    # Save last-run stats for the status API before deleting checkpoint
    LAST_RUN_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_RUN_FILE.write_text(json.dumps({
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "cities": [c for c, s in (cities if cities else CITIES)],
        "total_categories": len(active_categories),
        "custom_categories": categories is not None,
        "only_no_site": only_no_site,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()

    log("")
    log("=" * 60)
    log("NIGHT SCRAPER CONCLUIDO!")
    log("Total novos: {}".format(stats["total_new"]))
    log("Com site: {} | Sem site: {}".format(stats["with_website"], stats["without_website"]))
    log("Tasks auditoria: {} | Tasks outreach: {}".format(stats["audit_tasks_created"], stats["outreach_tasks_created"]))
    log("Duracao: {} min".format(round(stats["elapsed_seconds"] / 60, 1)))
    log("=" * 60)

    api_call("POST", "/api/activities", {
        "type": "task",
        "title": "Night Scraper CONCLUIDO - {} novos prospects".format(stats["total_new"]),
        "description": json.dumps(stats, ensure_ascii=False),
    })

    report_path = LOG_DIR / "night_scraper_report_{}.json".format(
        datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
    report_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    send_summary_email(stats)
    send_telegram_summary(stats)

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hermes Night Scraper")
    parser.add_argument("--city", help="Single city to scrape")
    parser.add_argument("--cities", help="Comma-separated list of cities to scrape")
    parser.add_argument("--categories", help="Comma-separated custom search terms")
    parser.add_argument("--only-no-site", action="store_true", help="Only save prospects WITHOUT a website")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--cuiaba-only", action="store_true", help="Only Cuiaba")
    parser.add_argument("--neighbors", action="store_true", help="Cuiaba + Varzea Grande + nearby")
    args = parser.parse_args()

    if args.cities:
        cities = [(c.strip(), "MT") for c in args.cities.split(",") if c.strip()]
    elif args.city:
        cities = [(args.city, "MT")]
    elif args.cuiaba_only:
        cities = [("Cuiaba", "MT")]
    elif args.neighbors:
        cities = [
            ("Cuiaba", "MT"),
            ("Varzea Grande", "MT"),
            ("Chapada dos Guimaraes", "MT"),
            ("Pocone", "MT"),
            ("Nossa Senhora do Livramento", "MT"),
            ("Santo Antonio de Leverger", "MT"),
            ("Campo Verde", "MT"),
        ]
    else:
        cities = None

    custom_cats = None
    if args.categories:
        custom_cats = [c.strip() for c in args.categories.split(",") if c.strip()]

    result = run_night_scraper(cities, categories=custom_cats, resume=args.resume, only_no_site=args.only_no_site)
    print(json.dumps(result, ensure_ascii=False, indent=2))
