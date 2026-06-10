"""hermes-prospects MCP — 7 tools CRUD + scoring.

D3 strict: scoring (`score_lead`) MANTÉM lógica Python local determinística.
Reads complexos (search/list_top/get_campaign_stats/get_by_status) PREFEREM
gateway dispatch pra `mcp.postgres.query` quando Postgres MCP Pro plug
(F.5.6) — SQLite local é fallback default até lá.

Tools (7):
  1. search_prospects   — filtro city/category/min_score/limit
  2. score_lead         — Python determinístico (D3 strict)
  3. mark_converted     — UPDATE stage='converted' + version bump
  4. get_campaign_stats — agg count by stage + period
  5. enrich_pipeline    — placeholder F.5.6 (apollo/hunter/firecrawl MCP)
  6. list_top_scored    — ORDER BY score DESC LIMIT
  7. get_by_status      — WHERE stage = ?

Run: python mcps/hermes-prospects/server.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover — VM-only dep
    raise SystemExit(
        "fastmcp não instalado. F.5.2 exige fastmcp>=3.0. Erro: " + str(exc)
    )

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

MCP_NAME = "hermes-prospects"
MCP_VERSION = "0.1.0-f5.2"

GATEWAY_URL = os.getenv("HERMES_GATEWAY_URL", "http://127.0.0.1:55401")
GATEWAY_TOKEN = os.getenv("HERMES_GATEWAY_OAUTH_SECRET", "")
PREFER_POSTGRES = os.getenv("HERMES_PROSPECTS_USE_POSTGRES_MCP", "0") == "1"

_VM_DB = Path(os.path.expanduser("~/.hermes/data/command_center.db"))
_PC_DB = _REPO_ROOT / "hermes_local.db"

VALID_STAGES = frozenset({
    "discovered", "qualified", "audited", "contacted", "converted", "dead",
})

_SENSITIVE_KEYS = frozenset({
    "li_at", "token", "cookie", "password", "auth", "authorization",
    "jsessionid", "csrf", "api_key", "secret", "bearer",
})


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if str(k).strip().lower() in _SENSITIVE_KEYS
                else _sanitize(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _db_path() -> Path:
    """VM path primary, PC fallback (smoke local)."""
    if _VM_DB.exists():
        return _VM_DB
    return _PC_DB


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


async def _postgres_query_via_gateway(
    sql: str, params: list | None = None
) -> list[dict] | None:
    """Best-effort dispatch pra mcp.postgres.query via gateway.

    Returns None se gateway/postgres MCP indisponível (caller fallback SQLite).
    """
    if not PREFER_POSTGRES or httpx is None:
        return None
    headers = {"Content-Type": "application/json"}
    if GATEWAY_TOKEN:
        headers["Authorization"] = f"Bearer {GATEWAY_TOKEN}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                f"{GATEWAY_URL}/dispatch/postgres/query",
                json={"sql": sql, "params": params or []},
                headers=headers,
            )
        if r.status_code == 200:
            data = r.json()
            return data.get("rows", []) if isinstance(data, dict) else None
        # 503 = postgres MCP not yet wired (F.5.6). Silent fallback SQLite.
        return None
    except Exception:
        return None


mcp = FastMCP(MCP_NAME)


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


@mcp.tool()
async def search_prospects(
    city: str = "",
    category: str = "",
    min_score: int = 0,
    limit: int = 50,
) -> dict:
    """Busca prospects com filtros opcionais (city, category, min_score).

    Prefere `mcp.postgres.query` via gateway (D3 — single source truth).
    Fallback SQLite local até F.5.6 plug Postgres MCP Pro.

    Args:
        city: filtra por city exato (vazio = sem filtro).
        category: filtra por category exato.
        min_score: score >= min_score (default 0 = sem floor).
        limit: max rows (default 50, max 500).

    Returns:
        dict {ok, source: "postgres-mcp"|"sqlite", count, rows[]}
    """
    limit = max(1, min(int(limit), 500))
    where = ["1=1"]
    params: list[Any] = []
    if city:
        where.append("city = ?")
        params.append(city)
    if category:
        where.append("category = ?")
        params.append(category)
    if min_score:
        where.append("score >= ?")
        params.append(int(min_score))
    sql = (
        f"SELECT * FROM prospects WHERE {' AND '.join(where)} "
        f"ORDER BY score DESC LIMIT {limit}"
    )
    pg_rows = await _postgres_query_via_gateway(sql, params)
    if pg_rows is not None:
        return _sanitize({
            "ok": True, "source": "postgres-mcp",
            "count": len(pg_rows), "rows": pg_rows,
        })
    with _connect() as conn:
        rows = [_row_to_dict(r) for r in conn.execute(sql, params)]
    return _sanitize({
        "ok": True, "source": "sqlite",
        "count": len(rows), "rows": rows,
    })


@mcp.tool()
async def score_lead(profile_data: dict) -> dict:
    """Score lead determinístico Python local (D3 strict — NUNCA delega).

    Heurística 0-100 baseada em sinais positivos (sem site → +25 sinal
    oportunidade design), categoria valiosa, dados completos, rating Google.

    Args:
        profile_data: dict campos prospects (name, category, website,
                      has_website, google_rating, google_reviews, phone,
                      email, social_*).

    Returns:
        dict {score, breakdown[], reason}
    """
    score = 50.0
    breakdown: list[dict] = []

    has_website = profile_data.get("has_website")
    website = (profile_data.get("website") or "").strip()
    has_site_real = bool(website) or has_website is True
    if not has_site_real and (has_website is False or has_website is None):
        score += 25.0
        breakdown.append({"signal": "no_website", "delta": +25})
    elif has_site_real:
        score -= 5.0
        breakdown.append({"signal": "has_website_baseline", "delta": -5})

    category = (profile_data.get("category") or "").lower().strip()
    valuable_categories = {
        "restaurant", "restaurante", "clinica", "clínica", "medico",
        "advogado", "lawyer", "dentista", "dentist", "salon", "salao",
        "academia", "gym", "estetica", "estética", "loja", "store",
    }
    if any(v in category for v in valuable_categories):
        score += 10.0
        breakdown.append({"signal": "category_valuable", "delta": +10})

    rating = profile_data.get("google_rating")
    if isinstance(rating, (int, float)) and rating >= 4.0:
        score += 5.0
        breakdown.append({"signal": "rating_4plus", "delta": +5})

    reviews = profile_data.get("google_reviews")
    if isinstance(reviews, int) and reviews >= 20:
        score += 5.0
        breakdown.append({"signal": "reviews_20plus", "delta": +5})

    if profile_data.get("phone"):
        score += 2.0
        breakdown.append({"signal": "phone_present", "delta": +2})
    if profile_data.get("email"):
        score += 3.0
        breakdown.append({"signal": "email_present", "delta": +3})
    if profile_data.get("social_instagram"):
        score += 3.0
        breakdown.append({"signal": "instagram_present", "delta": +3})

    score = max(0.0, min(100.0, score))
    return {
        "score": round(score, 1),
        "breakdown": breakdown,
        "reason": "deterministic Python scoring (D3 strict, no LLM, no MCP delegate)",
    }


@mcp.tool()
async def mark_converted(prospect_id: int, note: str = "") -> dict:
    """UPDATE stage='converted' + version bump (MERGED-006 path).

    Args:
        prospect_id: ID inteiro.
        note: nota livre adicionada em notes (truncada 500).

    Returns:
        dict {ok, prospect_id, prev_stage, new_stage}
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, stage, notes, version FROM prospects WHERE id = ?",
            (int(prospect_id),),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"prospect {prospect_id} not found"}
        prev_stage = row["stage"]
        note_safe = (note or "")[:500]
        new_notes = (row["notes"] or "")
        if note_safe:
            sep = "\n---\n" if new_notes else ""
            new_notes = f"{new_notes}{sep}[converted] {note_safe}"
        conn.execute(
            "UPDATE prospects SET stage='converted', notes=?, "
            "version = version + 1, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (new_notes, int(prospect_id)),
        )
        conn.commit()
    return {
        "ok": True,
        "prospect_id": int(prospect_id),
        "prev_stage": prev_stage,
        "new_stage": "converted",
    }


