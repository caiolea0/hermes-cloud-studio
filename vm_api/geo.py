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

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger("hermes_api_v2")

# Cache bairros (PostGIS spatial join é custoso — 5min TTL)
_bairros_cache: dict | None = None
_bairros_cache_ts: float = 0.0
_BAIRROS_TTL = 300.0

# Cache hexes (60s TTL, keyed por params tuple)
_hexes_cache: dict = {}
_hexes_cache_ts: dict = {}
_HEXES_TTL = 60.0

# Cache categories (5min TTL)
_categories_cache: dict | None = None
_categories_cache_ts: float = 0.0
_CATEGORIES_TTL = 300.0


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


def _pg_conn_write():
    """Conexão PostgreSQL com write access (para sweep_state)."""
    import psycopg2

    conn = psycopg2.connect(
        host=os.getenv("HERMES_PG_HOST", "localhost"),
        port=int(os.getenv("HERMES_PG_PORT", "5432")),
        user=os.getenv("HERMES_PG_USER", "hermes"),
        password=os.getenv("HERMES_PG_PASSWORD", ""),
        database=os.getenv("HERMES_PG_DB", "hermes"),
        connect_timeout=10,
        options="-c statement_timeout=15000",
    )
    conn.autocommit = False
    return conn


def init_geo_migrations():
    """Cria geo.sweep_state no PostgreSQL (idempotente). Chamado no boot da API."""
    try:
        conn = _pg_conn_write()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS geo.sweep_state (
                h3_cell TEXT PRIMARY KEY,
                resolution SMALLINT NOT NULL,
                swept_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                swept_by TEXT,
                prospect_count_at_sweep INT,
                notes TEXT
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_sweep_state_swept_at
            ON geo.sweep_state(swept_at)
        """)
        conn.commit()
        logger.info("geo migrations: geo.sweep_state OK")
    except Exception as exc:
        logger.warning("geo migrations: geo.sweep_state falhou (geo schema pode não existir ainda): %s", exc)
    finally:
        try:
            conn.close()
        except Exception:
            pass


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


@router.get("/api/geo/hexes")
def geo_hexes(
    resolution: int = Query(8, ge=7, le=9),
    min_score: Optional[int] = Query(None, ge=0, le=100),
    stage: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    missing_service: Optional[str] = Query(None),
):
    """Retorna hexes H3 agregados sem geometry (cliente desenha via h3-js).

    Propriedades por hex: h3_cell, prospect_count, avg_score, hot_count,
    medium_count, cool_count, has_site_ratio, category_top.
    Cache 60s por combinação de parâmetros.
    """
    cache_key = (resolution, min_score, stage, category, missing_service)
    now = time.time()
    if cache_key in _hexes_cache and now - _hexes_cache_ts.get(cache_key, 0) < _HEXES_TTL:
        return _hexes_cache[cache_key]

    h3_col = "h3_r8" if resolution == 8 else ("h3_r9" if resolution == 9 else "h3_r8")

    try:
        conn = _pg_conn()
    except Exception as exc:
        logger.warning("geo/hexes: falha conectar PG: %s", exc)
        return {"features": [], "count": 0, "note": str(exc)}

    try:
        cur = conn.cursor()

        wheres = [f"{h3_col} IS NOT NULL"]
        params: list = []

        if min_score is not None:
            wheres.append("score >= %s")
            params.append(min_score)
        if stage:
            wheres.append("stage = %s")
            params.append(stage)
        if category:
            wheres.append("category = %s")
            params.append(category)
        if missing_service == "website":
            wheres.append("has_website = false")

        where_clause = " AND ".join(wheres)

        sql = f"""
            SELECT
                {h3_col}                                                           AS h3_cell,
                COUNT(*)::int                                                       AS prospect_count,
                COALESCE(ROUND(AVG(score) FILTER (WHERE score > 0)), 0)::int        AS avg_score,
                COUNT(*) FILTER (WHERE score >= 70)::int                            AS hot_count,
                COUNT(*) FILTER (WHERE score >= 50 AND score < 70)::int             AS medium_count,
                COUNT(*) FILTER (WHERE score < 50 OR score = 0)::int                AS cool_count,
                COALESCE(AVG(has_website::int)::float, 0.0)                         AS has_site_ratio,
                mode() WITHIN GROUP (ORDER BY category)                             AS category_top
            FROM geo.business_points
            WHERE {where_clause}
            GROUP BY {h3_col}
            ORDER BY prospect_count DESC
        """

        cur.execute(sql, params)
        rows = cur.fetchall()

        features = []
        for row in rows:
            h3_cell, prospect_count, avg_score, hot_count, medium_count, cool_count, has_site_ratio, category_top = row
            features.append({
                "h3_cell": h3_cell,
                "prospect_count": prospect_count,
                "avg_score": avg_score,
                "hot_count": hot_count,
                "medium_count": medium_count,
                "cool_count": cool_count,
                "has_site_ratio": round(float(has_site_ratio or 0), 3),
                "category_top": category_top or "",
            })

        result = {"features": features, "count": len(features)}
        _hexes_cache[cache_key] = result
        _hexes_cache_ts[cache_key] = now
        return result

    except Exception as exc:
        if "geo.business_points" in str(exc) or 'does not exist' in str(exc):
            return {"features": [], "count": 0, "note": "geo schema não inicializado"}
        logger.exception("geo/hexes query error")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()


@router.get("/api/geo/categories")
def geo_categories(limit: int = Query(20, ge=1, le=100)):
    """Distinct categories de geo.business_points ordenado por count desc."""
    global _categories_cache, _categories_cache_ts

    now = time.time()
    if _categories_cache is not None and now - _categories_cache_ts < _CATEGORIES_TTL:
        return _categories_cache

    try:
        conn = _pg_conn()
    except Exception as exc:
        logger.warning("geo/categories: falha conectar PG: %s", exc)
        return {"items": [], "note": str(exc)}

    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT category, COUNT(*)::int AS cnt FROM geo.business_points "
            "WHERE category IS NOT NULL GROUP BY category ORDER BY cnt DESC LIMIT %s",
            (limit,),
        )
        rows = cur.fetchall()
        result = {"items": [{"category": r[0], "count": r[1]} for r in rows]}
        _categories_cache = result
        _categories_cache_ts = now
        return result
    except Exception as exc:
        if 'does not exist' in str(exc):
            return {"items": [], "note": "geo schema não inicializado"}
        logger.exception("geo/categories query error")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()


# ── Sweep State ──────────────────────────────────────────────────────────────


class SweepPayload(BaseModel):
    h3_cells: list[str]
    resolution: int = 8


@router.post("/api/geo/sweep")
def post_sweep(payload: SweepPayload):
    """Marca h3_cells como varridos no geo.sweep_state (upsert)."""
    if not payload.h3_cells:
        raise HTTPException(status_code=422, detail="h3_cells vazio")
    if len(payload.h3_cells) > 2000:
        raise HTTPException(status_code=422, detail="máximo 2000 células por request")

    try:
        conn = _pg_conn_write()
    except Exception as exc:
        logger.error("geo/sweep POST: falha conectar PG: %s", exc)
        raise HTTPException(status_code=503, detail="banco indisponível")

    try:
        cur = conn.cursor()
        inserted = 0
        for cell in payload.h3_cells:
            cur.execute(
                """
                INSERT INTO geo.sweep_state (h3_cell, resolution, swept_at)
                VALUES (%s, %s, now())
                ON CONFLICT (h3_cell) DO UPDATE SET swept_at = now(), resolution = EXCLUDED.resolution
                """,
                (cell, payload.resolution),
            )
            inserted += cur.rowcount
        # total swept
        cur.execute("SELECT COUNT(*) FROM geo.sweep_state WHERE resolution = %s", (payload.resolution,))
        total = cur.fetchone()[0]
        conn.commit()
        return {"inserted": inserted, "total_swept": total}
    except Exception as exc:
        conn.rollback()
        logger.exception("geo/sweep POST error")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()


@router.get("/api/geo/sweep")
def get_sweep(resolution: int = Query(8, ge=7, le=9)):
    """Retorna células varridas para fog-of-war."""
    try:
        conn = _pg_conn()
    except Exception as exc:
        logger.warning("geo/sweep GET: falha conectar PG: %s", exc)
        return {"cells": [], "total": 0, "last_swept_at": None}

    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT h3_cell, MAX(swept_at) AS last_swept_at FROM geo.sweep_state "
            "WHERE resolution = %s GROUP BY h3_cell ORDER BY last_swept_at DESC",
            (resolution,),
        )
        rows = cur.fetchall()
        cells = [r[0] for r in rows]
        last_swept_at = rows[0][1].isoformat() if rows else None
        return {"cells": cells, "total": len(cells), "last_swept_at": last_swept_at}
    except Exception as exc:
        if 'does not exist' in str(exc):
            return {"cells": [], "total": 0, "last_swept_at": None}
        logger.exception("geo/sweep GET error")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()


@router.delete("/api/geo/sweep/{h3_cell}")
def delete_sweep(h3_cell: str = Path(..., min_length=10, max_length=20)):
    """Remove uma célula do geo.sweep_state (undo varredura)."""
    try:
        conn = _pg_conn_write()
    except Exception as exc:
        logger.error("geo/sweep DELETE: falha conectar PG: %s", exc)
        raise HTTPException(status_code=503, detail="banco indisponível")

    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM geo.sweep_state WHERE h3_cell = %s", (h3_cell,))
        deleted = cur.rowcount
        conn.commit()
        if deleted == 0:
            raise HTTPException(status_code=404, detail="célula não encontrada no sweep_state")
        return {"deleted": deleted, "h3_cell": h3_cell}
    except HTTPException:
        raise
    except Exception as exc:
        conn.rollback()
        logger.exception("geo/sweep DELETE error")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()
