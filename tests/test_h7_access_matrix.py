"""H7 B11 — Tests for mcps/gateway/access_matrix.py.

Cover defense-in-depth allowlist semantics: default policy, explicit allow,
wildcard, unknown requester, missing file fail-open.
"""
from __future__ import annotations

import json
from pathlib import Path

import importlib.util
import pytest

# Direct file load — mcps/gateway/__init__.py imports server which requires
# fastmcp (VM-only dep). Bypass to test access_matrix in isolation on PC dev.
_AM_PATH = Path(__file__).resolve().parent.parent / "mcps" / "gateway" / "access_matrix.py"
_spec = importlib.util.spec_from_file_location("_h7_access_matrix", _AM_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
AccessMatrix = _mod.AccessMatrix
load_matrix = _mod.load_matrix


# ---------------------------------------------------------------------------
# AccessMatrix.check semantics
# ---------------------------------------------------------------------------

def test_unknown_requester_default_deny():
    m = AccessMatrix(default_policy="deny", rules={})
    allowed, reason = m.check("brain-rogue", "sentry")
    assert allowed is False
    assert "default_deny" in reason


def test_unknown_requester_default_allow():
    m = AccessMatrix(default_policy="allow", rules={})
    allowed, reason = m.check("brain-rogue", "sentry")
    assert allowed is True
    assert "default_allow" in reason


def test_wildcard_allows_any_target():
    m = AccessMatrix(default_policy="deny", rules={
        "brain-core": {"allow": ["*"]},
    })
    for target in ("sentry", "hermes-linkedin", "hermes-skills", "hermes-prospects"):
        allowed, _ = m.check("brain-core", target)
        assert allowed is True, f"wildcard should allow {target}"


def test_explicit_allow_lets_named_target_through():
    m = AccessMatrix(default_policy="deny", rules={
        "brain-f4": {"allow": ["sentry", "hermes-skills"]},
    })
    allowed, _ = m.check("brain-f4", "sentry")
    assert allowed is True
    allowed, _ = m.check("brain-f4", "hermes-skills")
    assert allowed is True


def test_explicit_allow_blocks_unlisted_target():
    """B11 mitigation core — brain-f4 cannot escalate to hermes-linkedin."""
    m = AccessMatrix(default_policy="deny", rules={
        "brain-f4": {"allow": ["sentry", "hermes-skills"]},
    })
    allowed, reason = m.check("brain-f4", "hermes-linkedin")
    assert allowed is False
    assert "not_in_allowlist" in reason


def test_empty_requester_treated_as_unknown():
    m = AccessMatrix(default_policy="deny", rules={"brain-core": {"allow": ["*"]}})
    allowed, _ = m.check("", "sentry")
    assert allowed is False


def test_invalid_default_policy_falls_back_to_deny():
    m = AccessMatrix(default_policy="lol_yes_please", rules={})
    assert m.default_policy == "deny"
    allowed, _ = m.check("brain-rogue", "sentry")
    assert allowed is False


# ---------------------------------------------------------------------------
# load_matrix file loading
# ---------------------------------------------------------------------------

def test_load_matrix_from_real_file_picks_up_default_policy_and_rules(tmp_path):
    p = tmp_path / "access_matrix.json"
    p.write_text(json.dumps({
        "version": 1,
        "default_policy": "deny",
        "rules": {
            "brain-f6": {"allow": ["sentry", "hermes-linkedin"]},
        },
    }), encoding="utf-8")
    m = load_matrix(p)
    assert m.default_policy == "deny"
    assert "brain-f6" in m.rules
    allowed, _ = m.check("brain-f6", "hermes-linkedin")
    assert allowed is True
    allowed, _ = m.check("brain-f6", "hermes-skills")
    assert allowed is False


def test_load_matrix_missing_file_fail_closed(tmp_path):
    """R6 hardening: missing config -> fail-CLOSED (deny-all).

    Reverted from fail-open: inverting security posture on partial deploy
    or permissions error was unsafe. Now CRITICAL log + default_policy='deny'.
    """
    p = tmp_path / "does_not_exist.json"
    m = load_matrix(p)
    assert m.default_policy == "deny"


def test_load_matrix_malformed_json_fail_closed(tmp_path):
    """R6 hardening: parse error -> fail-CLOSED (deny-all)."""
    p = tmp_path / "broken.json"
    p.write_text("{ not valid json ", encoding="utf-8")
    m = load_matrix(p)
    assert m.default_policy == "deny"


def test_repo_access_matrix_json_loads_and_has_expected_requesters():
    """Sanity: shipped config file parses + contains documented requesters."""
    repo_root = Path(__file__).resolve().parent.parent
    p = repo_root / "mcps" / "gateway" / "access_matrix.json"
    assert p.exists(), f"shipped access_matrix.json missing at {p}"
    m = load_matrix(p)
    assert m.default_policy == "deny"
    # Documented requester pinning — change deliberately if matrix evolves
    for r in ("brain-core", "brain-f4", "brain-f5-mcp-linkedin", "brain-f6",
              "brain-f7-cobaia", "brain-f8", "brain-f9", "api"):
        assert r in m.rules, f"requester {r} missing from shipped matrix"
    # Mitigation contract: brain-f4 must NOT access hermes-linkedin
    allowed, _ = m.check("brain-f4", "hermes-linkedin")
    assert allowed is False
    # brain-f5-mcp-linkedin (called by start_campaign delegate) must access hermes-linkedin
    allowed, _ = m.check("brain-f5-mcp-linkedin", "hermes-linkedin")
    assert allowed is True
