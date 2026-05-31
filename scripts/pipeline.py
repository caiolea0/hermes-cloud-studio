"""Hermes Prospecting Pipeline — Master Orchestrator.

Runs the full pipeline:
  1. Discovery  → Google Maps scraping for businesses
  2. Dedup      → Skip already-known prospects
  3. Audit      → Website & social media audit
  4. Score      → Qualification scoring
  5. Outreach   → Generate personalized messages
  6. Sync       → Push results to dashboard API

Designed to run as a cron job (daily) or on-demand.

Usage:
    python pipeline.py --city "Cuiabá" --mode full
    python pipeline.py --mode audit-pending
    python pipeline.py --mode outreach-ready
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from google_maps_scraper import discover_businesses, CATEGORIES
from web_audit import audit_prospect
from outreach_generator import generate_outreach

API_URL = os.environ.get("HERMES_API_URL", "http://localhost:8500")
HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
LOG_DIR = HERMES_HOME / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", file=sys.stderr)


def api_call(method: str, endpoint: str, data: dict = None) -> dict:
    """Call the dashboard API."""
    try:
        with httpx.Client(timeout=10) as client:
            url = f"{API_URL}{endpoint}"
            if method == "GET":
                r = client.get(url)
            elif method == "POST":
                r = client.post(url, json=data)
            elif method == "PATCH":
                r = client.patch(url, json=data)
            else:
                return {"error": f"Unknown method {method}"}
            r.raise_for_status()
            return r.json()
    except Exception as e:
        log(f"API error: {e}")
        return {"error": str(e)}


def log_activity(activity_type: str, title: str, description: str = None, prospect_id: int = None):
    """Log activity to the dashboard."""
    api_call("POST", "/api/activities", {
        "type": activity_type,
        "title": title,
        "description": description,
        "prospect_id": prospect_id,
    })


def get_existing_prospects() -> set:
    """Get set of known business names to avoid duplicates."""
    result = api_call("GET", "/api/prospects?limit=500")
    if "error" in result:
        return set()
    return {
        (p.get("business_name", "").lower(), p.get("city", "").lower())
        for p in result.get("prospects", [])
    }


def run_discovery(city: str, categories: list = None, max_per_category: int = 20):
    """Stage 1: Discover new businesses via Google Maps."""
    log(f"DISCOVERY: Buscando negócios em {city}...")
    log_activity("discovery", f"Iniciando busca em {city}", f"{len(categories or CATEGORIES)} categorias")

    result = discover_businesses(city, categories, only_no_website=False)

    if result.get("errors"):
        for err in result["errors"]:
            log(f"  Erro: {err}")

    existing = get_existing_prospects()
    new_prospects = []

    for p in result.get("prospects", []):
        key = (p.get("business_name", "").lower(), p.get("city", "").lower())
        if key not in existing:
            new_prospects.append(p)

    log(f"  Encontrados: {result['total_found']} | Novos: {len(new_prospects)} | Sem site: {result['without_website']}")

    created_ids = []
    for p in new_prospects:
        resp = api_call("POST", "/api/prospects", {
            "name": p["name"],
            "business_name": p["business_name"],
            "category": p["category"],
            "phone": p.get("phone"),
            "address": p.get("address"),
            "city": p["city"],
            "state": p.get("state", "MT"),
            "website": p.get("website"),
            "google_maps_url": p.get("google_maps_url"),
            "google_rating": p.get("google_rating"),
            "google_reviews": p.get("google_reviews", 0),
            "source": "google_maps",
        })
        if "id" in resp:
            created_ids.append(resp["id"])

    log_activity(
        "discovery",
        f"{len(new_prospects)} novos negócios encontrados em {city}",
        f"Sem website: {sum(1 for p in new_prospects if not p.get('has_website'))} | Com website: {sum(1 for p in new_prospects if p.get('has_website'))}"
    )

    return {"new": len(new_prospects), "total_found": result["total_found"], "ids": created_ids}


def run_audit_pending():
    """Stage 2-3: Audit prospects in 'discovered' stage."""
    log("AUDIT: Auditando prospects pendentes...")

    result = api_call("GET", "/api/prospects?stage=discovered&limit=20")
    prospects = result.get("prospects", [])

    if not prospects:
        log("  Nenhum prospect pendente para auditoria")
        return {"audited": 0}

    log(f"  {len(prospects)} prospects para auditar")
    audited_count = 0

    for p in prospects:
        log(f"  Auditando: {p.get('business_name', p.get('name', '?'))}...")
        audit = audit_prospect(p)

        new_stage = "qualified" if audit["score"] >= 50 else "discovered"
        if audit["score"] >= 70:
            new_stage = "audited"

        api_call("PATCH", f"/api/prospects/{p['id']}", {
            "score": audit["score"],
            "stage": new_stage,
            "audit_summary": audit["audit_summary"],
        })

        log_activity(
            "audit",
            f"Auditoria concluída: {p.get('business_name', p.get('name', '?'))}",
            f"Score: {audit['score']} | Stage: {new_stage}",
            prospect_id=p["id"],
        )

        audited_count += 1
        time.sleep(0.5)

    log(f"  {audited_count} prospects auditados")
    return {"audited": audited_count}


def run_outreach_ready():
    """Stage 4: Generate outreach for high-score audited prospects."""
    log("OUTREACH: Gerando mensagens para prospects qualificados...")

    result = api_call("GET", "/api/prospects?stage=audited&min_score=65&limit=10")
    prospects = result.get("prospects", [])

    if not prospects:
        log("  Nenhum prospect pronto para outreach")
        return {"generated": 0}

    log(f"  {len(prospects)} prospects prontos para outreach")
    generated = 0

    for p in prospects:
        outreach = generate_outreach(p)

        api_call("PATCH", f"/api/prospects/{p['id']}", {
            "stage": "outreach",
            "outreach_message": outreach["whatsapp_message"],
            "outreach_status": "ready",
        })

        log_activity(
            "outreach",
            f"Mensagem gerada: {p.get('business_name', p.get('name', '?'))}",
            f"Serviços recomendados: {', '.join(outreach['recommended_services'][:3])}",
            prospect_id=p["id"],
        )

        generated += 1

    log(f"  {generated} mensagens de outreach geradas")
    return {"generated": generated}


def update_pipeline_stats():
    """Update daily pipeline statistics."""
    result = api_call("GET", "/api/dashboard")
    if "error" in result:
        return

    stages = result.get("by_stage", {})
    log(f"STATS: discovered={stages.get('discovered', 0)} qualified={stages.get('qualified', 0)} "
        f"audited={stages.get('audited', 0)} outreach={stages.get('outreach', 0)}")


def run_full_pipeline(city: str, categories: list = None):
    """Run the complete pipeline end-to-end."""
    start = time.monotonic()
    log(f"=== HERMES PIPELINE START — {city} ===")
    log_activity("task", "Pipeline iniciado", f"Cidade: {city} | Modo: full")

    discovery = run_discovery(city, categories)
    log("")

    audit = run_audit_pending()
    log("")

    outreach = run_outreach_ready()
    log("")

    update_pipeline_stats()

    elapsed = round(time.monotonic() - start, 1)
    summary = {
        "city": city,
        "discovery": discovery,
        "audit": audit,
        "outreach": outreach,
        "elapsed_seconds": elapsed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    log(f"=== PIPELINE COMPLETO em {elapsed}s ===")
    log_activity(
        "task",
        f"Pipeline concluído — {discovery['new']} novos, {audit['audited']} auditados, {outreach['generated']} outreach",
        json.dumps(summary, ensure_ascii=False),
    )

    log_path = LOG_DIR / f"pipeline_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    log_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hermes Prospecting Pipeline")
    parser.add_argument("--city", default="Cuiabá", help="Target city")
    parser.add_argument("--mode", choices=["full", "discovery", "audit-pending", "outreach-ready"],
                        default="full", help="Pipeline mode")
    parser.add_argument("--categories", help="Comma-separated categories")
    args = parser.parse_args()

    categories = [c.strip() for c in args.categories.split(",")] if args.categories else None

    if args.mode == "full":
        result = run_full_pipeline(args.city, categories)
    elif args.mode == "discovery":
        result = run_discovery(args.city, categories)
    elif args.mode == "audit-pending":
        result = run_audit_pending()
    elif args.mode == "outreach-ready":
        result = run_outreach_ready()

    print(json.dumps(result, ensure_ascii=False, indent=2))
