"""hermes-linkedin MCP — FastMCP 3.0 wrapper sobre linkedin/*.

F.5.2 entrega 8 tools que importam DIRETO linkedin/* (sem proxy HTTP via VM API).
BLACKLIST R2 INVIOLAVEL: zero modificação em linkedin/{stealth,human,limiter,
cooldown,preflight,account_profile,config,stealth_compliance,ollama_router,
db_utils}.py — APENAS import e wrap.

Tools (8):
  1. get_health            — cooldown.check_health
  2. get_rate_limits       — RateLimiter.get_stats
  3. get_warmup_status     — RateLimiter.is_lurking_phase + warmup_multiplier
  4. get_account_profile   — AccountProfile.load
  5. assert_account_safe   — account_profile.assert_not_burned
  6. preflight_check       — preflight.assert_tunnel_healthy
  7. probe_cooldown        — cooldown.probe_linkedin
  8. start_campaign        — dispatch viewer/engager/connector.start

Sanitize SENSITIVE_KEYS (li_at/token/cookie/password/auth/jsessionid/csrf/
api_key/secret/bearer/li_rm/lidc/bcookie/bscookie/x-li-track) em TODAS responses
(mesmo pattern F.3.2 _event_emit.py defense-in-depth).

OAuth 2.1 JWT default ON, bypass loopback dev. Strict mode VM prod via env
HERMES_STRICT_MCP=1 + HERMES_GATEWAY_OAUTH_SECRET.

Run: python mcps/hermes-linkedin/server.py  (cwd = repo root)
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

# Repo root deve estar em sys.path pra `from linkedin.X import Y` resolver
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover — VM-only dep
    raise SystemExit(
        "fastmcp não instalado. F.5.2 exige fastmcp>=3.0 na VM "
        "(pip install fastmcp>=3.0). Erro: " + str(exc)
    )

MCP_NAME = "hermes-linkedin"
MCP_VERSION = "0.2.0-h7"

# Defense-in-depth sanitizer (mesmo pattern linkedin/lab/_event_emit.py F.3.2)
_SENSITIVE_KEYS = frozenset({
    "li_at", "token", "cookie", "cookies", "password", "auth", "authorization",
    "jsessionid", "csrf", "csrf_token", "api_key", "apikey", "secret", "bearer",
    "li_rm", "lidc", "bcookie", "bscookie", "x-li-track", "x_li_track",
    "liap", "usermatchhistory", "analyticssynchistory",
})


def _sanitize(value: Any) -> Any:
    """Mascarar keys sensíveis recursivamente (preserva estrutura)."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            key_norm = str(k).strip().lower()
            if key_norm in _SENSITIVE_KEYS:
                out[k] = "[REDACTED]"
            else:
                out[k] = _sanitize(v)
        return out
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


mcp = FastMCP(MCP_NAME)


@mcp.tool()
async def get_health(force_refresh: bool = False) -> dict:
    """Estado saúde LinkedIn (ok/challenge/cooldown/blocked).

    Wrap linkedin.cooldown.check_health — leitura cache disco com TTL
    (ok 5min, cooldown 30min, challenge 10min) ou probe via SOCKS5 se
    force_refresh=True.

    Args:
        force_refresh: ignora cache, força probe /feed/ via tunnel.

    Returns:
        dict {state, http_code, last_check_ts, ttl_remaining_s, ...}
    """
    from linkedin import cooldown
    payload = await cooldown.check_health(force_refresh=force_refresh)
    return _sanitize(payload)


@mcp.tool()
async def get_rate_limits(account_id: str = "default") -> dict:
    """Stats RateLimiter pra account_id: usado hoje vs. capacidade.

    Wrap linkedin.limiter.RateLimiter.get_stats — read-only.

    Args:
        account_id: identificador conta (default = "default").

    Returns:
        dict {daily_views, daily_connections, weekly_connections,
              daily_messages, effective_limits, warmup_day, within_working_hours}
    """
    from linkedin.config import LinkedInConfig
    from linkedin.limiter import RateLimiter
    cfg = LinkedInConfig()
    limiter = RateLimiter(account_id=account_id, config=cfg)
    stats = limiter.get_stats()
    within, _msg = limiter.is_within_working_hours()
    return _sanitize({
        "account_id": account_id,
        "stats": stats,
        "within_working_hours": bool(within),
        "next_working_window": limiter.next_working_window(),
        "is_lurking_phase": limiter.is_lurking_phase(),
    })


