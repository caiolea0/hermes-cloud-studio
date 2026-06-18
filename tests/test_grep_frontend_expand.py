"""F.1 — grep_frontend.py expand scope tests.

Verifies that the expanded scan (components/*.js + HTML inline scripts) correctly
reduces false orphans and captures endpoints from component files.

Gates:
  G2: 259+ pytest PASS (254 baseline + 5 new)
  G3: orphan count drops ~30% vs app.js-only baseline
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = ROOT / ".claude" / "skills" / "hermes-frontend-gap" / "scripts"
COMPONENTS_DIR = ROOT / "dashboard" / "components"
APP_JS = ROOT / "dashboard" / "app.js"


def _load_grep_frontend():
    spec = importlib.util.spec_from_file_location(
        "grep_frontend_f1", SCRIPTS_DIR / "grep_frontend.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gf():
    return _load_grep_frontend()


# ── G1: get_js_sources includes components ────────────────────────────────────

def test_app_js_glob_includes_components(gf):
    """get_js_sources() returns app.js + component files."""
    sources = gf.get_js_sources()
    names = [s.name for s in sources]
    assert "app.js" in names, "app.js must be first source"
    assert "panic_button.js" in names, "panic_button.js must be included"
    assert "subsystem_tile.js" in names, "subsystem_tile.js must be included"
    assert len(sources) >= 10, f"expected >=10 sources, got {len(sources)}"


# ── G2: extract_html_inline_scripts works ────────────────────────────────────

def test_extract_html_inline_scripts(gf, tmp_path):
    """extract_html_inline_scripts finds fetch() calls in <script> blocks."""
    html = tmp_path / "test.html"
    html.write_text(
        "<html><body>"
        '<script>fetch("/api/test/endpoint")</script>'
        "</body></html>",
        encoding="utf-8",
    )
    result = gf.extract_html_inline_scripts(html)
    assert "/api/test/endpoint" in result, "must capture fetch() in inline <script>"
    assert result["/api/test/endpoint"][0]["file"].endswith("test.html"), \
        "source file must be the HTML file"


# ── G3: merge_consumption deduplicates correctly ─────────────────────────────

def test_merge_consumption_dedups_endpoints(gf):
    """merge_consumption combines calls from multiple sources for same endpoint."""
    d1 = {"/api/prospects": [{"file": "app.js", "line": 1, "snippet": "fetch('/api/prospects')"}]}
    d2 = {"/api/prospects": [{"file": "subsystem_tile.js", "line": 5, "snippet": "api('/api/prospects')"}]}
    d3 = {"/api/tasks": [{"file": "app.js", "line": 10, "snippet": "fetch('/api/tasks')"}]}
    merged = gf.merge_consumption([d1, d2, d3])
    # Same endpoint from multiple sources merged
    assert "/api/prospects" in merged
    assert len(merged["/api/prospects"]) == 2, "must have 2 calls from 2 sources"
    sources = {c["file"] for c in merged["/api/prospects"]}
    assert "app.js" in sources
    assert "subsystem_tile.js" in sources
    # Different endpoint preserved
    assert "/api/tasks" in merged


# ── G4: panic_button.js endpoint now detected ────────────────────────────────

def test_panic_button_endpoint_not_orphan(gf):
    """panic_button.js POST /api/daemon/subsystems/all/pause must be consumed."""
    panic_js = COMPONENTS_DIR / "panic_button.js"
    if not panic_js.exists():
        pytest.skip("panic_button.js not found")
    result = gf.extract_js_consumption(panic_js)
    found_daemon = [ep for ep in result if "daemon" in ep or "subsystem" in ep]
    assert len(found_daemon) >= 1, (
        f"panic_button.js must consume >=1 daemon/subsystem endpoint. "
        f"Got endpoints: {sorted(result.keys())}"
    )


# ── G5: expanded scope >= app.js alone ───────────────────────────────────────

def test_expanded_scope_exceeds_app_js_alone(gf):
    """Scanning all sources finds strictly more endpoints than app.js alone."""
    app_only = gf.extract_js_consumption(APP_JS)
    all_sources = gf.get_js_sources()
    merged = gf.merge_consumption([gf.extract_js_consumption(s) for s in all_sources])
    assert len(merged) > len(app_only), (
        f"Expanded scope ({len(merged)} eps) must exceed app.js alone ({len(app_only)} eps)"
    )
    # Specifically: cobaia and observability endpoints must appear (from components)
    cobaia_eps = [ep for ep in merged if "cobaia" in ep]
    assert len(cobaia_eps) >= 3, f"expected >=3 cobaia endpoints, got {cobaia_eps}"
