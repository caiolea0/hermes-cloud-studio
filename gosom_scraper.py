#!/usr/bin/env python3
"""Hermes Command Center — Gosom Google Maps Scraper.

Replaces the Google Places API-based night_scraper.py with gosom/google-maps-scraper
(Docker, MIT license, free, ~120 places/min). Designed for nightly cron runs.

Usage:
    python3 gosom_scraper.py                          # Full run, all cities + categories
    python3 gosom_scraper.py --cities "Cuiaba,Sinop"  # Specific cities
    python3 gosom_scraper.py --categories "restaurante,pet shop"
    python3 gosom_scraper.py --resume                  # Resume from checkpoint
    python3 gosom_scraper.py --only-no-site            # Only scrape categories likely without websites
    python3 gosom_scraper.py --proxy socks5://hermes:cuiaba2026@127.0.0.1:1081
    python3 gosom_scraper.py --depth 3                 # Scroll depth (default 2)
    python3 gosom_scraper.py --concurrency 2           # Parallel browser tabs
"""
import argparse
import json
import logging
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gosom_scraper")

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
DB_PATH = HERMES_HOME / "data" / "command_center.db"
DATA_DIR = HERMES_HOME / "data"
CHECKPOINT_PATH = DATA_DIR / "gosom_checkpoint.json"
LAST_RUN_PATH = DATA_DIR / "gosom_last_run.json"
REPORT_DIR = DATA_DIR / "discovery"

DOCKER_IMAGE = "gosom/google-maps-scraper"

CITIES_MT = [
    "Cuiaba", "Varzea Grande", "Rondonopolis", "Sinop",
    "Tangara da Serra", "Caceres", "Sorriso", "Lucas do Rio Verde",
    "Primavera do Leste", "Barra do Garcas", "Nova Mutum", "Campo Verde",
    "Chapada dos Guimaraes", "Pocone", "Nossa Senhora do Livramento",
    "Santo Antonio de Leverger",
]

CATEGORIES = [
    # Food & Drink
    "restaurante", "pizzaria", "hamburgueria", "lanchonete", "padaria",
    "sorveteria", "açaiteria", "bar", "pub", "cafeteria", "churrascaria",
    "pastelaria", "sushi", "marmitaria", "food truck",
    # Health & Beauty
    "salão de beleza", "barbearia", "clínica de estética", "spa",
    "clínica médica", "clínica odontológica", "farmácia", "ótica",
    "clínica veterinária", "psicólogo", "nutricionista", "fisioterapia",
    # Fitness & Wellness
    "academia", "crossfit", "pilates", "yoga", "personal trainer",
    # Pets
    "pet shop", "banho e tosa", "clínica veterinária",
    # Automotive
    "oficina mecânica", "lava jato", "auto peças", "funilaria",
    "borracharia", "auto elétrica",
    # Home & Construction
    "material de construção", "marcenaria", "vidraçaria", "serralheria",
    "encanador", "eletricista", "pintor", "arquiteto", "decoração",
    # Retail
    "loja de roupas", "loja de calçados", "loja de celular",
    "loja de informática", "papelaria", "livraria", "floricultura",
    "loja de presentes", "joalheria", "loja de cosméticos",
    # Services
    "contabilidade", "advocacia", "imobiliária", "seguro",
    "despachante", "gráfica", "lavanderia", "hotel", "pousada",
    "escola de idiomas", "auto escola", "escola particular",
    "curso profissionalizante", "fotógrafo", "DJ",
    # Events
    "buffet", "casa de festas", "decoração de festas",
    "aluguel de brinquedos", "cerimonialista",
    # Tech & Digital
    "agência de marketing", "desenvolvimento de sites",
    "assistência técnica celular", "assistência técnica notebook",
]

CATEGORIES_NO_SITE = [
    "marmitaria", "food truck", "pastelaria", "borracharia",
    "encanador", "eletricista", "pintor", "banho e tosa",
    "lava jato", "serralheria", "marcenaria", "funilaria",
    "auto elétrica", "vidraçaria", "lavanderia",
]


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def load_existing_place_ids(conn) -> set:
    rows = conn.execute(
        "SELECT google_maps_url FROM prospects WHERE google_maps_url IS NOT NULL"
    ).fetchall()
    ids = set()
    for r in rows:
        url = r[0]
        m = re.search(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)", url)
        if m:
            ids.add(m.group(1))
        pid = re.search(r"place_id[=:]([A-Za-z0-9_-]+)", url)
        if pid:
            ids.add(pid.group(1))
    return ids


