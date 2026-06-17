"""Hermes Cloud Studio — Scraper control + prompt parser (MERGED-011)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException

from core.ai import call_ai
from core.models import ScraperConfig, ScraperPrompt
from core.state import VM_API_URL, get_db, is_subsystem_paused

router = APIRouter()


AVAILABLE_CITIES = [
    "Cuiaba", "Varzea Grande", "Rondonopolis", "Sinop", "Tangara da Serra",
    "Caceres", "Sorriso", "Lucas do Rio Verde", "Primavera do Leste",
    "Barra do Garcas", "Nova Mutum", "Campo Verde", "Chapada dos Guimaraes",
    "Pocone", "Nossa Senhora do Livramento", "Santo Antonio de Leverger",
]

NEIGHBOR_CITIES = [
    "Cuiaba", "Varzea Grande", "Chapada dos Guimaraes", "Pocone",
    "Nossa Senhora do Livramento", "Santo Antonio de Leverger", "Campo Verde",
]

PARSE_SYSTEM_PROMPT = """You are a scraper task parser for Hermes, a B2B prospecting tool in Mato Grosso, Brazil.
Given a natural language request in Portuguese, extract a structured scraper configuration.

Available cities: {cities}
Neighbor cities (Cuiaba + nearby): {neighbors}

Respond ONLY with valid JSON, no markdown, no explanation:
{{
  "search_terms": ["term1", "term2", ...],
  "cities": ["City1", "City2", ...] or null for all 16,
  "only_no_site": true/false,
  "explanation": "Brief explanation in Portuguese of what will be searched"
}}

Rules:
- search_terms: Google Places Text Search queries that match the user's intent. Be creative with variations. 5-10 terms.
- cities: Match user intent to city list. "cidades proximas/vizinhanca" = neighbor cities. "todas" = null. Specific city names = list them.
- only_no_site: true if user explicitly wants businesses WITHOUT websites.
- Keep search_terms in Portuguese, as they search Google Maps in Brazil."""


@router.get("/api/scraper/status")
async def scraper_status():
    """Get night scraper status from VM, with cached fallback."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{VM_API_URL}/api/scraper/status")
            if r.status_code == 200:
                data = r.json()
                # Cache for offline access
                conn = get_db()
                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES ('scraper_cache', ?, ?)",
                        (json.dumps(data), datetime.now(timezone.utc).isoformat())
                    )
                    conn.commit()
                finally:
                    conn.close()
                return data
    except Exception:  # noqa: silenciado intencional — fallback seguro
        pass

    # Fallback: return cached scraper status
    conn = get_db()
    try:
        row = conn.execute("SELECT value FROM sync_state WHERE key = 'scraper_cache'").fetchone()
        if row:
            return json.loads(row[0])
    finally:
        conn.close()

    return {
        "running": False,
        "current_city": None,
        "category_index": 0,
        "total_categories": 0,
        "stats": {
            "total_new": 0, "with_website": 0, "without_website": 0,
            "skipped_dupes": 0, "audit_tasks_created": 0, "outreach_tasks_created": 0,
            "cities_completed": [], "errors": [],
        },
        "log_tail": [],
    }


@router.post("/api/scraper/start")
async def start_scraper(config: ScraperConfig):
    """Start the night scraper on the VM."""
    if is_subsystem_paused("scraper"):
        return {"status": "paused", "reason": "scraper subsystem paused by owner"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{VM_API_URL}/api/scraper/start", json=config.model_dump())
            if r.status_code == 200:
                return r.json()
            return {"status": "error", "detail": f"VM returned {r.status_code}"}
    except Exception as e:
        raise HTTPException(502, f"Could not reach VM: {e}")


@router.post("/api/scraper/stop")
async def stop_scraper():
    """Stop the running scraper on the VM."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{VM_API_URL}/api/scraper/stop")
            if r.status_code == 200:
                return r.json()
            return {"status": "error", "detail": f"VM returned {r.status_code}"}
    except Exception as e:
        raise HTTPException(502, f"Could not reach VM: {e}")


@router.get("/api/scraper/history")
async def scraper_history():
    """Get past scraper run reports from VM."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{VM_API_URL}/api/scraper/history")
            if r.status_code == 200:
                return r.json()
    except Exception:  # noqa: silenciado intencional — fallback seguro
        pass
    return {"runs": []}


@router.post("/api/scraper/parse-prompt")
async def parse_scraper_prompt(body: ScraperPrompt):
    """Parse a natural language prompt into structured scraper config using AI."""
    system = PARSE_SYSTEM_PROMPT.format(
        cities=", ".join(AVAILABLE_CITIES),
        neighbors=", ".join(NEIGHBOR_CITIES),
    )
    full_prompt = f"{system}\n\nUser request: {body.prompt}"

    output = ""
    try:
        ai_result = await call_ai(full_prompt, timeout=60)
        output = ai_result["response"]

        # Extract JSON from output (handle potential markdown wrapping)
        json_str = output
        if "```" in json_str:
            import re
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", json_str, re.DOTALL)
            if match:
                json_str = match.group(1)

        parsed = json.loads(json_str)

        return {
            "status": "ok",
            "config": {
                "search_terms": parsed.get("search_terms", []),
                "cities": parsed.get("cities"),
                "only_no_site": parsed.get("only_no_site", False),
            },
            "explanation": parsed.get("explanation", ""),
            "original_prompt": body.prompt,
            "provider": ai_result.get("provider", "unknown"),
        }
    except json.JSONDecodeError as e:
        raise HTTPException(422, f"Nao foi possivel parsear resposta AI como JSON: {e}\nRaw: {output[:500]}")
    except Exception as e:
        raise HTTPException(500, f"Erro ao interpretar prompt: {e}")
