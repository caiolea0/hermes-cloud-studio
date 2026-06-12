"""hermes-llm provider adapters — F.5.7.

3 clients OpenAI-compat (NIM + Ollama PC + OpenRouter). T4 OpenRouter
existe pra force_provider explicit owner override only — coexiste com
existing skills/*.yaml openrouter config (zero refactor).

Errors capturados — NUNCA propaga raise pra caller (defesa-em-profundidade
F.5.2 D7 pattern). Retorna {ok, error, status_code, elapsed_ms}.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any

_SELF_DIR = Path(__file__).resolve().parent
if str(_SELF_DIR) not in sys.path:
    sys.path.insert(0, str(_SELF_DIR))

from _policy import load_routing_config  # type: ignore  # noqa: E402


def _safe_import_openai():
    try:
        from openai import AsyncOpenAI
        return AsyncOpenAI
    except ImportError:
        return None


class _BaseClient:
    name = "base"

    async def chat(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
        max_tokens: int = 2048,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def health(self, timeout: float = 2.0) -> dict[str, Any]:
        raise NotImplementedError


class NIMClient(_BaseClient):
    """T1 + T2: NVIDIA NIM cloud OpenAI-compatible."""

    name = "nim"

    def __init__(self):
        config = load_routing_config()
        endpoints = config.get("provider_endpoints", {}).get("nim", {})
        self.base_url = endpoints.get("base_url", "https://integrate.api.nvidia.com/v1")
        self.api_key_env = endpoints.get("api_key_env", "HERMES_NIM_API_KEY")
        self.api_key = os.getenv(self.api_key_env, "")
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        AsyncOpenAI = _safe_import_openai()
        if AsyncOpenAI is None:
            return None
        if not self.api_key:
            return None
        try:
            self._client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)
        except Exception:
            self._client = None
        return self._client

    async def chat(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
        max_tokens: int = 2048,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        t0 = time.monotonic()
        client = self._ensure_client()
        if client is None:
            return {
                "ok": False,
                "error": f"NIM client unavailable (key {self.api_key_env} missing OR openai SDK absent)",
                "status_code": 503,
                "elapsed_ms": 0,
            }
        kwargs: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        try:
            resp = await asyncio.wait_for(client.chat.completions.create(**kwargs), timeout=timeout)
            elapsed = int((time.monotonic() - t0) * 1000)
            usage = getattr(resp, "usage", None)
            return {
                "ok": True,
                "response": resp.choices[0].message.content or "",
                "tool_calls": getattr(resp.choices[0].message, "tool_calls", None),
                "tokens_in": getattr(usage, "prompt_tokens", 0) if usage else 0,
                "tokens_out": getattr(usage, "completion_tokens", 0) if usage else 0,
                "cost_credits": 0.0,
                "elapsed_ms": elapsed,
            }
        except asyncio.TimeoutError:
            return {"ok": False, "error": "timeout", "status_code": None, "elapsed_ms": int(timeout * 1000)}
        except Exception as e:
            return {
                "ok": False,
                "error": str(e)[:300],
                "status_code": getattr(e, "status_code", None),
                "elapsed_ms": int((time.monotonic() - t0) * 1000),
            }

    async def health(self, timeout: float = 2.0) -> dict[str, Any]:
        t0 = time.monotonic()
        client = self._ensure_client()
        if client is None:
            return {"up": False, "error": f"NIM key {self.api_key_env} missing OR SDK absent", "latency_ms": 0}
        try:
            await asyncio.wait_for(client.models.list(), timeout=timeout)
            return {"up": True, "latency_ms": int((time.monotonic() - t0) * 1000)}
        except Exception as e:
            return {"up": False, "error": str(e)[:200], "latency_ms": int((time.monotonic() - t0) * 1000)}


class OllamaPCClient(_BaseClient):
    """T3 fallback: Ollama PC local RTX 2060 6GB (até VM GPU F.future).

    F.5.7 caveat: VM GCP → PC residencial route requires SSH reverse tunnel
    OR Cloudflare Tunnel (documentado gap, NÃO bloqueia F.5.7). PC-side
    smoke testable (Ollama :11434 local).
    """

    name = "ollama_pc"

    def __init__(self):
        config = load_routing_config()
        endpoints = config.get("provider_endpoints", {}).get("ollama_pc", {})
        url_env = endpoints.get("base_url_env", "HERMES_OLLAMA_PC_URL")
        url_default = endpoints.get("base_url_default", "http://localhost:11434/v1")
        self.base_url = os.getenv(url_env, url_default)
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        AsyncOpenAI = _safe_import_openai()
        if AsyncOpenAI is None:
            return None
        try:
            self._client = AsyncOpenAI(base_url=self.base_url, api_key="ollama")
        except Exception:
            self._client = None
        return self._client

    async def chat(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
        max_tokens: int = 2048,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        t0 = time.monotonic()
        client = self._ensure_client()
        if client is None:
            return {"ok": False, "error": "openai SDK absent", "status_code": 503, "elapsed_ms": 0}
        kwargs: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        try:
            resp = await asyncio.wait_for(client.chat.completions.create(**kwargs), timeout=timeout)
            usage = getattr(resp, "usage", None)
            return {
                "ok": True,
                "response": resp.choices[0].message.content or "",
                "tokens_in": getattr(usage, "prompt_tokens", 0) if usage else 0,
                "tokens_out": getattr(usage, "completion_tokens", 0) if usage else 0,
                "cost_credits": 0.0,
                "elapsed_ms": int((time.monotonic() - t0) * 1000),
            }
        except asyncio.TimeoutError:
            return {"ok": False, "error": "timeout", "status_code": None, "elapsed_ms": int(timeout * 1000)}
        except Exception as e:
            return {
                "ok": False,
                "error": str(e)[:300],
                "status_code": getattr(e, "status_code", None),
                "elapsed_ms": int((time.monotonic() - t0) * 1000),
            }

    async def health(self, timeout: float = 2.0) -> dict[str, Any]:
        t0 = time.monotonic()
        client = self._ensure_client()
        if client is None:
            return {"up": False, "error": "openai SDK absent", "latency_ms": 0}
        try:
            await asyncio.wait_for(client.models.list(), timeout=timeout)
            return {"up": True, "latency_ms": int((time.monotonic() - t0) * 1000)}
        except Exception as e:
            return {"up": False, "error": str(e)[:200], "latency_ms": int((time.monotonic() - t0) * 1000)}


class OpenRouterClient(_BaseClient):
    """T4 último recurso: explicit force_provider="openrouter" only.

    Coexiste com existing skills/*.yaml openrouter config. Zero refactor.
    """

    name = "openrouter"

    def __init__(self):
        config = load_routing_config()
        endpoints = config.get("provider_endpoints", {}).get("openrouter", {})
        self.base_url = endpoints.get("base_url", "https://openrouter.ai/api/v1")
        self.api_key_env = endpoints.get("api_key_env", "OPENROUTER_API_KEY")
        self.api_key = os.getenv(self.api_key_env, "")
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        AsyncOpenAI = _safe_import_openai()
        if AsyncOpenAI is None or not self.api_key:
            return None
        try:
            self._client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)
        except Exception:
            self._client = None
        return self._client

    async def chat(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
        max_tokens: int = 2048,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        t0 = time.monotonic()
        client = self._ensure_client()
        if client is None:
            return {
                "ok": False,
                "error": f"OpenRouter client unavailable (key {self.api_key_env} missing OR SDK absent)",
                "status_code": 503,
                "elapsed_ms": 0,
            }
        kwargs: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        try:
            resp = await asyncio.wait_for(client.chat.completions.create(**kwargs), timeout=timeout)
            usage = getattr(resp, "usage", None)
            return {
                "ok": True,
                "response": resp.choices[0].message.content or "",
                "tokens_in": getattr(usage, "prompt_tokens", 0) if usage else 0,
                "tokens_out": getattr(usage, "completion_tokens", 0) if usage else 0,
                "cost_credits": 0.0,
                "elapsed_ms": int((time.monotonic() - t0) * 1000),
            }
        except asyncio.TimeoutError:
            return {"ok": False, "error": "timeout", "status_code": None, "elapsed_ms": int(timeout * 1000)}
        except Exception as e:
            return {
                "ok": False,
                "error": str(e)[:300],
                "status_code": getattr(e, "status_code", None),
                "elapsed_ms": int((time.monotonic() - t0) * 1000),
            }

    async def health(self, timeout: float = 2.0) -> dict[str, Any]:
        t0 = time.monotonic()
        client = self._ensure_client()
        if client is None:
            return {"up": False, "error": f"OpenRouter key {self.api_key_env} missing OR SDK absent", "latency_ms": 0}
        try:
            await asyncio.wait_for(client.models.list(), timeout=timeout)
            return {"up": True, "latency_ms": int((time.monotonic() - t0) * 1000)}
        except Exception as e:
            return {"up": False, "error": str(e)[:200], "latency_ms": int((time.monotonic() - t0) * 1000)}


def get_client(provider: str) -> _BaseClient | None:
    if provider in ("nim_free", "nim_credit", "nim"):
        return NIMClient()
    if provider == "ollama_pc":
        return OllamaPCClient()
    if provider == "openrouter":
        return OpenRouterClient()
    return None