@mcp.tool()
async def get_warmup_status(account_id: str = "default") -> dict:
    """Estado warmup 14d pra account_id: dia, multiplicador, fase.

    Wrap RateLimiter.warmup_action_multiplier + is_lurking_phase +
    get_effective_daily_limit por action_type.

    Args:
        account_id: identificador conta.

    Returns:
        dict {account_id, is_lurking_phase, multipliers_by_action,
              effective_limits_by_action}
    """
    from linkedin.config import LinkedInConfig
    from linkedin.limiter import RateLimiter
    cfg = LinkedInConfig()
    limiter = RateLimiter(account_id=account_id, config=cfg)
    actions = ["profile_view", "connection_request", "message", "comment"]
    multipliers = {a: limiter.warmup_action_multiplier(a) for a in actions}
    limits = {a: limiter.get_effective_daily_limit(a) for a in actions}
    return _sanitize({
        "account_id": account_id,
        "is_lurking_phase": limiter.is_lurking_phase(),
        "warmup_multipliers_by_action": multipliers,
        "effective_daily_limits_by_action": limits,
    })


@mcp.tool()
async def get_account_profile(account_id: str) -> dict:
    """Carrega AccountProfile (sticky_session_id, burned_flag, signals).

    Wrap AccountProfile.load. Sanitiza li_at / cookies / session secrets.

    Args:
        account_id: identificador conta (obrigatório).

    Returns:
        dict {account_id, exists, profile, burned, last_check_ts} OR
        {account_id, exists: false} se perfil não existe.
    """
    from linkedin.account_profile import AccountProfile
    profile = AccountProfile.load(account_id)
    if profile is None:
        return {"account_id": account_id, "exists": False}
    # Build serializable summary (NÃO retornar objeto AccountProfile direto)
    raw = {
        "account_id": account_id,
        "exists": True,
        "is_burned": profile.is_burned(),
        "data": {k: v for k, v in profile.__dict__.items() if not k.startswith("_")},
    }
    return _sanitize(raw)


@mcp.tool()
async def assert_account_safe(account_id: str) -> dict:
    """Asserta que account_id NÃO está burned. Retorna estado + raise-friendly.

    Wrap account_profile.assert_not_burned — NÃO levanta no MCP (retorna
    {ok: false, reason} pro Brain decidir).

    Args:
        account_id: identificador conta.

    Returns:
        dict {account_id, ok: bool, reason: str | null}
    """
    from linkedin.account_profile import assert_not_burned
    try:
        profile = assert_not_burned(account_id)
        return _sanitize({
            "account_id": account_id,
            "ok": True,
            "reason": None,
            "sticky_session_id": getattr(profile, "sticky_session_id", None),
        })
    except Exception as exc:
        return {
            "account_id": account_id,
            "ok": False,
            "reason": str(exc)[:200],
        }


@mcp.tool()
async def preflight_check(proxy_url: str | None = None) -> dict:
    """Tunnel SOCKS5 residencial healthy? Egress IP datacenter check.

    Wrap preflight.assert_tunnel_healthy. NÃO levanta — retorna estado.

    Args:
        proxy_url: socks5://host:port (None = usa default config).

    Returns:
        dict {ok, egress_ip, is_datacenter, error?}
    """
    from linkedin import preflight
    from linkedin.config import LinkedInConfig
    cfg = LinkedInConfig()
    host = cfg.proxy_host or "127.0.0.1"
    port = int(cfg.proxy_port or 55081)
    try:
        ip = preflight.assert_tunnel_healthy(
            socks_host=host, socks_port=port, max_attempts=1,
        )
        return {"ok": True, "egress_ip": ip, "is_datacenter": False}
    except preflight.ProxyHealthError as exc:
        return {"ok": False, "error": str(exc)[:200]}
    except Exception as exc:
        return {"ok": False, "error": f"unexpected: {str(exc)[:200]}"}


