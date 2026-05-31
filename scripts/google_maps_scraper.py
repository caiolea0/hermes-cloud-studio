"""Google Maps Business Discovery — Hermes Pipeline Stage 1.

Uses Google Places API (Text Search) to find local businesses.
Focuses on businesses WITHOUT websites — prime targets for web design services.

Requires: GOOGLE_PLACES_API_KEY environment variable.

Usage:
    python google_maps_scraper.py --city "Cuiabá" --categories "restaurante,salão de beleza"
    python google_maps_scraper.py --city "Cuiabá" --all-categories
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")
BASE_URL = "https://places.googleapis.com/v1/places:searchText"

CATEGORIES = [
    "restaurante",
    "salão de beleza",
    "barbearia",
    "clínica médica",
    "clínica odontológica",
    "pet shop",
    "academia",
    "escritório de advocacia",
    "escritório de contabilidade",
    "imobiliária",
    "construtora",
    "oficina mecânica",
    "buffet infantil",
    "escola de idiomas",
    "estúdio fotográfico",
    "loja de roupas",
    "padaria",
    "farmácia",
    "hotel pousada",
    "confeitaria",
]

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
])


def search_places(query: str, city: str, page_token: str = None) -> dict:
    """Search Google Places API (New) for businesses."""
    if not API_KEY:
        return {"error": "GOOGLE_PLACES_API_KEY not set", "results": []}

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELD_MASK,
    }

    body = {
        "textQuery": f"{query} em {city}",
        "languageCode": "pt-BR",
        "maxResultCount": 20,
    }

    if page_token:
        body["pageToken"] = page_token

    try:
        with httpx.Client(timeout=15) as client:
            r = client.post(BASE_URL, json=body, headers=headers)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"API error {e.response.status_code}: {e.response.text[:300]}", "results": []}
    except Exception as e:
        return {"error": str(e), "results": []}


def extract_prospects(api_response: dict, category: str, city: str) -> list:
    """Convert Google Places API response to prospect dicts."""
    prospects = []
    places = api_response.get("places", [])

    for place in places:
        display_name = place.get("displayName", {})
        name = display_name.get("text", "Desconhecido")
        website = place.get("websiteUri", "")
        has_website = bool(website)

        prospect = {
            "name": name,
            "business_name": name,
            "category": category,
            "phone": place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber"),
            "address": place.get("formattedAddress", ""),
            "city": city,
            "state": "MT",
            "website": website if website else None,
            "has_website": has_website,
            "google_maps_url": place.get("googleMapsUri", ""),
            "google_rating": place.get("rating"),
            "google_reviews": place.get("userRatingCount", 0),
            "google_place_id": place.get("id", ""),
            "primary_type": place.get("primaryType", ""),
            "source": "google_maps",
            "score": 0,
            "stage": "discovered",
        }

        if not has_website:
            prospect["score"] = 60
        elif website:
            prospect["score"] = 30

        prospects.append(prospect)

    return prospects


def discover_businesses(city: str, categories: list = None, only_no_website: bool = False) -> dict:
    """Run discovery across multiple categories for a city."""
    if not categories:
        categories = CATEGORIES

    all_prospects = []
    seen_place_ids = set()
    errors = []

    for category in categories:
        print(f"  Buscando: {category} em {city}...", file=sys.stderr)
        response = search_places(category, city)

        if "error" in response:
            errors.append(f"{category}: {response['error']}")
            continue

        prospects = extract_prospects(response, category, city)

        for p in prospects:
            pid = p.get("google_place_id", p["name"])
            if pid not in seen_place_ids:
                seen_place_ids.add(pid)
                if only_no_website and p["has_website"]:
                    continue
                all_prospects.append(p)

        next_token = response.get("nextPageToken")
        if next_token:
            time.sleep(2)
            response2 = search_places(category, city, page_token=next_token)
            if "error" not in response2:
                prospects2 = extract_prospects(response2, category, city)
                for p in prospects2:
                    pid = p.get("google_place_id", p["name"])
                    if pid not in seen_place_ids:
                        seen_place_ids.add(pid)
                        if only_no_website and p["has_website"]:
                            continue
                        all_prospects.append(p)

        time.sleep(1)

    all_prospects.sort(key=lambda x: x["score"], reverse=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    result = {
        "city": city,
        "timestamp": ts,
        "total_found": len(all_prospects),
        "without_website": sum(1 for p in all_prospects if not p["has_website"]),
        "categories_searched": len(categories),
        "errors": errors,
        "prospects": all_prospects,
    }

    return result


def save_results(result: dict, output_dir: str = None):
    """Save discovery results to JSON file."""
    if output_dir:
        out_dir = Path(output_dir)
    else:
        out_dir = Path.home() / ".hermes" / "data" / "discovery"
    out_dir.mkdir(parents=True, exist_ok=True)

    city_slug = result["city"].lower().replace(" ", "_").replace("á", "a").replace("ã", "a")
    filename = f"discovery_{city_slug}_{result['timestamp']}.json"
    out_path = out_dir / filename
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(out_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Google Maps Business Discovery")
    parser.add_argument("--city", default="Cuiabá", help="City to search")
    parser.add_argument("--categories", help="Comma-separated categories (default: all)")
    parser.add_argument("--all-categories", action="store_true", help="Search all default categories")
    parser.add_argument("--no-website-only", action="store_true", help="Only return businesses without websites")
    parser.add_argument("--output-dir", help="Output directory for results")
    args = parser.parse_args()

    categories = None
    if args.categories:
        categories = [c.strip() for c in args.categories.split(",")]
    elif args.all_categories:
        categories = CATEGORIES

    print(f"Hermes Discovery: Buscando negócios em {args.city}...", file=sys.stderr)
    result = discover_businesses(args.city, categories, only_no_website=args.no_website_only)

    saved = save_results(result, args.output_dir)
    print(f"Salvo em: {saved}", file=sys.stderr)
    print(f"Total: {result['total_found']} | Sem website: {result['without_website']}", file=sys.stderr)

    print(json.dumps(result, ensure_ascii=False, indent=2))
