"""Hermes ContextForge Gateway — FastMCP 3.0 multiplex layer.

F.5.1 scaffold deliverable:
- HTTP server bind loopback 127.0.0.1:55401 (VM-only, never public)
- /health endpoint (consumed by hermes_api_v2 STRICT_MODE startup gate)
- /tools endpoint (consumed by F.8 observability + F.9 pipeline studio)
- /audit-log endpoint (read-only audit trail)
- Config loaded from config.yaml — upstream MCPs as `status: pending` placeholders
- OAuth 2.1 bypass loopback (dev mode), enforced when HERMES_STRICT_MCP=1

F.5.2 entrega real custom MCPs (3 customs ACTIVE).
F.5.3 entrega dispatch real fastmcp.Client + MCPClientPool + S2 logging mcp_calls
       + seed mcp_registry 11 rows.
F.5.4 entrega validate_implementation.py phase F grep-audit.

F.5.3 NOT YET IMPLEMENTED (by design):
- OAuth 2.1 token issuance (F.5.6 quando primeiro MCP público demandar JWT)
- ToolRegistry.invoke middleware F.6 (Brain wrap superset deste logging)
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from vm_core.mcp_tiering import classify_coverage

from ._pool import MCPClientPool

GATEWAY_VERSION = "0.2.0-f5.3"
DEFAULT_BIND_HOST = "127.0.0.1"
DEFAULT_BIND_PORT = 55401

# Sensitive keys mask em mcp_calls.args/response (defense-in-depth — wrappers
# já fazem sanitize per-tool, mas gateway é última camada antes DB persist).
_SENSITIVE_KEYS = frozenset({
    "li_at", "token", "cookie", "cookies", "password", "auth", "authorization",
    "jsessionid", "csrf", "csrf_token", "api_key", "apikey", "secret", "bearer",
    "li_rm", "lidc", "bcookie", "bscookie", "x-li-track", "x_li_track",
    "liap", "usermatchhistory", "analyticssynchistory",
})


def _sanitize(value: Any) -> Any:
    """Mask sensitive keys recursive (preserves structure)."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if str(k).strip().lower() in _SENSITIVE_KEYS:
                out[k] = "[REDACTED]"
            else:
                out[k] = _sanitize(v)
        return out
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _truncate_json(value: Any, max_bytes: int = 10000) -> Optional[str]:
    """Serialize + truncate pra evitar payloads gigantes em mcp_calls DB."""
    if value is None:
        return None
    try:
        s = json.dumps(_sanitize(value), default=str, ensure_ascii=False)
    except Exception:
        s = str(value)
    if len(s.encode("utf-8")) > max_bytes:
        return s[:max_bytes] + "...[TRUNCATED]"
    return s


def _resolve_db_path() -> Path:
    """Locate mcp_calls SQLite DB.

    VM: ~/.hermes/data/command_center.db (master).
    Dev/PC: hermes_local.db at repo root.
    Override: HERMES_MCP_CALLS_DB env var.
    """
    override = os.getenv("HERMES_MCP_CALLS_DB")
    if override:
        return Path(override)
    vm_db = Path.home() / ".hermes" / "data" / "command_center.db"
    if vm_db.exists():
        return vm_db
    # Fallback: repo root hermes_local.db (dev)
    repo_root = Path(__file__).resolve().parent.parent.parent
    return repo_root / "hermes_local.db"

