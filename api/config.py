"""F.4.3 — Runtime config endpoint exposing whitelisted ENV flags.

Cross-ref: .claude/PLAN.md § "F.4.3 Decisões Cristalizadas" D3 (PATH 1 WS flag).

Only feature flags explicitly whitelisted below are exposed. NEVER expose
secrets, API tokens, or arbitrary env vars — supply-chain safety.
"""
from __future__ import annotations

import os
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["config"])


_WHITELIST_FLAGS = {
    # F.4.3 D3 — PATH 1 experimental WS listener for Tauri / F.4.6.
    "HERMES_F43_WS_LISTENER",
}


def _read_flag(name: str) -> bool:
    raw = os.environ.get(name, "")
    return raw == "1" or raw.lower() in ("true", "yes", "on")


@router.get("/config")
async def get_runtime_config() -> dict[str, bool]:
    """Whitelisted feature flags only. Read at call-time (no caching).

    Returns:
        {flag_name: bool} dict — bool reflects ENV truthiness.
    """
    return {flag: _read_flag(flag) for flag in _WHITELIST_FLAGS}