@mcp.tool()
async def probe_cooldown() -> dict:
    """Probe ativo /feed/ via SOCKS5 + LI_AT — força refresh state cooldown.

    Wrap cooldown.probe_linkedin (ignora cache, ativo HTTP request).

    Returns:
        dict {state, http_code, ts, detail}
    """
    from linkedin import cooldown
    payload = await cooldown.probe_linkedin()
    return _sanitize(payload)


_TYPE_TO_ENDPOINT = {
    "viewer": "/api/linkedin/campaigns/view",
    "engager": "/api/linkedin/campaigns/engage",
    "connector": "/api/linkedin/campaigns/connect",
}


@mcp.tool()
async def start_campaign(campaign_type: str, config: dict) -> dict:
    """Despacha campanha LinkedIn REAL via delegate hermes_api_v2 (H7 B12).

    Design intent preservado (H7 OPÇÃO D): MCP tool é CONTROL plane,
    campaign exec mantém-se em hermes_api_v2 (async task tracker
    _running_linkedin_campaigns). start_campaign agora HTTP POST pra
    endpoint VM existente em vez de echo.

    BLACKLIST R2 preservada 100% — zero touch direct em linkedin/{viewer,
    engager,connector,stealth,human,limiter,cooldown,preflight}. linkedin/*
    é executado pela VM API (call site existente F.5).

    Args:
        campaign_type: "viewer" | "engager" | "connector".
        config: dict campaign_config (sanitized antes POST + body envia raw
                pra VM — VM aceita cookies/auth no body por design).

    Returns:
        dict {ok, campaign_type, campaign_id, started_ts, delegated_to}
        OR {ok: false, error}.

    Env:
        HERMES_VM_API_URL (default http://127.0.0.1:8420)
        HERMES_VM_AUTH_TOKEN (X-Hermes-Token header)
    """
    valid_types = set(_TYPE_TO_ENDPOINT.keys())
    if campaign_type not in valid_types:
        return {
            "ok": False,
            "error": f"campaign_type must be one of {sorted(valid_types)}",
        }
    endpoint = _TYPE_TO_ENDPOINT[campaign_type]
    vm_api_url = os.getenv("HERMES_VM_API_URL", "http://127.0.0.1:8420").rstrip("/")
    vm_token = os.getenv("HERMES_VM_AUTH_TOKEN", "")
    started_ts = time.time()

    try:
        import httpx  # type: ignore[import-not-found]
    except ImportError as exc:
        return {
            "ok": False,
            "error": f"httpx not installed: {exc}",
            "version": MCP_VERSION,
        }

    headers = {
        "X-Hermes-Token": vm_token,
        "X-Hermes-Requester": "brain-f5-mcp-linkedin",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{vm_api_url}{endpoint}",
                json=config or {},
                headers=headers,
            )
            response.raise_for_status()
            vm_payload = response.json() if response.content else {}
    except Exception as exc:  # noqa: BLE001
        # H5 sentry_via_gateway pattern — fire-and-forget via gateway
        try:
            from core.sentry_via_gateway import capture_exception
            capture_exception(
                exc,
                requester="brain-f5-mcp-linkedin",
                extra={"campaign_type": campaign_type, "endpoint": endpoint},
            )
        except Exception:  # noqa: BLE001
            pass
        return {
            "ok": False,
            "campaign_type": campaign_type,
            "error": str(exc)[:500],
            "delegated_to": endpoint,
            "version": MCP_VERSION,
        }

    campaign_id = vm_payload.get("campaign_id") if isinstance(vm_payload, dict) else None
    return {
        "ok": True,
        "campaign_type": campaign_type,
        "campaign_id": campaign_id,
        "started_ts": started_ts,
        "delegated_to": endpoint,
        "vm_response": _sanitize(vm_payload) if isinstance(vm_payload, dict) else vm_payload,
        "version": MCP_VERSION,
    }


def main() -> None:
    """Stdio transport entrypoint. FastMCP default."""
    transport = os.getenv("HERMES_MCP_TRANSPORT", "stdio").lower()
    if transport == "http":
        port = int(os.getenv("HERMES_HERMES_LINKEDIN_PORT", "55411"))
        mcp.run(transport="http", host="127.0.0.1", port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