@mcp.tool()
async def get_campaign_stats(period_days: int = 7) -> dict:
    """Agregado count por stage nos últimos N dias.

    Prefere Postgres MCP (D3). Fallback SQLite.

    Args:
        period_days: janela em dias (default 7, max 90).

    Returns:
        dict {ok, source, period_days, total, by_stage{}}
    """
    period_days = max(1, min(int(period_days), 90))
    cutoff = time.time() - period_days * 86400
    sql = (
        "SELECT stage, COUNT(*) as n FROM prospects "
        "WHERE COALESCE(updated_at, created_at) >= datetime(?, 'unixepoch') "
        "GROUP BY stage"
    )
    pg_rows = await _postgres_query_via_gateway(sql, [cutoff])
    if pg_rows is not None:
        by_stage = {r.get("stage", "unknown"): int(r.get("n", 0)) for r in pg_rows}
        return {
            "ok": True, "source": "postgres-mcp",
            "period_days": period_days,
            "total": sum(by_stage.values()),
            "by_stage": by_stage,
        }
    with _connect() as conn:
        rows = list(conn.execute(sql, (cutoff,)))
    by_stage = {r["stage"]: r["n"] for r in rows}
    return {
        "ok": True, "source": "sqlite",
        "period_days": period_days,
        "total": sum(by_stage.values()),
        "by_stage": by_stage,
    }


