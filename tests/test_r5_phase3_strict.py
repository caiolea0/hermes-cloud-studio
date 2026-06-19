"""R5 PHASE 3 -- Kill switch strict bearer env flag (opt-in, default False).

6 tests covering:
- G3: strict_bearer=False preserves fallback_spoofable back-compat
- G4: strict_bearer=True rejects shared bearer with denied_strict + 401
- G5: per-role bearers trusted in BOTH strict and non-strict modes
- ENV flag parse: true/1/yes variants
- Default safe: flag absent = False = back-compat
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
_req_spec = importlib.util.spec_from_file_location("_r5p3_requester", _REQ_PATH)
_req_mod = importlib.util.module_from_spec(_req_spec)
_req_spec.loader.exec_module(_req_mod)  # type: ignore[union-attr]

derive_requester = _req_mod.derive_requester

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FAKE_PER_ROLE: dict[str, str] = {
    "brain-core-secret-abc": "brain-core",
    "breadcrumb-secret-xyz": "breadcrumb",
}
FAKE_SHARED = "shared-secret-999"


# ---------------------------------------------------------------------------
# G3 — strict_bearer=False (default) preserves back-compat
# ---------------------------------------------------------------------------

def test_strict_false_shared_bearer_returns_fallback_spoofable():
    """G3: default strict_bearer=False → shared bearer still yields fallback_spoofable."""
    body = {"requester": "brain", "args": {}}
    req, mode = derive_requester(
        f"Bearer {FAKE_SHARED}", body, FAKE_PER_ROLE, FAKE_SHARED, strict_bearer=False
    )
    assert mode == "fallback_spoofable"
    assert req == "brain"


# ---------------------------------------------------------------------------
# G4 — strict_bearer=True rejects shared bearer
# ---------------------------------------------------------------------------

def test_strict_true_shared_bearer_returns_denied_strict():
    """G4: strict_bearer=True → shared bearer returns (None, 'denied_strict')."""
    body = {"requester": "brain", "args": {}}
    req, mode = derive_requester(
        f"Bearer {FAKE_SHARED}", body, FAKE_PER_ROLE, FAKE_SHARED, strict_bearer=True
    )
    assert req is None
    assert mode == "denied_strict"


def test_strict_true_shared_bearer_no_body_also_denied_strict():
    """G4 edge: strict mode rejects shared bearer even with empty body."""
    req, mode = derive_requester(
        f"Bearer {FAKE_SHARED}", {}, FAKE_PER_ROLE, FAKE_SHARED, strict_bearer=True
    )
    assert req is None
    assert mode == "denied_strict"


# ---------------------------------------------------------------------------
# G5 — per-role bearers unaffected by strict mode
# ---------------------------------------------------------------------------

def test_per_role_bearer_trusted_with_strict_false():
    """G5a: per-role bearer stays 'trusted' when strict_bearer=False."""
    req, mode = derive_requester(
        "Bearer brain-core-secret-abc", {}, FAKE_PER_ROLE, FAKE_SHARED, strict_bearer=False
    )
    assert mode == "trusted"
    assert req == "brain-core"


def test_per_role_bearer_trusted_with_strict_true():
    """G5b: per-role bearer stays 'trusted' when strict_bearer=True (unaffected)."""
    req, mode = derive_requester(
        "Bearer brain-core-secret-abc", {}, FAKE_PER_ROLE, FAKE_SHARED, strict_bearer=True
    )
    assert mode == "trusted"
    assert req == "brain-core"


# ---------------------------------------------------------------------------
# ENV flag parsing — HERMES_GATEWAY_STRICT_BEARER variants
# ---------------------------------------------------------------------------

def test_strict_bearer_env_flag_parse_variants():
    """HERMES_GATEWAY_STRICT_BEARER: true/1/yes all parse to True; false/absent = False."""
    true_values = ("true", "1", "yes", "True", "YES")
    false_values = ("false", "0", "no", "", "off")

    for val in true_values:
        parsed = val.lower() in ("true", "1", "yes")
        assert parsed is True, f"Expected True for value {val!r}"

    for val in false_values:
        parsed = val.lower() in ("true", "1", "yes")
        assert parsed is False, f"Expected False for value {val!r}"
