"""R5 PHASE 1 -- Per-role bearer to requester resolution.

Extracted from server.py dispatch_real for standalone testability
(no relative imports, no fastmcp dependency).
"""
from __future__ import annotations

import logging
import os
import secrets
from typing import Any, Optional

logger = logging.getLogger("hermes.gateway")

# Per-role env vars -> requester identifier mapping
_ENV_TO_REQUESTER: dict[str, str] = {
    "HERMES_GATEWAY_BEARER_BRAIN": "brain",
    "HERMES_GATEWAY_BEARER_BRAIN_CORE": "brain-core",
    "HERMES_GATEWAY_BEARER_BRAIN_F4": "brain-f4",
    "HERMES_GATEWAY_BEARER_BRAIN_F5": "brain-f5",
    "HERMES_GATEWAY_BEARER_BRAIN_F5_MCP_LINKEDIN": "brain-f5-mcp-linkedin",
    "HERMES_GATEWAY_BEARER_BRAIN_F6": "brain-f6",
    "HERMES_GATEWAY_BEARER_BRAIN_F7_COBAIA": "brain-f7-cobaia",
    "HERMES_GATEWAY_BEARER_BRAIN_F7_COBAIA_AUTOTUNE": "brain-f7-cobaia-autotune",
    "HERMES_GATEWAY_BEARER_BRAIN_F8": "brain-f8",
    "HERMES_GATEWAY_BEARER_BRAIN_F9": "brain-f9",
    "HERMES_GATEWAY_BEARER_BREADCRUMB": "breadcrumb",
    "HERMES_GATEWAY_BEARER_API": "api",
}


def build_bearer_to_requester_map() -> dict[str, str]:
    """Build per-role bearer -> requester map from env at startup."""
    mapping: dict[str, str] = {}
    for env_var, requester in _ENV_TO_REQUESTER.items():
        bearer = os.getenv(env_var)
        if bearer:
            mapping[bearer] = requester
    return mapping


def derive_requester(
    authorization_header: str,
    request_body: Any,
    per_role_map: dict[str, str],
    shared_bearer: str,
    strict_bearer: bool = False,
) -> tuple[Optional[str], str]:
    """Derive (requester, trust_mode) from Authorization header.

    trust_mode:
      'trusted'            -- per-role bearer matched; requester is server-authoritative.
      'fallback_spoofable' -- shared bearer; requester from body (client-claimed, R5_FALLBACK).
      'denied'             -- invalid or missing bearer.
      'denied_strict'      -- shared bearer presented but strict_bearer=True rejects it (R5-PHASE3).

    R5-PHASE3: strict_bearer=True rejects shared bearer with 'denied_strict' instead of
    fallback_spoofable. Controlled by HERMES_GATEWAY_STRICT_BEARER env flag (default False).
    Activate AFTER confirming 7d zero R5_FALLBACK warnings in gateway audit log.
    """
    if not authorization_header.startswith("Bearer "):
        return None, "denied"
    bearer = authorization_header[len("Bearer "):].strip()
    if not bearer:
        return None, "denied"

    if bearer in per_role_map:
        return per_role_map[bearer], "trusted"

    if shared_bearer and secrets.compare_digest(bearer, shared_bearer):
        if strict_bearer:
            # R5-PHASE3 kill switch: shared bearer no longer accepted
            return None, "denied_strict"
        requester_claimed = (
            request_body.get("requester")
            if isinstance(request_body, dict)
            else None
        ) or "api"
        return requester_claimed, "fallback_spoofable"

    return None, "denied"
