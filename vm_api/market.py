"""Hermes Cloud Studio — Market Intelligence REST API (H2-F7).

Endpoints:
  GET /api/market/signals?type=&cnae=&region=&limit=
    → signals from cnpj.market_signals (Postgres)
  GET /api/market/heatmap
    → CNAE × bairro density matrix for dashboard heatmap

Auth: X-Hermes-Token via standard VM auth middleware.

API contract (consumed by future dashboard Market-Intel page):
  /api/market/signals:
    { signals: [{ id, signal_type, cnae, cnae_label, region,
                  metric_value, rank, meta, computed_at }],
      total: int }

  /api/market/heatmap:
    { heatmap: { cnae: { bairro: count } },
      cnaes: [str], total_cells: int }
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter()
logger = logging.getLogger("hermes.vm_api.market")


def _pg():
    """Lazy import + connect to hermes-postgres. Raises RuntimeError if PG unavailable."""
    from brain.market_analyzer import _pg_connect
    return _pg_connect()


@router.get("/api/market/signals")
async def market_signals(
    request: Request,
    type: Optional[str] = Query(default=None, alias="type"),
    cnae: Optional[str] = Query(default=None),
    region: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
):
    """Return market signals from cnpj.market_signals.

    Filters: type (density|churn_velocity|new_reg_velocity|opportunity),
             cnae (exact CHAR(7)), region (ILIKE partial match).
    Ordered by signal_type ASC, rank ASC.
    """
    try:
        conn = _pg()
    except Exception as exc:
        logger.warning("market_signals: PG unavailable — %s", exc)
        raise HTTPException(status_code=503, detail=f"Market signals DB unavailable: {exc}")

    try:
        conditions: list[str] = []
        params: list = []

        if type:
            conditions.append("signal_type = %s")
            params.append(type)
        if cnae:
            conditions.append("cnae = %s")
            params.append(cnae)
        if region:
            conditions.append("region ILIKE %s")
            params.append(f"%{region}%")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(limit)

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, signal_type, cnae, cnae_label, region,
                       metric_value, rank, meta, computed_at
                FROM cnpj.market_signals
                {where}
                ORDER BY signal_type ASC, rank ASC NULLS LAST
                LIMIT %s
                """,
                params,
            )
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
    except Exception as exc:
        logger.exception("market_signals query error")
        raise HTTPException(status_code=500, detail=f"Query error: {exc}")
    finally:
        conn.close()

    result = []
    for row in rows:
        d = dict(zip(cols, row))
        if d.get("computed_at"):
            d["computed_at"] = d["computed_at"].isoformat()
        if d.get("metric_value") is not None:
            d["metric_value"] = float(d["metric_value"])
        if d.get("meta") and isinstance(d["meta"], str):
            try:
                d["meta"] = json.loads(d["meta"])
            except Exception:
                pass
        result.append(d)

    return {"signals": result, "total": len(result)}


@router.get("/api/market/heatmap")
async def market_heatmap(request: Request):
    """Return CNAE × bairro density matrix for heatmap visualization.

    Response: { heatmap: { cnae: { bairro: count } }, cnaes: [...], total_cells: int }
    Covers top 20 CNAEs by total count in Cuiabá.
    """
    try:
        conn = _pg()
    except Exception as exc:
        logger.warning("market_heatmap: PG unavailable — %s", exc)
        raise HTTPException(status_code=503, detail=f"Heatmap DB unavailable: {exc}")

    try:
        from brain.market_analyzer import compute_heatmap
        rows = compute_heatmap(conn)
    except Exception as exc:
        logger.exception("market_heatmap compute error")
        raise HTTPException(status_code=500, detail=f"Heatmap compute error: {exc}")
    finally:
        conn.close()

    pivot: dict[str, dict[str, int]] = {}
    for r in rows:
        cnae = r.get("cnae") or "?"
        bairro = r.get("bairro") or "—"
        pivot.setdefault(cnae, {})[bairro] = int(r.get("count") or 0)

    return {
        "heatmap": pivot,
        "cnaes": list(pivot.keys()),
        "total_cells": len(rows),
    }
