"""PA-F1 — access_matrix breadcrumb + hermes-hunter + hermes-llm gaps.

Verifies the 3 changes from the post-248h audit (2026-06-19):
  1. breadcrumb requester added (sentry_via_gateway.py BREADCRUMB bearer was fail-closed 403)
  2. hermes-hunter added to brain-f7-cobaia (email_verifier.py was fail-closed 403)
  3. hermes-llm added as defense-in-depth to brain sub-requesters that route LLM calls
  4. All active MCPs in config.yaml reachable by at least one requester path
  5. template_gallery.js broken <script> ref removed from index.html
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load access_matrix module without pulling in fastmcp (VM-only dep)
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parent.parent
_AM_PATH = _REPO / "mcps" / "gateway" / "access_matrix.py"
_spec = importlib.util.spec_from_file_location("_pa_f1_access_matrix", _AM_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
AccessMatrix = _mod.AccessMatrix
load_matrix = _mod.load_matrix

_MATRIX_FILE = _REPO / "mcps" / "gateway" / "access_matrix.json"
_CONFIG_FILE = _REPO / "mcps" / "gateway" / "config.yaml"
_INDEX_HTML = _REPO / "dashboard" / "index.html"


@pytest.fixture(scope="module")
def real_matrix() -> AccessMatrix:
    return load_matrix(_MATRIX_FILE)


# ---------------------------------------------------------------------------
# 1. breadcrumb gap fix (REGRESSION sentry telemetria silenciosa perdida)
# ---------------------------------------------------------------------------
def test_breadcrumb_requester_allows_sentry(real_matrix):
    """sentry_via_gateway.py BREADCRUMB bearer → sentry must not be fail-closed 403."""
    allowed, reason = real_matrix.check("breadcrumb", "sentry")
    assert allowed is True, f"breadcrumb→sentry denied: {reason}"


def test_breadcrumb_does_not_escalate_beyond_sentry(real_matrix):
    """breadcrumb is scoped to sentry only — no escalation to linkedin/llm."""
    for target in ("hermes-linkedin", "hermes-llm", "hermes-hunter", "hermes-prospects"):
        allowed, _ = real_matrix.check("breadcrumb", target)
        assert allowed is False, f"breadcrumb should NOT reach {target}"


# ---------------------------------------------------------------------------
# 2. brain-f7-cobaia hermes-hunter gap (email_verifier.py → 403 before fix)
# ---------------------------------------------------------------------------
def test_brain_f7_cobaia_allows_hermes_hunter(real_matrix):
    """email_verifier.py uses BRAIN_F7_COBAIA bearer → hermes-hunter must be allowed."""
    allowed, reason = real_matrix.check("brain-f7-cobaia", "hermes-hunter")
    assert allowed is True, f"brain-f7-cobaia→hermes-hunter denied: {reason}"


# ---------------------------------------------------------------------------
# 3. hermes-llm defense-in-depth on brain sub-requesters
# ---------------------------------------------------------------------------
def test_brain_f7_cobaia_allows_hermes_llm(real_matrix):
    """brain-f7-cobaia cobaia path needs hermes-llm for LLM reasoning (defense-in-depth)."""
    allowed, reason = real_matrix.check("brain-f7-cobaia", "hermes-llm")
    assert allowed is True, f"brain-f7-cobaia→hermes-llm denied: {reason}"


# ---------------------------------------------------------------------------
# 4. All active MCPs reachable by at least one requester
# ---------------------------------------------------------------------------
def test_all_active_mcp_targets_have_requester_path(real_matrix):
    """Every MCP with status:active in config.yaml is reachable by ≥1 non-wildcard requester
    (or by brain-core wildcard). Catches future MCPs added without matrix coverage."""
    if not _CONFIG_FILE.exists():
        pytest.skip("config.yaml not found")

    yaml_text = _CONFIG_FILE.read_text(encoding="utf-8")
    # Extract active MCP names (simple parse — avoids yaml dep)
    active_targets: list[str] = []
    current_name: str | None = None
    for line in yaml_text.splitlines():
        name_m = re.match(r"\s*-\s*name:\s*(\S+)", line)
        if name_m:
            current_name = name_m.group(1)
        if current_name and "status: active" in line:
            active_targets.append(current_name)
            current_name = None

    assert active_targets, "No active MCPs found in config.yaml — check parser"

    matrix_raw = json.loads(_MATRIX_FILE.read_text(encoding="utf-8"))
    rules = matrix_raw.get("rules", {})

    unreachable = []
    for target in active_targets:
        reachable = False
        for requester, rule in rules.items():
            allows = rule.get("allow", [])
            if "*" in allows or target in allows:
                reachable = True
                break
        if not reachable:
            unreachable.append(target)

    assert not unreachable, (
        f"Active MCPs with NO requester path (fail-closed 403): {unreachable}"
    )


# ---------------------------------------------------------------------------
# 5. template_gallery.js ref removed (index.html no longer 404s)
# ---------------------------------------------------------------------------
def test_template_gallery_ref_removed():
    """dashboard/index.html must not reference the non-existent template_gallery.js."""
    html = _INDEX_HTML.read_text(encoding="utf-8")
    assert "template_gallery.js" not in html, (
        "template_gallery.js still referenced in index.html — 404 on every page load"
    )
