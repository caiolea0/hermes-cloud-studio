"""
UX-RM-F7-B — A11y + H1 + div→button + Optimistic UI + Error Boundary
Tests: file existence, content smoke, HTML/JS patterns.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD = os.path.join(ROOT, "dashboard")
COMPONENTS = os.path.join(DASHBOARD, "components")


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


# ─────────────────────────────────────────────
# G1: axe_runner.js exists
# ─────────────────────────────────────────────
def test_axe_runner_file_exists():
    path = os.path.join(COMPONENTS, "axe_runner.js")
    assert os.path.isfile(path), "axe_runner.js not found"


# ─────────────────────────────────────────────
# G2: axe_runner references wcag2a + wcag2aa + wcag21aa
# ─────────────────────────────────────────────
def test_axe_runner_filters_wcag2aa():
    src = _read(os.path.join(COMPONENTS, "axe_runner.js"))
    assert "wcag2a" in src
    assert "wcag2aa" in src
    assert "wcag21aa" in src


# ─────────────────────────────────────────────
# G3: axe_runner covers all 17 pages
# ─────────────────────────────────────────────
def test_axe_runner_covers_17_pages():
    src = _read(os.path.join(COMPONENTS, "axe_runner.js"))
    pages = [
        "dashboard", "control", "cobaia", "pipeline-studio",
        "tasks", "prospects", "proposals", "audit", "linkedin",
        "skills", "skill-proposals", "lab", "memory", "missions",
        "claude", "mcp-gateway", "observability",
    ]
    for p in pages:
        assert p in src, f"Page '{p}' not in PAGE_IDS list in axe_runner.js"


# ─────────────────────────────────────────────
# G4: H1 injection function exists in app.js
# ─────────────────────────────────────────────
def test_navigate_injects_h1():
    src = _read(os.path.join(DASHBOARD, "app.js"))
    assert "_ensurePageH1" in src, "_ensurePageH1 function not found in app.js"
    assert "page-h1" in src, "page-h1 CSS class not used in app.js"


# ─────────────────────────────────────────────
# G5: _ensurePageH1 is called from navigate()
# ─────────────────────────────────────────────
def test_ensure_h1_called_from_navigate():
    src = _read(os.path.join(DASHBOARD, "app.js"))
    nav_start = src.find("function navigate(")
    assert nav_start != -1, "navigate() function not found"
    # Find the window.location.hash = page; assignment within navigate (not the read at top)
    hash_assign = src.find("window.location.hash = page", nav_start)
    assert hash_assign != -1, "window.location.hash = page not found inside navigate()"
    nav_block = src[nav_start:hash_assign]
    assert "_ensurePageH1" in nav_block, "_ensurePageH1 not called inside navigate()"


# ─────────────────────────────────────────────
# G6: Static divs with onclick converted to buttons in index.html
# ─────────────────────────────────────────────
def test_no_div_onclick_in_index_html():
    src = _read(os.path.join(DASHBOARD, "index.html"))
    # Find all <div ...> with onclick that are NOT inside a comment
    matches = re.findall(r"<div[^>]+onclick=", src)
    # Allow zero — all clickable divs must be buttons
    assert len(matches) == 0, (
        f"Found {len(matches)} <div ...onclick=...> in index.html — convert to <button>: {matches}"
    )


# ─────────────────────────────────────────────
# G7: optimistic_mutations.js exists
# ─────────────────────────────────────────────
def test_optimistic_mutation_file_exists():
    path = os.path.join(COMPONENTS, "optimistic_mutations.js")
    assert os.path.isfile(path), "optimistic_mutations.js not found"


# ─────────────────────────────────────────────
# G8: optimistic_mutations has rollback on error
# ─────────────────────────────────────────────
def test_optimistic_mutation_rollback_on_error():
    src = _read(os.path.join(COMPONENTS, "optimistic_mutations.js"))
    assert "rollback()" in src, "rollback() not called on error path"
    assert "catch" in src, "no catch block for rollback"


# ─────────────────────────────────────────────
# G9: error_boundary.js exists
# ─────────────────────────────────────────────
def test_error_boundary_file_exists():
    path = os.path.join(COMPONENTS, "error_boundary.js")
    assert os.path.isfile(path), "error_boundary.js not found"


# ─────────────────────────────────────────────
# G10: error_boundary renders fallback for data-component elements
# ─────────────────────────────────────────────
def test_error_boundary_renders_fallback_on_crash():
    src = _read(os.path.join(COMPONENTS, "error_boundary.js"))
    assert "_renderFallback" in src, "_renderFallback not defined"
    assert "data-component" in src, "error boundary does not check data-component attr"
    assert "error-boundary" in src, "error-boundary CSS class not used in fallback"


# ─────────────────────────────────────────────
# Bonus: axe_runner.js loaded in index.html head
# ─────────────────────────────────────────────
def test_a11y_scripts_in_index_html():
    src = _read(os.path.join(DASHBOARD, "index.html"))
    assert "axe_runner.js" in src, "axe_runner.js not loaded in index.html"
    assert "optimistic_mutations.js" in src, "optimistic_mutations.js not loaded in index.html"
    assert "error_boundary.js" in src, "error_boundary.js not loaded in index.html"


# ─────────────────────────────────────────────
# Bonus: A11y tab added to observability
# ─────────────────────────────────────────────
def test_a11y_tab_in_observability():
    src = _read(os.path.join(DASHBOARD, "index.html"))
    assert 'data-tab="a11y"' in src, "A11y tab not added to observability"
    assert "axe-runner-panel" in src, "axe-runner-panel mount point not found"
