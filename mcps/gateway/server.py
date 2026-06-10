"""Hermes ContextForge Gateway — FastMCP 3.0 multiplex layer.

F.5.1 scaffold deliverable:
- HTTP server bind loopback 127.0.0.1:55401 (VM-only, never public)
- /health endpoint (consumed by hermes_api_v2 STRICT_MODE startup gate)
- /tools endpoint (consumed by F.8 observability + F.9 pipeline studio)
- /audit-log endpoint (read-only audit trail)
- Config loaded from config.yaml — upstream MCPs as `status: pending` placeholders
- OAuth 2.1 bypass loopback (dev mode), enforced when HERMES_STRICT_MCP=1

F.5.2 entrega real custom MCPs + tools dispatch via fastmcp.
F.5.3 entrega mcp_registry table seed.
F.5.4 entrega validate_implementation.py phase F.

NOT IMPLEMENTED in F.5.1 (by design):
- Actual upstream MCP dispatch (placeholders return 503)
- mcp_calls audit DB writes (F.6 entrega via ToolRegistry.invoke middleware)
- OAuth 2.1 token issuance (F.5.2 entrega when first custom MCP needs it)
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

GATEWAY_VERSION = "0.1.0-f5.1"
DEFAULT_BIND_HOST = "127.0.0.1"
DEFAULT_BIND_PORT = 55401

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

    app = FastAPI(
        title="Hermes ContextForge Gateway",
        version=GATEWAY_VERSION,
        docs_url=None,
        redoc_url=None,
    )

    @app.middleware("http")
    async def auth_loopback(request: Request, call_next):
        # /health probe sem auth pra startup gate hermes_api_v2 conseguir consultar.
        if request.url.path == "/health":
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
    async def dispatch_placeholder(server_name: str, tool_name: str) -> dict[str, Any]:
        """F.5.1 returns 503 — actual dispatch lands in F.5.2 via fastmcp.Client."""
        matched = next((m for m in upstream if m.get("name") == server_name), None)
        if not matched:
            raise HTTPException(status_code=404, detail=f"Unknown server: {server_name}")
        raise HTTPException(
            status_code=503,
            detail=f"{server_name}.{tool_name} not yet wired (status={matched.get('status')}). F.5.2 entrega.",
        )

    return app


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
