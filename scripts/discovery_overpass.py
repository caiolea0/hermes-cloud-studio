"""Discovery via Overpass (OpenStreetMap) self-hosted.

Queries commercial POIs in Cuiabá (bounding box do município 5103403/MT) e
normaliza pro schema Prospect com source_type='osm'.

Idempotente: caller deduplica por osm_id ou name+address.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger("hermes.discovery.overpass")

# Cuiabá + região metropolitana (bbox: S, W, N, E)
CUIABA_BBOX = (-15.75, -56.25, -15.35, -55.85)

# Tags OSM → categoria legível
CATEGORY_MAP: dict[str, str] = {
    "restaurant": "Restaurante", "cafe": "Café", "bar": "Bar",
    "pharmacy": "Farmácia", "bank": "Banco", "clinic": "Clínica",
    "hospital": "Hospital", "dentist": "Dentista", "school": "Escola",
    "university": "Universidade", "hotel": "Hotel",
    "supermarket": "Supermercado", "hairdresser": "Salão de Beleza",
    "beauty": "Estética", "gym": "Academia", "fast_food": "Fast Food",
    "marketplace": "Feira/Mercado", "fuel": "Posto de Combustível",
    "car_repair": "Mecânica Automotiva", "car_wash": "Lava-Rápido",
    "clothes": "Moda e Vestuário", "shoes": "Calçados",
    "electronics": "Eletrônicos", "furniture": "Móveis",
    "hardware": "Materiais de Construção", "bakery": "Padaria",
    "butcher": "Açougue", "florist": "Floricultura",
    "jewelry": "Joalheria", "optician": "Ótica",
    "car": "Revenda de Veículos", "motorcycle": "Motocicletas",
    "lawyer": "Advocacia", "accountant": "Contabilidade",
    "insurance": "Seguros", "real_estate": "Imobiliária",
    "travel_agent": "Agência de Viagens", "it": "TI / Tecnologia",
    "architect": "Arquitetura", "tailor": "Alfaiataria",
    "photographer": "Fotografia", "printing": "Gráfica",
}

# Query Overpass: shop + amenity comercial + office + craft
# [out:json] com bbox e timeout conservador
_QUERY_TEMPLATE = """
[out:json][timeout:120];
(
  node["shop"]({s},{w},{n},{e});
  node["amenity"~"^(restaurant|cafe|bar|pharmacy|bank|clinic|hospital|dentist|school|university|hotel|supermarket|hairdresser|beauty|gym|fast_food|marketplace|fuel)$"]({s},{w},{n},{e});
  node["office"]({s},{w},{n},{e});
  node["craft"]({s},{w},{n},{e});
  way["shop"]({s},{w},{n},{e});
  way["amenity"~"^(restaurant|cafe|bar|pharmacy|bank|clinic|hospital|dentist|school|university|hotel|supermarket|hairdresser|beauty|gym|fast_food|marketplace|fuel)$"]({s},{w},{n},{e});
  way["office"]({s},{w},{n},{e});
);
out center tags;
""".strip()


def _normalize_category(tags: dict) -> str:
    for key in ("amenity", "shop", "office", "craft"):
        val = tags.get(key, "")
        if val:
            mapped = CATEGORY_MAP.get(val)
            if mapped:
                return mapped
            # valor não mapeado: capitaliza
            return val.replace("_", " ").title()
    return "Comércio"


def _extract_lat_lng(element: dict) -> tuple[Optional[float], Optional[float]]:
    if element.get("type") == "node":
        return element.get("lat"), element.get("lon")
    # way/relation: usa centroide calculado pelo Overpass
    center = element.get("center", {})
    return center.get("lat"), center.get("lon")


def _clean_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    url = url.strip()
    if url.startswith("http"):
        return url
    return "https://" + url


def _build_prospect(element: dict) -> Optional[dict]:
    """Normaliza element OSM para dict compatível com ProspectCreate."""
    tags = element.get("tags", {})
    name = (tags.get("name") or tags.get("brand") or "").strip()
    if not name or len(name) < 2:
        return None

    # Filtrar elementos sem nome significativo
    if name.lower() in {"sim", "não", "yes", "no", "true", "false"}:
        return None

    lat, lng = _extract_lat_lng(element)

    # Endereço OSM addr:* tags
    parts = []
    street = tags.get("addr:street", "")
    number = tags.get("addr:housenumber", "")
    suburb = tags.get("addr:suburb") or tags.get("addr:neighbourhood") or tags.get("addr:quarter", "")
    if street and number:
        parts.append(f"{street}, {number}")
    elif street:
        parts.append(street)
    if suburb:
        parts.append(suburb)
    address = ", ".join(parts) if parts else None

    phone = (
        tags.get("phone")
        or tags.get("contact:phone")
        or tags.get("contact:mobile")
        or tags.get("mobile")
    )
    website = _clean_url(
        tags.get("website") or tags.get("contact:website") or tags.get("url")
    )
    social_ig = tags.get("contact:instagram") or tags.get("instagram")
    social_fb = tags.get("contact:facebook") or tags.get("facebook")
    opening_hours = tags.get("opening_hours")
    whatsapp = tags.get("contact:whatsapp") or tags.get("whatsapp")

    return {
        "name": name,
        "business_name": name,
        "category": _normalize_category(tags),
        "phone": phone or whatsapp,
        "address": address,
        "city": "Cuiabá",
        "state": "MT",
        "website": website,
        "has_website": bool(website),
        "lat": lat,
        "lng": lng,
        "social_instagram": social_ig,
        "social_facebook": social_fb,
        "opening_hours": opening_hours,
        "osm_id": str(element["id"]),
        "source_type": "osm",
        "source": "overpass_osm",
    }


def discover_cuiaba(
    overpass_url: Optional[str] = None,
    bbox: tuple[float, float, float, float] = CUIABA_BBOX,
) -> dict:
    """
    Consulta Overpass para POIs comerciais em Cuiabá.

    Returns:
        {"prospects": [...], "total_found": N, "errors": [...]}
    """
    url = overpass_url or os.environ.get("OVERPASS_URL", "http://localhost:12345")
    s, w, n, e = bbox
    query = _QUERY_TEMPLATE.format(s=s, w=w, n=n, e=e)

    logger.info("Overpass query: bbox=(%.4f,%.4f,%.4f,%.4f) url=%s", s, w, n, e, url)
    t0 = time.time()

    try:
        with httpx.Client(timeout=180) as client:
            resp = client.post(
                f"{url}/api/interpreter",
                data={"data": query},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.ConnectError as exc:
        msg = f"Overpass indisponível em {url}: {exc}"
        logger.warning(msg)
        return {"prospects": [], "total_found": 0, "errors": [msg]}
    except Exception as exc:
        msg = f"Overpass query falhou: {exc}"
        logger.error(msg)
        return {"prospects": [], "total_found": 0, "errors": [msg]}

    elapsed = round(time.time() - t0, 1)
    elements = data.get("elements", [])
    logger.info("Overpass: %d elementos retornados em %.1fs", len(elements), elapsed)

    prospects: list[dict] = []
    skipped = 0
    for el in elements:
        p = _build_prospect(el)
        if p:
            prospects.append(p)
        else:
            skipped += 1

    logger.info(
        "Normalização: %d prospects válidos, %d descartados (sem nome)",
        len(prospects), skipped,
    )
    return {
        "prospects": prospects,
        "total_found": len(prospects),
        "errors": [],
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")

    result = discover_cuiaba()
    print(f"\n=== Overpass Discovery — Cuiabá ===")
    print(f"Total: {result['total_found']} prospects")
    if result["errors"]:
        print(f"Erros: {result['errors']}")
    print("\nPrimeiros 10:")
    for p in result["prospects"][:10]:
        phone = p.get("phone") or "-"
        addr = p.get("address") or "-"
        site = p.get("website") or "-"
        print(f"  {p['name'][:40]:<40} | {p['category']:<25} | {phone:<15} | {addr}")
