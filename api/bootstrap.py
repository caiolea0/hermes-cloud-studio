"""Hermes Cloud Studio — Bootstrap tokens (loopback-only, no X-Hermes-Token) — MERGED-011.

Retorna tokens locais pra clientes loopback (Tauri webview, extension Chrome).
NUNCA exposto via Cloudflare tunnel (bind 127.0.0.1 + check client.host).
Risco mitigado: clientes locais JA tem acesso ao .env diretamente (mesmo host).
Bootstrap so expoe pra quem ja conseguiria ler .env. Sem novo vetor de ataque.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from config import settings
from core.state import AUTH_TOKEN, INTERNAL_TOKEN

router = APIRouter()


@router.get("/api/_bootstrap")
async def bootstrap_tokens(request: Request):
    """Retorna tokens locais pra clientes loopback. NUNCA exposto remotamente."""
    if request.client.host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(403, "loopback only")
    port_now = settings.dashboard_port
    try:
        from scripts.port_allocator import _load_global_registry, _key
        _reg = _load_global_registry()
        _entry = _reg.get("allocations", {}).get(_key("dashboard"))
        if _entry:
            port_now = _entry.get("port", port_now)
    except Exception:  # noqa: silenciado intencional — fallback seguro
        pass
    return {
        "auth_token": AUTH_TOKEN,
        "internal_token": INTERNAL_TOKEN,
        "dashboard_port": port_now,
        "project": "hermes-cloud-studio",
    }
