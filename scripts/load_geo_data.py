#!/usr/bin/env python3
"""UI-P0 B4: Carrega dados geográficos no PostGIS para o mapa v2.

O que faz:
  1. Cria extensão PostGIS + schema geo (idempotente)
  2. Cria tabelas geo.bairros + geo.business_points
  3. Carrega bairros de Cuiabá via Overpass (admin_level=9/10)
  4. Carrega prospects com lat/lng do SQLite → PostGIS + H3 cells (res 8/9)
  5. Atualiza prospect_count em geo.bairros (ST_Contains)

Roda na VPS: python3 scripts/load_geo_data.py
Requer: psycopg2-binary, h3>=3.7.6, requests
Docker: hermes-postgres deve estar UP com postgis/postgis:16-3.4
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
import httpx

# h3 — importado com fallback claro
try:
    import h3
    HAS_H3 = True
except ImportError:
    HAS_H3 = False
    print("WARN: h3 não instalado. Instale: pip install h3>=3.7.6. H3 cells não serão calculados.")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

HERMES_HOME = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))
DB_PATH = HERMES_HOME / "data" / "command_center.db"

PG_HOST = os.getenv("HERMES_PG_HOST", "localhost")
PG_PORT = int(os.getenv("HERMES_PG_PORT", "5432"))
PG_USER = os.getenv("HERMES_PG_USER", "hermes")
PG_PASS = os.getenv("HERMES_PG_PASSWORD", "")
PG_DB = os.getenv("HERMES_PG_DB", "hermes")

# Overpass acessível de dentro do container (via rede docker) ou do host
OVERPASS_URL = os.getenv("OVERPASS_URL", "http://localhost:12345")


def _pg_conn(autocommit: bool = False) -> psycopg2.extensions.connection:
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS, dbname=PG_DB,
        connect_timeout=15,
    )
    conn.autocommit = autocommit
    return conn


def init_postgis(conn) -> None:
    """Cria extensão PostGIS + schema geo + tabelas. Idempotente."""
    logger.info("Inicializando PostGIS + schema geo...")
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        cur.execute("CREATE SCHEMA IF NOT EXISTS geo")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS geo.bairros (
                id SERIAL PRIMARY KEY,
                osm_id BIGINT UNIQUE,
                name TEXT NOT NULL,
                admin_level INTEGER,
                geom GEOMETRY(MultiPolygon, 4326),
                prospect_count INTEGER DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_bairros_geom ON geo.bairros USING GIST(geom)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_bairros_name ON geo.bairros(name)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS geo.business_points (
                id INTEGER PRIMARY KEY,
                name TEXT,
                category TEXT,
                score INTEGER DEFAULT 0,
                stage TEXT,
                has_website BOOLEAN DEFAULT FALSE,
                h3_r8 TEXT,
                h3_r9 TEXT,
                status_color TEXT,
                geom GEOMETRY(Point, 4326),
                synced_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_business_geom ON geo.business_points USING GIST(geom)"
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_business_score ON geo.business_points(score DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_business_h3r8 ON geo.business_points(h3_r8)")

    conn.commit()
    logger.info("PostGIS schema geo pronto.")


def load_bairros(conn) -> int:
    """Carrega bairros de Cuiabá via Overpass. Retorna count inseridos/atualizados."""
    logger.info("Consultando Overpass para bairros de Cuiabá...")

    # Tenta admin_level=10 (bairros) depois admin_level=9 (sub-distritos)
    for level in [10, 9]:
        query = f"""