@mcp.tool()
async def enrich_pipeline(prospect_id: int, provider: str = "firecrawl") -> dict:
    """Enrich prospect via MCP externo (apollo/hunter/firecrawl) — F.5.6 plug.

    F.5.2 scaffold: retorna handle + provider plan. Real dispatch acontece
    via gateway quando Apollo/Hunter/Firecrawl MCPs forem plugged (F.5.6).

    Args:
        prospect_id: ID prospect.
        provider: apollo | hunter | firecrawl | omnisearch (validated).

    Returns:
        dict {ok, prospect_id, provider, status, next_step}
    """
    valid = {"apollo", "hunter", "firecrawl", "omnisearch"}
    if provider not in valid:
        return {"ok": False, "error": f"provider must be one of {sorted(valid)}"}
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name, website FROM prospects WHERE id = ?",
            (int(prospect_id),),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": f"prospect {prospect_id} not found"}
    return {
        "ok": True,
        "prospect_id": int(prospect_id),
        "provider": provider,
        "status": "pending_f5_6_mcp_plug",
        "next_step": (
            f"F.5.6 plug {provider} MCP no gateway. Tool então invoca "
            f"mcp.{provider}.enrich via dispatch + persiste em prospects."
        ),
    }


@mcp.tool()
async def list_top_scored(limit: int = 10, min_score: int = 0) -> dict:
    """Top N prospects por score desc.

    Args:
        limit: max rows (default 10, max 100).
        min_score: floor opcional.

    Returns:
        dict {ok, source, count, rows[]}
    """
    limit = max(1, min(int(limit), 100))
    sql = (
        "SELECT id, name, city, category, score, stage, website "
        "FROM prospects WHERE score >= ? "
        "ORDER BY score DESC, id ASC LIMIT ?"
    )
    params: list[Any] = [int(min_score), limit]
    pg_rows = await _postgres_query_via_gateway(sql, params)
    if pg_rows is not None:
        return {
            "ok": True, "source": "postgres-mcp",
            "count": len(pg_rows), "rows": pg_rows,
        }
    with _connect() as conn:
        rows = [_row_to_dict(r) for r in conn.execute(sql, params)]
    return {
        "ok": True, "source": "sqlite",
        "count": len(rows), "rows": rows,
    }


@mcp.tool()
async def get_by_status(status: str, limit: int = 50) -> dict:
    """Lista prospects por stage exato.

    Args:
        status: discovered|qualified|audited|contacted|converted|dead.
        limit: max rows (default 50, max 500).

    Returns:
        dict {ok, source, status, count, rows[]}
    """
    if status not in VALID_STAGES:
        return {
            "ok": False,
            "error": f"status must be one of {sorted(VALID_STAGES)}",
        }
    limit = max(1, min(int(limit), 500))
    sql = (
        "SELECT id, name, city, category, score, stage, updated_at "
        "FROM prospects WHERE stage = ? "
        "ORDER BY updated_at DESC LIMIT ?"
    )
    params = [status, limit]
    pg_rows = await _postgres_query_via_gateway(sql, params)
    if pg_rows is not None:
        return {
            "ok": True, "source": "postgres-mcp", "status": status,
            "count": len(pg_rows), "rows": pg_rows,
        }
    with _connect() as conn:
        rows = [_row_to_dict(r) for r in conn.execute(sql, params)]
    return {
        "ok": True, "source": "sqlite", "status": status,
        "count": len(rows), "rows": rows,
    }


def main() -> None:
    transport = os.getenv("HERMES_MCP_TRANSPORT", "stdio").lower()
    if transport == "http":
        port = int(os.getenv("HERMES_HERMES_PROSPECTS_PORT", "55412"))
        mcp.run(transport="http", host="127.0.0.1", port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
