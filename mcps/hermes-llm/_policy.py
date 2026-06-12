"""hermes-llm routing policy + RpmLimiter + FALLBACK_TRIGGERS — F.5.7.

Ground truth: .claude/NVIDIA-MODELS-ROUTING-MATRIX.md §4 + §5.

Decide routing chain per task_type + policy. NÃO faz I/O — pure decision.
FALLBACK_TRIGGERS: per-call failure → next tier.
RpmLimiter: sliding window 60s, margin 38/40 NIM Free cap.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(__file__).parent / "config.yaml"

_CONFIG_CACHE: dict[str, Any] | None = None


def load_routing_config(force_reload: bool = False) -> dict[str, Any]:
    """Lê config.yaml (cached). Reload se force_reload=True."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None and not force_reload:
        return _CONFIG_CACHE
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        _CONFIG_CACHE = yaml.safe_load(fh) or {}
    return _CONFIG_CACHE


class RpmLimiter:
    """Sliding window 60s. NIM Free hard cap 40 RPM, margin 38."""

    def __init__(self, max_rpm: int = 38, window_seconds: int = 60):
        self.max_rpm = max_rpm
        self.window_seconds = window_seconds
        self.calls: list[float] = []

    def can_proceed(self) -> bool:
        now = time.monotonic()
        self.calls = [t for t in self.calls if now - t < self.window_seconds]
        if len(self.calls) < self.max_rpm:
            self.calls.append(now)
            return True
        return False

    def remaining(self) -> int:
        now = time.monotonic()
        active = [t for t in self.calls if now - t < self.window_seconds]
        return max(0, self.max_rpm - len(active))


def _is_429(r: dict) -> bool:
    return not r.get("ok") and r.get("status_code") == 429


def _is_5xx(r: dict) -> bool:
    code = r.get("status_code") or 0
    return not r.get("ok") and 500 <= code < 600


def _is_timeout(r: dict) -> bool:
    return not r.get("ok") and r.get("error") == "timeout"


def _is_auth_fail(r: dict) -> bool:
    return not r.get("ok") and r.get("status_code") in (401, 403)


def _is_empty(r: dict) -> bool:
    if not r.get("ok"):
        return False
    resp = r.get("response") or ""
    return len(str(resp)) < 10


def _is_model_unavailable(r: dict) -> bool:
    if r.get("ok"):
        return False
    err = str(r.get("error") or "").lower()
    return "model_not_found" in err or "model not found" in err or "no such model" in err


FALLBACK_TRIGGERS = {
    "rate_limit": _is_429,
    "server_error": _is_5xx,
    "timeout": _is_timeout,
    "auth_fail": _is_auth_fail,
    "empty_response": _is_empty,
    "model_unavailable": _is_model_unavailable,
}


def _is_client_error(r: dict) -> bool:
    return not r.get("ok") and r.get("status_code") == 400


ABORT_TRIGGERS_NO_FALLBACK = {
    "client_error": _is_client_error,
}


def should_fallback(response: dict) -> tuple[bool, str | None]:
    """Returns (fallback_required, trigger_name). Aborts wins over fallback."""
    for name, fn in ABORT_TRIGGERS_NO_FALLBACK.items():
        if fn(response):
            return False, name
    for name, fn in FALLBACK_TRIGGERS.items():
        if fn(response):
            return True, name
    return False, None


def route_decide(
    task_type: str,
    policy: str = "balanced",
    force_provider: str = "",
) -> list[tuple[str, str, str]]:
    """Returns ordered list of (tier, provider, model) tuples for fallback chain.

    Policy filters apply:
      cost-optimize: deny nim_credit + openrouter
      latency-optimize: allow only nim_free + ollama_pc
      balanced: deny openrouter (T4 explicit force only)

    force_provider != "": single tier no fallback (owner explicit override).
    """
    config = load_routing_config()

    if force_provider:
        model = config.get("forced_models", {}).get(force_provider, "")
        return [("T1", force_provider, model)]

    matrix = config.get("routing_matrix", {})
    chain = matrix.get(task_type) or matrix.get("default") or []

    policy_cfg = config.get("policies", {}).get(policy, {})
    deny = set(policy_cfg.get("deny_providers", []))
    allow = set(policy_cfg.get("allow_providers", []))

    filtered = []
    for entry in chain:
        provider = entry.get("provider", "")
        if deny and provider in deny:
            continue
        if allow and provider not in allow:
            continue
        filtered.append((entry.get("tier", ""), provider, entry.get("model", "")))

    if not filtered:
        for entry in chain:
            filtered.append((entry.get("tier", ""), entry.get("provider", ""), entry.get("model", "")))

    return filtered


VALID_TASK_TYPES = frozenset({
    "default", "reasoning", "classify", "code_gen", "code_gen_light",
    "creative_ptbr", "summarize", "embedding", "generic_light",
})

VALID_POLICIES = frozenset({"balanced", "cost-optimize", "latency-optimize"})

VALID_PROVIDERS = frozenset({"nim_free", "nim_credit", "ollama_pc", "openrouter"})