[out:json][timeout:90];
area["name"="Cuiabá"]["admin_level"="8"]["boundary"="administrative"]->.cuiaba;
(
  relation["boundary"="administrative"]["admin_level"="{level}"](area.cuiaba);
);
out geom;
"""
        try:
            resp = httpx.post(
                f"{OVERPASS_URL}/api/interpreter",
                content=query.encode(),
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            elements = data.get("elements", [])
            if elements:
                logger.info("Overpass: %d bairros encontrados (admin_level=%d)", len(elements), level)
                break
            logger.info("admin_level=%d sem resultados, tentando próximo nível...", level)
        except Exception as exc:
            logger.warning("Overpass query falhou (level=%d): %s", level, exc)
            elements = []

    if not elements:
        logger.warning("Nenhum bairro encontrado no Overpass. Inserindo boundary de Cuiabá como fallback.")
        elements = _cuiaba_municipality_fallback()

    count = 0
    with conn.cursor() as cur:
        for elem in elements:
            osm_id = elem.get("id")
            tags = elem.get("tags", {})
            name = tags.get("name") or tags.get("name:pt") or f"Área {osm_id}"
            admin_level = int(tags.get("admin_level", 10))

            # Constrói GeoJSON a partir da geometria Overpass
            geom_geojson = _overpass_to_geojson(elem)
            if not geom_geojson:
                continue

            try:
                cur.execute("""
                    INSERT INTO geo.bairros (osm_id, name, admin_level, geom)
                    VALUES (%s, %s, %s, ST_Multi(ST_GeomFromGeoJSON(%s)))
                    ON CONFLICT (osm_id) DO UPDATE
                        SET name = EXCLUDED.name,
                            geom = EXCLUDED.geom,
                            admin_level = EXCLUDED.admin_level
                """, (osm_id, name, admin_level, json.dumps(geom_geojson)))
                count += 1
            except Exception as exc:
                logger.warning("Falha inserir bairro %s (%s): %s", osm_id, name, exc)
                conn.rollback()
                continue

    conn.commit()
    logger.info("Bairros carregados: %d", count)
    return count


def _overpass_to_geojson(elem: dict) -> dict | None:
    """Converte elemento Overpass (relation/way) em GeoJSON Polygon."""
    members = elem.get("members", [])
    outer_rings = []

    for m in members:
        if m.get("role") == "outer" and m.get("type") == "way":
            coords = [[nd["lon"], nd["lat"]] for nd in m.get("geometry", [])]
            if len(coords) >= 4:
                # Fecha o anel se necessário
                if coords[0] != coords[-1]:
                    coords.append(coords[0])
                outer_rings.append(coords)

    if not outer_rings:
        # Way simples (não relation)
        coords = [[nd["lon"], nd["lat"]] for nd in elem.get("geometry", [])]
        if len(coords) >= 4:
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            outer_rings.append(coords)

    if not outer_rings:
        return None

    return {"type": "Polygon", "coordinates": outer_rings}


def _cuiaba_municipality_fallback() -> list:
    """Retorna o bounding box de Cuiabá como polígono fallback."""
    # Cuiabá bbox: lon -56.20 a -55.80, lat -15.75 a -15.40
    return [{
        "id": -1,
        "type": "relation",
        "tags": {"name": "Cuiabá (bbox)", "admin_level": "8"},
        "geometry": [
            {"lon": -56.20, "lat": -15.75},
            {"lon": -55.80, "lat": -15.75},
            {"lon": -55.80, "lat": -15.40},
            {"lon": -56.20, "lat": -15.40},
            {"lon": -56.20, "lat": -15.75},
        ],
        "members": [],
    }]


def _status_color(score: int, has_website: bool) -> str:
    if score >= 70 and not has_website:
        return "warm"   # oportunidade clara
    if score >= 50:
        return "good"
    if has_website and score < 30:
        return "cool"   # já consolidado
    return "neutral"


def load_business_points(conn) -> int:
    """Lê prospects com lat/lng do SQLite e insere em geo.business_points."""
    if not DB_PATH.exists():
        logger.warning("command_center.db não encontrado em %s", DB_PATH)
        return 0

    sqlite_conn = sqlite3.connect(str(DB_PATH))
    sqlite_conn.row_factory = sqlite3.Row
    try:
        rows = sqlite_conn.execute("""
            SELECT id, name, category, score, stage, has_website, lat, lng
            FROM prospects
            WHERE lat IS NOT NULL AND lng IS NOT NULL
              AND lat != 0 AND lng != 0
        """).fetchall()
    finally:
        sqlite_conn.close()

    logger.info("Carregando %d prospects com coordenadas...", len(rows))
    count = 0
    with conn.cursor() as cur:
        for r in rows:
            pid = r["id"]
            lat, lng = r["lat"], r["lng"]
            score = r["score"] or 0
            has_website = bool(r["has_website"])
            stage = r["stage"] or "discovered"
            status_color = _status_color(score, has_website)

            h3_r8 = h3_r9 = None
            if HAS_H3:
                try:
                    h3_r8 = h3.latlng_to_cell(lat, lng, 8)
                    h3_r9 = h3.latlng_to_cell(lat, lng, 9)
                except Exception:
                    pass

            try:
                cur.execute("""
                    INSERT INTO geo.business_points
                        (id, name, category, score, stage, has_website,
                         h3_r8, h3_r9, status_color, geom, synced_at)
                    VALUES
                        (%s, %s, %s, %s, %s, %s,
                         %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        category = EXCLUDED.category,
                        score = EXCLUDED.score,
                        stage = EXCLUDED.stage,
                        has_website = EXCLUDED.has_website,
                        h3_r8 = EXCLUDED.h3_r8,
                        h3_r9 = EXCLUDED.h3_r9,
                        status_color = EXCLUDED.status_color,
                        geom = EXCLUDED.geom,
                        synced_at = NOW()
                """, (
                    pid, r["name"], r["category"], score, stage, has_website,
                    h3_r8, h3_r9, status_color, lng, lat,
                ))
                count += 1
            except Exception as exc:
                logger.warning("Falha inserir prospect id=%d: %s", pid, exc)
                conn.rollback()
                continue

    conn.commit()
    logger.info("business_points carregados: %d", count)
    return count


def update_bairro_counts(conn) -> None:
    """Atualiza prospect_count em geo.bairros via ST_Contains."""
    logger.info("Atualizando contagem de prospects por bairro...")
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE geo.bairros b
            SET prospect_count = (
                SELECT COUNT(*)
                FROM geo.business_points p
                WHERE ST_Contains(b.geom, p.geom)
            )
        """)
    conn.commit()
    logger.info("Contagens atualizadas.")


def main() -> None:
    logger.info("=== load_geo_data.py UI-P0 B4 ===")
    conn = _pg_conn()
    try:
        init_postgis(conn)
        bairros = load_bairros(conn)
        prospects = load_business_points(conn)
        if bairros > 0 and prospects > 0:
            update_bairro_counts(conn)

        # Relatório final
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM geo.bairros")
            b_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM geo.business_points")
            p_count = cur.fetchone()[0]

        logger.info("=== CONCLUÍDO ===")
        logger.info("geo.bairros:         %d", b_count)
        logger.info("geo.business_points: %d", p_count)

        if p_count == 0:
            logger.warning(
                "AVISO: nenhum prospect carregado. "
                "Verifique se command_center.db existe em %s e tem prospects com lat/lng.",
                DB_PATH,
            )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