def load_existing_names_phones(conn) -> set:
    rows = conn.execute(
        "SELECT name, phone FROM prospects WHERE name IS NOT NULL"
    ).fetchall()
    return {(r[0].strip().lower(), (r[1] or "").strip()) for r in rows}


def parse_gosom_json_line(line: str) -> Optional[dict]:
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    if "title" not in data or "input_id" not in data:
        return None
    return data


def extract_city_from_address(data: dict) -> str:
    ca = data.get("complete_address", {})
    if ca and ca.get("city"):
        city = ca["city"]
        city = city.replace("á", "a").replace("ã", "a").replace("é", "e")
        return city
    addr = data.get("address", "")
    for c in CITIES_MT:
        if c.lower() in addr.lower():
            return c
    return "Cuiaba"


def extract_state(data: dict) -> str:
    ca = data.get("complete_address", {})
    if ca and ca.get("state"):
        s = ca["state"]
        if "Mato Grosso" in s:
            return "MT"
        return s[:2].upper()
    return "MT"


def map_gosom_to_prospect(data: dict, query_category: str) -> dict:
    website = data.get("web_site", "") or ""
    has_website = bool(website and website.strip() and "linktr.ee" not in website.lower())

    phone = data.get("phone", "") or ""
    emails = data.get("emails") or []
    email = emails[0] if emails else None

    thumbnail = data.get("thumbnail", "") or ""
    images = data.get("images") or []
    photo = thumbnail
    if not photo and images:
        photo = images[0].get("image", "")

    return {
        "name": data.get("title", ""),
        "business_name": data.get("title", ""),
        "category": query_category or (data.get("category", "") or ""),
        "phone": phone,
        "email": email,
        "address": data.get("address", ""),
        "city": extract_city_from_address(data),
        "state": extract_state(data),
        "website": website if has_website else None,
        "has_website": has_website,
        "google_maps_url": data.get("link", ""),
        "google_rating": data.get("review_rating"),
        "google_reviews": data.get("review_count", 0) or 0,
        "photo_ref": photo,
        "source": "gosom",
        "data_id": data.get("data_id", ""),
        "place_id": data.get("place_id", ""),
    }


