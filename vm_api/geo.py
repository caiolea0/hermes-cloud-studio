"""GET /api/geo/* — GeoJSON endpoints para dashboard-v2 map.

Queries PostGIS (geo schema): business_points (prospects com H3) + bairros (Cuiabá).
Auth: X-Hermes-Token via auth_middleware padrão.
Retorna FeatureCollection compatível com MapLibre addSource type='geojson'.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()
logger = logging.getLogger("hermes_api_v2")

# Cache bairros (PostGIS spatial join é custoso — 5min TTL)
_bairros_cache: dict | None = None
_bairros_cache_ts: float = 0.0
_BAIRROS_TTL = 300.0


def _pg_conn():
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(
        host=os.getenv("HERMES_PG_HOST", "localhost"),
        port=int(os.getenv("HERMES_PG_PORT", "5432")),
        user=os.getenv("HERMES_PG_USER", "hermes"),
        password=os.getenv("HERMES_PG_PASSWORD", ""),
        database=os.getenv("HERMES_PG_DB", "hermes"),
        connect_timeout=10,
        options="-c statement_timeout=15000",
    )
    conn.set_session(readonly=True, autocommit=True)
    return conn


@router.get("/api/geo/prospects")
def geo_prospects(
    min_score: Optional[int] = Query(None, ge=0, le=100),
    stage: Optional[str] = Query(None),
    limit: int = Query(2000, ge=1, le=5000),
):
    """FeatureCollection de prospects com lat/lng e H3 cells.

    Propriedades por feature: id, name, category, score, stage,
    has_website, h3_r8, h3_r9, status_color.
    Fallback gracioso se geo.business_points ainda não existe (load_geo_data.py não rodou).
    """
    try:
        conn = _pg_conn()
    except Exception as exc:
        logger.warning("geo/prospects: falha conectar PG: %s", exc)
        return {"type": "FeatureCollection", "features": [], "note": str(exc)}

    try:
        cur = conn.cursor()

        wheres = ["geom IS NOT NULL"]
        params: list = []

        if min_score is not None:
            wheres.append("score >= %s")
            params.append(min_score)
        if stage:
            wheres.append("stage = %s")
            params.append(stage)

        params.append(limit)

        sql = f"""
            SELECT
                id, name, category, score, stage,
                has_website, h3_r8, h3_r9, status_color,
                ST_AsGeoJSON(geom)::json AS geometry
            FROM geo.business_points
            WHERE {" AND ".join(wheres)}
            ORDER BY score DESC
            LIMIT %s
        """

        cur.execute(sql, params)
        rows = cur.fetchall()

        features = []
        for row in rows:
            (pid, name, category, score, stage_val,
             has_website, h3_r8, h3_r9, status_color, geom) = row
            features.append({
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "id": pid,
                    "name": name,
                    "category": category,
                    "score": score,
                    "stage": stage_val,
                    "has_website": bool(has_website),
                    "h3_r8": h3_r8,
                    "h3_r9": h3_r9,
                    "status_color": status_color,
                },
            })

        return {"type": "FeatureCollection", "features": features, "count": len(features)}

    except Exception as exc:
        if "geo.business_points" in str(exc) or 'does not exist' in str(exc):
            logger.info("geo/prospects: geo schema não inicializado ainda — retornando vazio")
            return {
                "type": "FeatureCollection",
                "features": [],
                "note": "geo schema não inicializado — execute scripts/load_geo_data.py",
            }
        logger.exception("geo/prospects query error")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()


@router.get("/api/geo/bairros")
def geo_bairros():
    """FeatureCollection de bairros de Cuiabá com contagens de oportunidade (PostGIS join).

    Propriedades: id, name, admin_level, prospect_count, avg_score, hot_count.
    Resultado cacheado por 5 minutos (join espacial PostGIS é custoso).
    """
    global _bairros_cache, _bairros_cache_ts

    if _bairros_cache is not None and time.time() - _bairros_cache_ts < _BAIRROS_TTL:
        return _bairros_cache

    try:
        conn = _pg_conn()
    except Exception as exc:
        logger.warning("geo/bairros: falha conectar PG: %s", exc)
        if _bairros_cache is not None:
            return _bairros_cache
        return {"type": "FeatureCollection", "features": [], "note": str(exc)}

    try:
        cur = conn.cursor()
        # PostGIS spatial join: conta prospects dentro de cada bairro.
        # ST_MakeValid corrige auto-interseções nos polígonos dos bairros (dados OSM brutos).
        cur.execute("""
            WITH bairros_valid AS (
                SELECT id, name, admin_level,
                       ST_MakeValid(geom) AS geom_v,
                       geom
                FROM geo.bairros
                WHERE geom IS NOT NULL
            )
            SELECT
                b.id, b.name, b.admin_level,
                COUNT(bp.id)::int                                       AS prospect_count,
                COALESCE(ROUND(AVG(bp.score) FILTER (WHERE bp.score > 0)), 0)::int AS avg_score,
                COUNT(bp.id) FILTER (WHERE bp.score >= 70)::int         AS hot_count,
                COUNT(bp.id) FILTER (WHERE bp.score >= 50 AND bp.score < 70)::int AS medium_count,
                ST_AsGeoJSON(b.geom)::json                               AS geometry
            FROM bairros_valid b
            LEFT JOIN geo.business_points bp ON ST_Within(bp.geom, b.geom_v)
            GROUP BY b.id, b.name, b.admin_level, b.geom
            ORDER BY b.name
        """)
        rows = cur.fetchall()

        features = []
        for row in rows:
            bid, name, admin_level, prospect_count, avg_score, hot_count, medium_count, geom = row
            features.append({
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "id": bid,
                    "name": name,
                    "admin_level": admin_level,
                    "prospect_count": prospect_count,
                    "avg_score": avg_score,
                    "hot_count": hot_count,
                    "medium_count": medium_count,
                },
            })

        result = {"type": "FeatureCollection", "features": features, "count": len(features)}
        _bairros_cache = result
        _bairros_cache_ts = time.time()
        return result

    except Exception as exc:
        if "geo.bairros" in str(exc) or 'does not exist' in str(exc):
            logger.info("geo/bairros: geo schema não inicializado ainda — retornando vazio")
            return {
                "type": "FeatureCollection",
                "features": [],
                "note": "geo schema não inicializado — execute scripts/load_geo_data.py",
            }
        logger.exception("geo/bairros query error")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()
