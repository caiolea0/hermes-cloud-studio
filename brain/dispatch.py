"""F.6.2 Brain Gateway HTTP client.

Brain consome MCPs SEMPRE via ContextForge gateway dispatch endpoint
(POST /dispatch/{server}/{tool}) — NUNCA chama mcps/* direto.

Bearer auth via HERMES_GATEWAY_OAUTH_SECRET env (F.5.3 pattern).
Default URL via HERMES_GATEWAY_URL env (default http://localhost:55401).

PC dev: requer SSH tunnel forward 55401→55401 OU HERMES_GATEWAY_URL override.
VM prod: gateway loopback nativo (mesmo host hermes_api_v2.py).

Defense-in-depth:
  - SENSITIVE_KEYS sanitize per-log call (gateway-side já sanitize, Brain dupla camada)
  - NIM key NUNCA logged raw (startswith nvapi- → [REDACTED])
  - Timeout HTTP 30s default (D7 cristalizado — routing matrix decide max_latency)

Cross-ref:
  .claude/PLAN.md § F.6.2 Decisões D1-D8 (commit 68f0623)
  mcps/gateway/server.py F.5.3 dispatch_real (POST /dispatch/{srv}/{tool})
  brain/_react.py F.6.2 (consumer ReAct loop)
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

__all__ = ["GatewayDispatcher", "SENSITIVE_KEYS", "sanitize"]

log = logging.getLogger("brain.dispatch")

# Defense-in-depth sanitize (gateway-side ALSO sanitize — duplo gate).
# Inclui LinkedIn cookies, LLM API keys, OAuth bearers, passwords.
SENSITIVE_KEYS: frozenset[str] = frozenset({
    "li_at", "jsessionid", "cookie", "cookies", "csrf", "csrf_token",
    "li_rm", "lidc", "bcookie", "bscookie", "x-li-track", "x_li_track",
    "liap", "usermatchhistory",
    # LLM provider keys (F.5.7 + F.6.2)
    "nvidia_api_key", "nvapi", "nim_token", "hermes_nim_api_key",
    "openrouter_api_key", "anthropic_api_key", "openai_api_key",
    # Generic
    "api_key", "apikey", "secret", "bearer", "authorization",
    "password", "token", "auth",
})


def sanitize(value: Any) -> Any:
    """Recursive sanitize SENSITIVE_KEYS pra log/response. Preserves structure."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            key_lower = str(k).strip().lower()
            redacted = any(sk in key_lower for sk in SENSITIVE_KEYS)
            out[k] = "[REDACTED]" if redacted else sanitize(v)
        return out
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str) and value.startswith("nvapi-"):
        return "[REDACTED]"
    return value


class GatewayDispatcher:
    """HTTP client dispatch via ContextForge gateway.

    F.6.2 Brain consumer — substitui mocks F.6.1.

    Usage:
        d = GatewayDispatcher()
        result = await d.route(task_type="reasoning", prompt="2+2?")
        # OR
        result = await d.invoke_tool("hermes-llm", "route", {"task_type": "reasoning", "prompt": "..."})
    """

    DEFAULT_URL = "http://localhost:55401"

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 30.0,
        bearer: str | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("HERMES_GATEWAY_URL", self.DEFAULT_URL)).rstrip("/")
        self.timeout = timeout
        self.bearer = bearer if bearer is not None else os.getenv("HERMES_GATEWAY_OAUTH_SECRET", "")
        # NOTA: STRICT_MODE=0 gateway aceita sem Bearer (loopback bypass).
        # STRICT_MODE=1 prod exige Bearer válido — F.future quando JWT issuance ativo.

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.bearer:
            h["Authorization"] = f"Bearer {self.bearer}"
        return h

    async def route(
        self,
        task_type: str,
        prompt: str,
        model_hint: str = "",
        max_latency_ms: int = 30000,
        max_cost_credits: int = 0,
        force_provider: str = "",
    ) -> dict[str, Any]:
        """Dispatch via mcp.hermes-llm.route — routing matrix decide T1/T2/T3 fallback.

        Returns gateway response dict:
            {ok, call_id, server, tool, response: {provider, model, tier, response, ...}, duration_ms}
        OR error:
            {ok: False, error, status_code?}
        """
        return await self.invoke_tool(
            server="hermes-llm",
            tool="route",
            args={
                "prompt": prompt,
                "task_type": task_type,
                "model_hint": model_hint,
                "max_latency_ms": max_latency_ms,
                "max_cost_credits": max_cost_credits,
                "force_provider": force_provider,
            },
        )

    async def invoke_tool(self, server: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """Generic gateway dispatch: POST /dispatch/{server}/{tool}.

        Returns:
            On success: {ok: True, call_id, server, tool, response, duration_ms}
            On error:   {ok: False, error, status_code?}
        """
        url = f"{self.base_url}/dispatch/{server}/{tool}"
        payload = {"args": args, "requester": "brain"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, headers=self._headers(), json=payload)
        except httpx.TimeoutException:
            log.warning("dispatch %s.%s timeout (%.1fs)", server, tool, self.timeout)
            return {"ok": False, "error": "timeout"}
        except httpx.RequestError as exc:
            log.warning("dispatch %s.%s connect_error: %s", server, tool, type(exc).__name__)
            return {"ok": False, "error": f"connect_error:{type(exc).__name__}"}
        except Exception as exc:  # noqa: BLE001 — defensive boundary
            log.exception("dispatch %s.%s unexpected", server, tool)
            return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}

        if resp.status_code == 200:
            try:
                data = resp.json()
            except Exception:  # noqa: BLE001
                return {"ok": False, "error": "invalid_json_response", "status_code": 200}
            elapsed = data.get("duration_ms")
            log.info("dispatch %s.%s ok (%sms)", server, tool, elapsed)
            return data

        # HTTP error (4xx/5xx)
        try:
            detail = resp.json().get("detail", resp.text[:200])
        except Exception:  # noqa: BLE001
            detail = resp.text[:200]
        log.warning("dispatch %s.%s HTTP %d: %s", server, tool, resp.status_code, detail)
        return {
            "ok": False,
            "status_code": resp.status_code,
            "error": str(detail)[:500],
        }
