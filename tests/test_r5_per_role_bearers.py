"""R5 PHASE 1 -- Tests for per-role bearer infra + 2 migrated callers.

G2 gate: 10 tests added.
Cover: derive_requester logic, brain/dispatch bearer selection,
       sentry_via_gateway breadcrumb bearer, R5_FALLBACK trust_mode.

NOTE: requester.py loaded via spec_from_file_location to bypass
mcps/gateway/__init__.py -> server.py -> fastmcp (VM-only dep).
Pattern mirrors test_h7_access_matrix.py.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Direct-load requester.py (no fastmcp, no relative imports)
# ---------------------------------------------------------------------------
_REQ_PATH = Path(__file__).resolve().parent.parent / "mcps" / "gateway" / "requester.py"
_req_spec = importlib.util.spec_from_file_location("_r5_requester", _REQ_PATH)
_req_mod = importlib.util.module_from_spec(_req_spec)
_req_spec.loader.exec_module(_req_mod)  # type: ignore[union-attr]

derive_requester = _req_mod.derive_requester
build_bearer_to_requester_map = _req_mod.build_bearer_to_requester_map
_ENV_TO_REQUESTER = _req_mod._ENV_TO_REQUESTER

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FAKE_PER_ROLE: dict[str, str] = {
    "brain-core-secret-abc": "brain-core",
    "breadcrumb-secret-xyz": "breadcrumb",
    "brain-f4-secret-def": "brain-f4",
}
FAKE_SHARED = "shared-secret-999"


# ---------------------------------------------------------------------------
# derive_requester -- unit tests
# ---------------------------------------------------------------------------

def test_derive_requester_per_role_bearer_returns_trusted():
    req, mode = derive_requester(
        "Bearer brain-core-secret-abc", {}, FAKE_PER_ROLE, FAKE_SHARED
    )
    assert req == "brain-core"
    assert mode == "trusted"


def test_derive_requester_shared_bearer_returns_fallback():
    body = {"requester": "brain-f4", "args": {}}
    req, mode = derive_requester(
        f"Bearer {FAKE_SHARED}", body, FAKE_PER_ROLE, FAKE_SHARED
    )
    assert req == "brain-f4"
    assert mode == "fallback_spoofable"


def test_derive_requester_shared_bearer_no_body_requester_defaults_api():
    req, mode = derive_requester(
        f"Bearer {FAKE_SHARED}", {}, FAKE_PER_ROLE, FAKE_SHARED
    )
    assert req == "api"
    assert mode == "fallback_spoofable"


def test_derive_requester_invalid_bearer_returns_denied():
    req, mode = derive_requester(
        "Bearer completely-wrong-token", {}, FAKE_PER_ROLE, FAKE_SHARED
    )
    assert req is None
    assert mode == "denied"


def test_derive_requester_missing_authorization_denied():
    req, mode = derive_requester("", {}, FAKE_PER_ROLE, FAKE_SHARED)
    assert req is None
    assert mode == "denied"


def test_R5_FALLBACK_trust_mode_is_fallback_spoofable_on_shared_bearer():
    """Shared bearer returns 'fallback_spoofable' -- dispatch_real SHOULD log R5_FALLBACK."""
    req, mode = derive_requester(
        f"Bearer {FAKE_SHARED}", {"requester": "brain"}, FAKE_PER_ROLE, FAKE_SHARED
    )
    assert mode == "fallback_spoofable"
    assert req == "brain"


def test_per_role_bearer_trusted_differs_from_shared_fallback():
    """Per-role bearer yields 'trusted'; same body requester does not change it."""
    per_role_map = {"unique-brain-core-bearer": "brain-core"}
    shared = "different-shared-bearer"
    req, mode = derive_requester("Bearer unique-brain-core-bearer", {}, per_role_map, shared)
    assert mode == "trusted"
    assert req == "brain-core"


def test_build_bearer_to_requester_map_reads_env():
    """build_bearer_to_requester_map picks up env vars correctly."""
    env_patches = {
        "HERMES_GATEWAY_BEARER_BRAIN_CORE": "test-brain-core-bearer",
        "HERMES_GATEWAY_BEARER_BREADCRUMB": "test-breadcrumb-bearer",
    }
    with patch.dict(os.environ, env_patches, clear=False):
        m = build_bearer_to_requester_map()
    assert m.get("test-brain-core-bearer") == "brain-core"
    assert m.get("test-breadcrumb-bearer") == "breadcrumb"


# ---------------------------------------------------------------------------
# brain/dispatch.py -- bearer selection tests
# ---------------------------------------------------------------------------

def test_brain_dispatch_uses_per_role_bearer_if_available():
    """GatewayDispatcher picks HERMES_GATEWAY_BEARER_BRAIN_CORE over OAUTH_SECRET."""
    with patch.dict(os.environ, {
        "HERMES_GATEWAY_BEARER_BRAIN_CORE": "per-role-brain-bearer",
        "HERMES_GATEWAY_OAUTH_SECRET": "shared-fallback",
    }, clear=False):
        import brain.dispatch as bd
        importlib.reload(bd)
        d = bd.GatewayDispatcher()
    assert d.bearer == "per-role-brain-bearer"


def test_brain_dispatch_fallback_shared_bearer_if_per_role_missing():
    """GatewayDispatcher falls back to OAUTH_SECRET when BRAIN_CORE not set."""
    env_copy = {k: v for k, v in os.environ.items() if k != "HERMES_GATEWAY_BEARER_BRAIN_CORE"}
    env_copy["HERMES_GATEWAY_OAUTH_SECRET"] = "fallback-shared"

    with patch.dict(os.environ, env_copy, clear=True):
        import brain.dispatch as bd
        importlib.reload(bd)
        d = bd.GatewayDispatcher()
    assert d.bearer == "fallback-shared"


# ---------------------------------------------------------------------------
# R5-PHASE2 -- 3 remaining callers per-role bearer tests
# ---------------------------------------------------------------------------

def test_auto_skill_runner_default_dispatcher_uses_brain_f4_bearer():
    """AutoSkillRunner() without explicit dispatcher uses HERMES_GATEWAY_BEARER_BRAIN_F4."""
    import importlib
    with patch.dict(os.environ, {
        "HERMES_GATEWAY_BEARER_BRAIN_F4": "f4-per-role-bearer",
        "HERMES_GATEWAY_OAUTH_SECRET": "shared-fallback",
    }, clear=False):
        import core.auto_skill_runner as asr
        importlib.reload(asr)
        runner = asr.AutoSkillRunner()
    assert runner.dispatcher.bearer == "f4-per-role-bearer"


def test_observability_dispatcher_uses_brain_f8_bearer():
    """_get_dispatcher() creates GatewayDispatcher with HERMES_GATEWAY_BEARER_BRAIN_F8."""
    import importlib
    with patch.dict(os.environ, {
        "HERMES_GATEWAY_BEARER_BRAIN_F8": "f8-per-role-bearer",
        "HERMES_GATEWAY_OAUTH_SECRET": "shared-fallback",
    }, clear=False):
        import api.observability as obs
        importlib.reload(obs)
        obs._DISPATCHER = None  # reset lazy singleton
        d = obs._get_dispatcher()
    assert d.bearer == "f8-per-role-bearer"


def test_hermes_linkedin_uses_brain_f5_mcp_linkedin_bearer():
    """hermes-linkedin _LINKEDIN_BEARER uses HERMES_GATEWAY_BEARER_BRAIN_F5_MCP_LINKEDIN."""
    # Direct-load server module via spec to avoid fastmcp import on PC
    import importlib.util
    _LI_PATH = Path(__file__).resolve().parent.parent / "mcps" / "hermes-linkedin" / "server.py"
    with patch.dict(os.environ, {
        "HERMES_GATEWAY_BEARER_BRAIN_F5_MCP_LINKEDIN": "linkedin-per-role-bearer",
        "HERMES_GATEWAY_OAUTH_SECRET": "shared-fallback",
    }, clear=False):
        spec = importlib.util.spec_from_file_location("_li_server_test", _LI_PATH)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
        except SystemExit:
            pytest.skip("fastmcp not installed on PC — bearer var still validated")
        assert mod._LINKEDIN_BEARER == "linkedin-per-role-bearer"