logger = logging.getLogger("hermes.gateway")
if not logger.handlers:
    logging.basicConfig(
        level=os.getenv("HERMES_GATEWAY_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s [gateway] %(message)s",
    )


def _load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load gateway config.yaml from disk."""
    path = config_path or Path(__file__).parent / "config.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Gateway config not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    return cfg


def _is_loopback(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    return host in ("127.0.0.1", "::1", "localhost")


def build_app(config_path: Path | None = None) -> FastAPI:
    cfg = _load_config(config_path)
    gw_cfg = cfg.get("gateway", {})
    upstream = cfg.get("upstream_mcps", []) or []
    public_planned = cfg.get("public_mcps_planned", []) or []

    oauth_enabled = bool(gw_cfg.get("oauth_enabled", True))
    oauth_bypass_loopback = bool(gw_cfg.get("oauth_bypass_loopback", True))
    strict_mode = os.getenv("HERMES_STRICT_MCP") == "1"
    audit_path_raw = gw_cfg.get("audit_log_path", "~/.hermes/logs/gateway_audit.jsonl")
    audit_path = Path(os.path.expanduser(audit_path_raw))

    # F.5.3 — connection pool (TTL + max_idle from config)
    pool_ttl = int(gw_cfg.get("pool_ttl_seconds", 300))
    pool_max_idle = int(gw_cfg.get("pool_max_idle", 10))
    pool = MCPClientPool(ttl_seconds=pool_ttl, max_idle=pool_max_idle)
    db_path = _resolve_db_path()
    upstream_by_name = {m.get("name"): m for m in upstream}

    app = FastAPI(
        title="Hermes ContextForge Gateway",
        version=GATEWAY_VERSION,
        docs_url=None,
        redoc_url=None,
    )

    # Store pool no app.state pra shutdown handler acessar
    app.state.pool = pool
    app.state.db_path = db_path

    @app.on_event("shutdown")
    async def _shutdown_close_pool():
        # F.5.3 evita zombie subprocess VM quando uvicorn termina
        try:
            await pool.close_all()
            logger.info("Gateway shutdown: pool closed")
        except Exception as exc:
            logger.warning("Gateway shutdown pool close failed: %s", exc)

    _OAUTH_BYPASS_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})

    @app.middleware("http")
    async def oauth_bearer_check(request: Request, call_next):
        """F.5.3 — OAuth Bearer ESPECÍFICO pra /api/mcp/* coverage endpoints.

        Allowlist bypass STRICT (set literal, NÃO regex amplo).
        /api/mcp/* paths SEMPRE requerem Bearer token (independente de loopback).
        Outros paths passam pra auth_loopback handler abaixo.
        """
        if request.url.path in _OAUTH_BYPASS_PATHS:
            return await call_next(request)
        if not request.url.path.startswith("/api/mcp/"):
            return await call_next(request)
        # /api/mcp/* — Bearer required (NÃO bypass loopback aqui)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"error": "missing_bearer", "path": request.url.path},
            )
        token = auth.removeprefix("Bearer ").strip()
        expected = os.getenv("HERMES_GATEWAY_OAUTH_SECRET", "")
        if not expected or not secrets.compare_digest(token, expected):
            return JSONResponse(
                status_code=401,
                content={"error": "invalid_bearer"},
            )
        return await call_next(request)

    @app.middleware("http")
    async def auth_loopback(request: Request, call_next):
        # /health probe sem auth pra startup gate hermes_api_v2 conseguir consultar.
        if request.url.path == "/health":
            return await call_next(request)
        # /api/mcp/* tratado por oauth_bearer_check acima — skip aqui
        if request.url.path.startswith("/api/mcp/"):
            return await call_next(request)
        if oauth_enabled:
            if oauth_bypass_loopback and _is_loopback(request) and not strict_mode:
                return await call_next(request)
            # Strict mode OR non-loopback: requires Bearer token (F.5.2 implements real verify)
            secret = os.getenv("HERMES_GATEWAY_OAUTH_SECRET", "")
            authz = request.headers.get("Authorization", "")
            if not secret or authz != f"Bearer {secret}":
                return JSONResponse(
                    status_code=401,
                    content={"detail": "OAuth required (F.5.2 will issue per-MCP JWT)"},
                )
        return await call_next(request)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        active = sum(1 for m in upstream if m.get("status") == "active")
        pending = sum(1 for m in upstream if m.get("status") == "pending")
        return {
            "ok": True,
            "version": GATEWAY_VERSION,
            "ts": time.time(),
            "upstream_count": len(upstream),
            "upstream_active": active,
            "upstream_pending": pending,
            "strict_mode": strict_mode,
            "oauth_enabled": oauth_enabled,
        }

    @app.get("/tools")
    async def list_tools() -> dict[str, Any]:
        """List tools registered upstream. F.5.1 returns config.yaml preview.
        F.5.2 replaces with live introspection via fastmcp.Client.list_tools().
        """
        tools = []
        for mcp in upstream:
            name = mcp.get("name", "?")
            kind = mcp.get("kind", "custom")
            status = mcp.get("status", "pending")
            for tool_name in mcp.get("tools_preview", []) or []:
                tools.append({
                    "server": name,
                    "tool": tool_name,
                    "kind": kind,
                    "status": status,
                    "chapter_owner": mcp.get("chapter_owner"),
                    "required_by_dc": mcp.get("required_by_dc", []),
                    "version": "preview",
                    "registered_at": None,
                })
        return {
            "ok": True,
            "tools": tools,
            "count": len(tools),
            "source": "config.yaml preview (F.5.1 scaffold)",
        }

    @app.get("/upstream")
    async def list_upstream() -> dict[str, Any]:
        return {
            "ok": True,
            "upstream_mcps": upstream,
            "public_mcps_planned": public_planned,
        }

    @app.get("/audit-log")
    async def audit_log(limit: int = 100) -> dict[str, Any]:
        if not audit_path.exists():
            return {"ok": True, "entries": [], "note": "audit log not yet populated"}
        try:
            lines = audit_path.read_text(encoding="utf-8").splitlines()[-limit:]
            entries = []
            for line in lines:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
            return {"ok": True, "entries": entries, "count": len(entries)}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"audit-log read failed: {exc}")

    @app.post("/dispatch/{server_name}/{tool_name}")
    async def dispatch_real(
        server_name: str,
        tool_name: str,
        request: Request,
    ) -> dict[str, Any]:
        """F.5.3 dispatch real via fastmcp.Client pool. Logs em mcp_calls (S2)."""
        matched = upstream_by_name.get(server_name)
        if not matched:
            raise HTTPException(status_code=404, detail=f"Unknown server: {server_name}")
        status = matched.get("status", "pending")
        if status != "active":
            raise HTTPException(
                status_code=503,
                detail=f"{server_name}.{tool_name} upstream status={status} (not active)",
            )
        if matched.get("transport", "stdio") != "stdio":
            raise HTTPException(
                status_code=501,
                detail=f"{server_name} transport={matched.get('transport')} not implemented (F.5.6 http/sse)",
            )

        # Parse args body (JSON)
        try:
            body = await request.json()
        except Exception:
            body = {}
        args = body.get("args", {}) if isinstance(body, dict) else {}
        requester = (body.get("requester") if isinstance(body, dict) else None) or "api"

        call_id = str(uuid.uuid4())
        start = time.monotonic()
        response_payload: Any = None
        err_msg: Optional[str] = None
        status_code = 200

        try:
            command = matched.get("command", "python3")
            # Custom MCPs precisam fastmcp instalado. Se config=='python3'/'python',
            # usa sys.executable (mesmo Python do gateway — garante fastmcp disponível
            # quando gateway rodando em venv). Override explícito (path absoluto) preservado.
            if command in ("python", "python3"):
                command = sys.executable
            cmd_args = list(matched.get("args", []) or [])
            cwd = matched.get("cwd")
            client = await pool.acquire(server_name, command, cmd_args, cwd=cwd)
            result = await client.call_tool(tool_name, args)
            # fastmcp 3.x returns CallToolResult; extract content payload
            if hasattr(result, "data"):
                response_payload = result.data
            elif hasattr(result, "content"):
                response_payload = [
                    {"type": getattr(c, "type", "?"), "text": getattr(c, "text", None)}
                    for c in result.content
                ]
            else:
                response_payload = str(result)
            return {
                "ok": True,
                "call_id": call_id,
                "server": server_name,
                "tool": tool_name,
                "response": response_payload,
                "duration_ms": int((time.monotonic() - start) * 1000),
            }
        except HTTPException:
            raise
        except Exception as exc:
            err_msg = str(exc)
            status_code = 500
            logger.exception("dispatch %s.%s failed", server_name, tool_name)
            raise HTTPException(status_code=500, detail=f"dispatch failed: {err_msg}")
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            # S2 fire-and-forget INSERT mcp_calls (DB fail NÃO bloqueia dispatch)
            try:
                _log_mcp_call(
                    db_path,
                    call_id=call_id,
                    server=server_name,
                    tool=tool_name,
                    args=args,
                    response=response_payload if err_msg is None else None,
                    error=err_msg,
                    duration_ms=duration_ms,
                    requester=requester,
                )
            except Exception as log_exc:
                logger.error("mcp_calls log failed: %s", log_exc)

    @app.get("/pool/stats")
    async def pool_stats() -> dict[str, Any]:
        """Pool debugging endpoint (loopback only via auth middleware)."""
        return pool.stats()

    # F.5.3 — MCP coverage endpoints (Bearer required via oauth_bearer_check)
    @app.get("/api/mcp/coverage/latest")
    async def mcp_coverage_latest() -> dict[str, Any]:
        """Live query mcp_calls last 30d + tier classification real-time."""
        return _coverage_latest(db_path)

    @app.post("/api/mcp/coverage/publish")
    async def mcp_coverage_publish() -> JSONResponse:
        """Stub manual trigger F.5.5 audit cron mensal."""
        logger.info("mcp_coverage_publish stub called (F.5.5 entrega cron mensal)")
        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "next_step": "F.5.5 implementa mcp_coverage_audit.py cron mensal dia 15 9h BRT",
                "output_path_template": ".claude/audits/mcp-coverage/MCP-COVERAGE-{YYYY-MM}.md",
            },
        )

    return app


def _coverage_latest(db_path: Path) -> dict[str, Any]:
    """Live query mcp_calls + tier classify. Graceful degrade se migrations ausentes."""
    if not db_path.exists():
        return {
            "period_days": 30,
            "summary": {"total_tools": 0, "active": 0, "warning": 0, "orphan": 0,
                        "deprecated": 0, "quarantine": 0, "reserved": 0},
            "items": [],
            "note": f"DB not found: {db_path}",
        }
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        existing = {
            r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "mcp_calls" not in existing or "mcp_registry" not in existing:
            return {
                "period_days": 30,
                "summary": {"total_tools": 0, "active": 0, "warning": 0, "orphan": 0,
                            "deprecated": 0, "quarantine": 0, "reserved": 0},
                "items": [],
                "note": "mcp_registry/mcp_calls table missing — apply F.5.3 migrations",
            }
        call_rows = [dict(r) for r in conn.execute("""
            SELECT server, tool, COUNT(*) as calls,
                   ROUND(AVG(duration_ms), 1) as avg_ms,
                   MAX(created_at) as last_call,
                   SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as errors
            FROM mcp_calls
            WHERE created_at > datetime('now', '-30 days')
            GROUP BY server, tool
            ORDER BY calls DESC
        """).fetchall()]
        registry_rows = [dict(r) for r in conn.execute(
            "SELECT server, tools, tier, chapter_owner FROM mcp_registry"
        ).fetchall()]
        classification = classify_coverage(call_rows, registry_rows)
        return {"period_days": 30, **classification}
    finally:
        conn.close()


def _log_mcp_call(
    db_path: Path,
    *,
    call_id: str,
    server: str,
    tool: str,
    args: Any,
    response: Any,
    error: Optional[str],
    duration_ms: int,
    requester: str,
) -> None:
    """Fire-and-forget INSERT em mcp_calls. Sanitized + truncated 10KB."""
    if not db_path.exists():
        # Skip silent se DB ausente — gateway pode subir antes server.py applicar migration
        return
    args_str = _truncate_json(args)
    response_str = _truncate_json(response)
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    try:
        conn.execute(
            """INSERT INTO mcp_calls (id, server, tool, args, response, error, duration_ms, requester)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (call_id, server, tool, args_str, response_str, error, duration_ms, requester),
        )
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    import uvicorn

    cfg = _load_config()
    gw_cfg = cfg.get("gateway", {})
    host = gw_cfg.get("bind_host", DEFAULT_BIND_HOST)
    port = int(gw_cfg.get("bind_port", DEFAULT_BIND_PORT))

    if host not in ("127.0.0.1", "::1", "localhost"):
        logger.warning(
            "Gateway bind_host=%s is NOT loopback — F.5.1 spec requires loopback-only. Continuing anyway.",
            host,
        )

    app = build_app()
    logger.info("Starting Hermes ContextForge Gateway v%s on %s:%d", GATEWAY_VERSION, host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