def insert_prospect(conn, p: dict, existing_ids: set, existing_names: set) -> str:
    data_id = p.get("data_id", "")
    place_id = p.get("place_id", "")
    name_key = (p["name"].strip().lower(), (p["phone"] or "").strip())

    if data_id and data_id in existing_ids:
        return "dupe_id"
    if place_id and place_id in existing_ids:
        return "dupe_id"
    if name_key in existing_names:
        return "dupe_name"

    has_website = 1 if p["has_website"] else 0
    score = 0 if p["has_website"] else 70
    stage = "discovered" if p["has_website"] else "qualified"

    conn.execute("""
        INSERT INTO prospects (
            name, business_name, category, phone, email, address,
            city, state, website, has_website, google_maps_url,
            google_rating, google_reviews, photo_ref, source,
            score, stage
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        p["name"], p["business_name"], p["category"], p["phone"],
        p["email"], p["address"], p["city"], p["state"],
        p["website"], has_website, p["google_maps_url"],
        p["google_rating"], p["google_reviews"], p["photo_ref"],
        p["source"], score, stage,
    ))

    prospect_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    if data_id:
        existing_ids.add(data_id)
    if place_id:
        existing_ids.add(place_id)
    existing_names.add(name_key)

    action = "full_audit" if p["has_website"] else "generate_outreach"
    priority = "high" if not p["has_website"] else ("high" if (p.get("google_rating") or 0) >= 4.0 else "medium")

    conn.execute("""
        INSERT INTO tasks (title, description, status, priority, assigned_to, created_by)
        VALUES (?, ?, 'pending', ?, 'claude_code', 'gosom_scraper')
    """, (
        f"{'Audit' if p['has_website'] else 'Outreach'}: {p['name']}",
        json.dumps({"prospect_id": prospect_id, "action": action, "category": p["category"], "city": p["city"]}),
        priority,
    ))

    conn.execute("""
        INSERT INTO activities (type, title, description, prospect_id)
        VALUES ('discovery', ?, ?, ?)
    """, (
        f"Descoberto via gosom: {p['name']}",
        f"Categoria: {p['category']}, Cidade: {p['city']}, Rating: {p.get('google_rating', 'N/A')}",
        prospect_id,
    ))

    return "with_site" if p["has_website"] else "no_site"


def run_gosom(query: str, output_dir: str, proxy: str = "", depth: int = 2,
              concurrency: int = 1, timeout_min: int = 5) -> list[dict]:
    query_file = os.path.join(output_dir, "query.txt")
    with open(query_file, "w") as f:
        f.write(query + "\n")

    cmd = [
        "docker", "run", "--rm", "--network", "host",
        "-v", f"{query_file}:/queries.txt:ro",
        DOCKER_IMAGE,
        "-input", "/queries.txt",
        "-json",
        "-depth", str(depth),
        "-exit-on-inactivity", "2m",
        "-lang", "pt-BR",
        "-c", str(concurrency),
    ]
    if proxy:
        cmd.extend(["-proxies", proxy])

    log.info(f"Running: {query}")
    results = []

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        deadline = time.time() + timeout_min * 60
        for line in proc.stdout:
            if time.time() > deadline:
                log.warning(f"Timeout ({timeout_min}m) for query: {query}")
                proc.terminate()
                break
            parsed = parse_gosom_json_line(line)
            if parsed:
                results.append(parsed)
        proc.wait(timeout=30)
    except Exception as e:
        log.error(f"Gosom error for '{query}': {e}")

    log.info(f"  → {len(results)} results for '{query}'")
    return results


def save_checkpoint(city_idx: int, cat_idx: int, stats: dict):
    CHECKPOINT_PATH.write_text(json.dumps({
        "city_idx": city_idx,
        "cat_idx": cat_idx,
        "stats": stats,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }, indent=2))


def load_checkpoint() -> Optional[dict]:
    if CHECKPOINT_PATH.exists():
        return json.loads(CHECKPOINT_PATH.read_text())
    return None


def save_last_run(stats: dict, cities: list, categories: list):
    LAST_RUN_PATH.write_text(json.dumps({
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "scraper": "gosom",
        "stats": stats,
        "cities": cities,
        "total_categories": len(categories),
    }, indent=2))
    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()


def send_notification(stats: dict, cities: list, elapsed: float):
    try:
        import smtplib
        from email.mime.text import MIMEText

        email_from = os.environ.get("EMAIL_FROM")
        email_to = os.environ.get("EMAIL_TO")
        email_pass = os.environ.get("EMAIL_PASS")
        if not all([email_from, email_to, email_pass]):
            return

        body = f"""Hermes Gosom Scraper — Relatório

Cidades: {', '.join(cities)}
Duração: {elapsed/60:.1f} min
Novos prospects: {stats['total_new']}
  Com site: {stats['with_website']}
  Sem site: {stats['without_website']}
Duplicados ignorados: {stats['skipped_dupes']}
Erros: {len(stats['errors'])}

Tasks criadas:
  Audit: {stats['audit_tasks']}
  Outreach: {stats['outreach_tasks']}
"""
        msg = MIMEText(body)
        msg["Subject"] = f"[Hermes] Gosom: {stats['total_new']} novos prospects"
        msg["From"] = email_from
        msg["To"] = email_to

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(email_from, email_pass)
            smtp.send_message(msg)
        log.info("Email notification sent")
    except Exception as e:
        log.warning(f"Failed to send email: {e}")

    try:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if token and chat_id:
            import urllib.request
            text = (
                f"🔍 Gosom Scraper Done\n"
                f"Novos: {stats['total_new']} | Dupes: {stats['skipped_dupes']}\n"
                f"Com site: {stats['with_website']} | Sem site: {stats['without_website']}\n"
                f"Duração: {elapsed/60:.1f}min"
            )
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = json.dumps({"chat_id": chat_id, "text": text}).encode()
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10)
            log.info("Telegram notification sent")
    except Exception as e:
        log.warning(f"Failed to send Telegram: {e}")


def main():
    parser = argparse.ArgumentParser(description="Hermes Gosom Scraper")
    parser.add_argument("--cities", type=str, default="", help="Comma-separated cities")
    parser.add_argument("--categories", type=str, default="", help="Comma-separated categories")
    parser.add_argument("--only-no-site", action="store_true", help="Only categories likely without websites")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--proxy", type=str, default="socks5://hermes:cuiaba2026@127.0.0.1:1081")
    parser.add_argument("--depth", type=int, default=2, help="Scroll depth (default 2)")
    parser.add_argument("--concurrency", type=int, default=1, help="Browser tabs (default 1)")
    parser.add_argument("--timeout", type=int, default=5, help="Timeout per query in minutes")
    parser.add_argument("--no-proxy", action="store_true", help="Run without proxy")
    args = parser.parse_args()

    cities = [c.strip() for c in args.cities.split(",") if c.strip()] if args.cities else CITIES_MT
    if args.only_no_site:
        categories = CATEGORIES_NO_SITE
    elif args.categories:
        categories = [c.strip() for c in args.categories.split(",") if c.strip()]
    else:
        categories = CATEGORIES

    proxy = "" if args.no_proxy else args.proxy

    start_city_idx = 0
    start_cat_idx = 0
    stats = {
        "total_new": 0, "with_website": 0, "without_website": 0,
        "skipped_dupes": 0, "audit_tasks": 0, "outreach_tasks": 0,
        "cities_completed": [], "errors": [], "gosom_total_results": 0,
    }

    if args.resume:
        cp = load_checkpoint()
        if cp:
            start_city_idx = cp["city_idx"]
            start_cat_idx = cp["cat_idx"]
            stats = cp["stats"]
            log.info(f"Resuming from city={start_city_idx}, cat={start_cat_idx}")

    conn = get_db()
    existing_ids = load_existing_place_ids(conn)
    existing_names = load_existing_names_phones(conn)
    log.info(f"Loaded {len(existing_ids)} existing place IDs, {len(existing_names)} name+phone combos")

    start_time = time.time()
    interrupted = False

    def handle_signal(sig, frame):
        nonlocal interrupted
        log.warning("Interrupted — saving checkpoint")
        interrupted = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    with tempfile.TemporaryDirectory(prefix="gosom_") as tmpdir:
        for ci in range(start_city_idx, len(cities)):
            city = cities[ci]
            cat_start = start_cat_idx if ci == start_city_idx else 0

            for cj in range(cat_start, len(categories)):
                if interrupted:
                    save_checkpoint(ci, cj, stats)
                    break

                category = categories[cj]
                query = f"{category} em {city}"

                results = run_gosom(
                    query, tmpdir, proxy=proxy,
                    depth=args.depth, concurrency=args.concurrency,
                    timeout_min=args.timeout,
                )
                stats["gosom_total_results"] += len(results)

                batch_new = 0
                for data in results:
                    p = map_gosom_to_prospect(data, category)
                    result = insert_prospect(conn, p, existing_ids, existing_names)
                    if result == "with_site":
                        stats["total_new"] += 1
                        stats["with_website"] += 1
                        stats["audit_tasks"] += 1
                        batch_new += 1
                    elif result == "no_site":
                        stats["total_new"] += 1
                        stats["without_website"] += 1
                        stats["outreach_tasks"] += 1
                        batch_new += 1
                    else:
                        stats["skipped_dupes"] += 1

                conn.commit()

                if batch_new > 0:
                    log.info(f"  → {batch_new} new prospects inserted")

                save_checkpoint(ci, cj + 1, stats)
                time.sleep(2)

            if interrupted:
                break
            stats["cities_completed"].append(city)
            log.info(f"City done: {city} — total new so far: {stats['total_new']}")

    elapsed = time.time() - start_time
    conn.close()

    if not interrupted:
        save_last_run(stats, cities, categories)
        log.info(f"Scraping complete in {elapsed/60:.1f}min — {stats['total_new']} new prospects")
    else:
        log.info(f"Interrupted after {elapsed/60:.1f}min — checkpoint saved")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scraper": "gosom",
        "elapsed_seconds": elapsed,
        "interrupted": interrupted,
        **stats,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_file = REPORT_DIR / f"gosom_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_file.write_text(json.dumps(report, indent=2))
    log.info(f"Report saved: {report_file}")

    if not interrupted:
        send_notification(stats, cities, elapsed)

    today = datetime.now().strftime("%Y-%m-%d")
    try:
        conn2 = get_db()
        conn2.execute("""
            INSERT INTO pipeline_stats (date, discovered, qualified)
            VALUES (?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                discovered = discovered + excluded.discovered,
                qualified = qualified + excluded.qualified
        """, (today, stats["total_new"], stats["without_website"]))
        conn2.commit()
        conn2.close()
    except Exception as e:
        log.warning(f"Failed to update pipeline_stats: {e}")

    print(json.dumps(report))


if __name__ == "__main__":
    main()
