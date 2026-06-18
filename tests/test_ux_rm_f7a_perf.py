"""
UX-RM-F7-A — Bundle Splitting + Skeleton Patterns + WS Reconnect Badge
Tests: static analysis of JS/HTML files (no browser required).
"""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
DASH = ROOT / "dashboard"
COMP = DASH / "components"


# ── helpers ────────────────────────────────────────────────────────────────

def _index_html():
    return (DASH / "index.html").read_text(encoding="utf-8-sig")


def _app_js():
    return (DASH / "app.js").read_text(encoding="utf-8")


def _loader_js():
    return (DASH / "loader.js").read_text(encoding="utf-8")


def _skeleton_patterns_js():
    return (COMP / "skeleton_patterns.js").read_text(encoding="utf-8")


def _ws_status_js():
    return (COMP / "ws_status_indicator.js").read_text(encoding="utf-8")


# ── T1: loader.js exists and exports loadComponent ─────────────────────────

def test_loader_file_exists():
    assert (DASH / "loader.js").exists(), "dashboard/loader.js not found"


def test_loader_exports_loadComponent():
    src = _loader_js()
    assert "window.loadComponent" in src, "loader.js must export window.loadComponent"
    assert "window.BUNDLE_VERSION" in src, "loader.js must export window.BUNDLE_VERSION"


# ── T2: skeleton_patterns.js has all 4 required presets ────────────────────

def test_skeleton_patterns_file_exists():
    assert (COMP / "skeleton_patterns.js").exists(), "skeleton_patterns.js not found"


def test_skeleton_patterns_has_4_presets():
    src = _skeleton_patterns_js()
    for preset in ("table", "card_grid", "kpi_strip", "timeline"):
        assert preset + ":" in src or preset + " :" in src, \
            f"skeleton_patterns.js missing preset: {preset}"
    assert "window.skeletonPatterns" in src, "must export window.skeletonPatterns"


def test_skeleton_patterns_aria_busy():
    src = _skeleton_patterns_js()
    assert 'aria-busy="true"' in src, "skeleton patterns must include aria-busy=true"


# ── T3: ws_status_indicator.js exists and exports HermesWSStatus ──────────

def test_ws_status_indicator_file_exists():
    assert (COMP / "ws_status_indicator.js").exists(), "ws_status_indicator.js not found"


def test_ws_status_indicator_exports_setState():
    src = _ws_status_js()
    assert "window.HermesWSStatus" in src, "ws_status_indicator.js must export window.HermesWSStatus"
    assert "setState" in src, "ws_status_indicator.js must expose setState method"


def test_ws_status_indicator_has_aria_live():
    src = _ws_status_js()
    assert "aria-live" in src, "ws_status_indicator.js must set aria-live for screen readers"
    assert "role" in src, "ws_status_indicator.js must set role=status"


# ── T4: lazy components NOT loaded as eager <script> tags in index.html ────

LAZY_COMPONENTS = [
    "command_palette.js",
    "brain_sidebar.js",
    "brain_confirm_drawer.js",
    "shortcuts_help_overlay.js",
    "onboarding_wizard.js",
    "skill_proposals_studio.js",
    "skill_proposals_modal.js",
]


def test_lazy_components_not_eager_in_index_html():
    html = _index_html()
    for comp in LAZY_COMPONENTS:
        pattern = r'<script[^>]+src=["\'][^"\']*' + re.escape(comp)
        assert not re.search(pattern, html), \
            f"{comp} must NOT be loaded as an eager <script> tag in index.html"


# ── T5: critical components still loaded eager ─────────────────────────────

CRITICAL_EAGER = [
    "skeleton.js",
    "toast.js",
    "breadcrumbs.js",
    "loader.js",
    "skeleton_patterns.js",
    "ws_status_indicator.js",
    "keyboard_shortcuts.js",
    "filter_persistence.js",
]


def test_critical_components_loaded_eager():
    html = _index_html()
    for comp in CRITICAL_EAGER:
        pattern = r'<script[^>]+src=["\'][^"\']*' + re.escape(comp)
        assert re.search(pattern, html), \
            f"{comp} must remain as an eager <script> tag in index.html"


# ── T6: WS reconnect uses exponential backoff capped at 30s ───────────────

def test_ws_reconnect_exponential_backoff_capped_30s():
    src = _app_js()
    # Must have retry attempt tracking
    assert "_wsRetryAttempt" in src, "app.js must track _wsRetryAttempt counter"
    # Must cap at 30000ms
    assert "30000" in src, "app.js WS backoff must cap at 30000ms"
    # Must use Math.pow or Math.min for backoff calculation
    assert "Math.pow" in src or "Math.min" in src, \
        "app.js must use Math.pow/Math.min for exponential backoff"
    # HermesWSStatus integration
    assert "HermesWSStatus" in src, "app.js must integrate window.HermesWSStatus"
