"""UX-RM-F4-B: Lucide icons full pass + light theme OKLCH + motion tokens."""
import re
from pathlib import Path

ROOT       = Path(__file__).parent.parent
INDEX      = ROOT / "dashboard" / "index.html"
TOKENS     = ROOT / "dashboard" / "styles" / "tokens.css"
MOTION_CSS = ROOT / "dashboard" / "styles" / "motion.css"
LIGHT_CSS  = ROOT / "dashboard" / "styles" / "light.css"
ICON_JS    = ROOT / "dashboard" / "components" / "icon.js"
THEME_JS   = ROOT / "dashboard" / "components" / "theme_toggle.js"
APP_JS     = ROOT / "dashboard" / "app.js"


# ── G1 · Icon sprite present ────────────────────────────────────────────────

def test_svg_sprite_symbols_present():
    """index.html must define SVG <symbol id="i-*"> sprite entries."""
    content = INDEX.read_text(encoding="utf-8")
    assert 'symbol id="i-alert-triangle"' in content, "i-alert-triangle symbol missing"
    assert 'symbol id="i-pause"' in content, "i-pause symbol missing"
    assert 'symbol id="i-lock"' in content, "i-lock symbol missing"
    assert 'symbol id="i-eye"' in content, "i-eye symbol missing"
    count = content.count('<symbol id="i-')
    assert count >= 30, f"Expected ≥30 SVG symbols, found {count}"


# ── G2 · icon() helper ──────────────────────────────────────────────────────

def test_icon_helper_file_exists():
    assert ICON_JS.exists(), "dashboard/components/icon.js missing"


def test_icon_helper_exposes_window_icon():
    content = ICON_JS.read_text(encoding="utf-8")
    assert "window.icon = icon" in content, "window.icon not assigned in icon.js"


def test_icon_helper_returns_svg_use():
    content = ICON_JS.read_text(encoding="utf-8")
    assert '<use href="#i-' in content, "icon() does not produce <use href='#i-*'>"


# ── G3 · No naked emoji in component JS ─────────────────────────────────────

def test_no_naked_emoji_in_subsystem_tile():
    txt = (ROOT / "dashboard" / "components" / "subsystem_tile.js").read_text(encoding="utf-8")
    for emoji in ("🔗", "📧", "🕷", "🛡", "⚙", "🌐", "⏸"):
        assert emoji not in txt, f"Naked emoji {emoji!r} still in subsystem_tile.js"


def test_no_naked_emoji_in_rate_limit_gauge():
    txt = (ROOT / "dashboard" / "components" / "cobaia_rate_limit_gauge.js").read_text(encoding="utf-8")
    for emoji in ("👁", "🤝", "💬"):
        assert emoji not in txt, f"Naked emoji {emoji!r} still in cobaia_rate_limit_gauge.js"


def test_no_naked_emoji_in_sentry_banner():
    txt = (ROOT / "dashboard" / "components" / "cobaia_sentry_banner.js").read_text(encoding="utf-8")
    for emoji in ("🚨", "⚠"):
        assert emoji not in txt, f"Naked emoji {emoji!r} still in cobaia_sentry_banner.js"


# ── G4 · Light theme OKLCH ──────────────────────────────────────────────────

def test_light_css_exists():
    assert LIGHT_CSS.exists(), "dashboard/styles/light.css missing"


def test_light_theme_oklch_surface_scale():
    content = LIGHT_CSS.read_text(encoding="utf-8")
    assert "@supports (color: oklch" in content, "No @supports OKLCH block in light.css"
    for token in ("--s0:", "--s1:", "--s2:", "--s3:"):
        assert token in content, f"Missing surface token {token} in light.css"


def test_light_theme_text_scale_present():
    content = LIGHT_CSS.read_text(encoding="utf-8")
    for token in ("--text-1:", "--text-2:", "--text-3:", "--text-4:"):
        assert token in content, f"Missing text token {token} in light.css"


def test_light_theme_hex_fallback_present():
    """Hex fallback block must exist for pre-OKLCH browsers."""
    content = LIGHT_CSS.read_text(encoding="utf-8")
    assert "@supports" in content, "No @supports OKLCH block in light.css"
    # Both hex fallback and OKLCH values must be present
    assert "#f7f7fb" in content or "#f1f1f7" in content, "Missing hex surface fallback in light.css"


# ── G5 · Theme toggle ────────────────────────────────────────────────────────

def test_theme_toggle_file_exists():
    assert THEME_JS.exists(), "dashboard/components/theme_toggle.js missing"


def test_theme_toggle_storage_key():
    content = THEME_JS.read_text(encoding="utf-8")
    assert "hermes.theme" in content, "STORAGE_KEY must be 'hermes.theme'"


def test_theme_fouc_script_uses_correct_key():
    content = INDEX.read_text(encoding="utf-8")
    assert "hermes.theme" in content, "FOUC script must use 'hermes.theme' key"


# ── G6 · Motion tokens ───────────────────────────────────────────────────────

def test_motion_css_file_exists():
    assert MOTION_CSS.exists(), "dashboard/styles/motion.css missing"


def test_duration_scale_in_tokens():
    content = TOKENS.read_text(encoding="utf-8")
    for token in (
        "--duration-instant:", "--duration-fast:", "--duration-normal:",
        "--duration-slow:", "--duration-slower:", "--duration-slowest:",
    ):
        assert token in content, f"Missing {token} in tokens.css"


def test_easing_curves_in_tokens():
    content = TOKENS.read_text(encoding="utf-8")
    for token in ("--ease-linear:", "--ease-in:", "--ease-bounce:", "--ease-emphasis:"):
        assert token in content, f"Missing {token} in tokens.css"


def test_prefers_reduced_motion_in_motion_css():
    content = MOTION_CSS.read_text(encoding="utf-8")
    assert "prefers-reduced-motion: reduce" in content, "Missing reduced-motion media query"
    assert "animation-duration" in content, "Must zero animation-duration in reduced-motion"
    assert "transition-duration" in content, "Must zero transition-duration in reduced-motion"


def test_status_dot_classes_in_motion_css():
    content = MOTION_CSS.read_text(encoding="utf-8")
    for cls in (".status-dot", ".status-dot-green", ".status-dot-red", ".status-dot-amber"):
        assert cls in content, f"Missing {cls} in motion.css"


# ── G7 · CSS token refactors: no naked ms literals ──────────────────────────

def test_no_hardcoded_120ms_in_skill_proposals():
    """skill-proposals.css must not have bare '120ms' transition literals."""
    txt = (ROOT / "dashboard" / "styles" / "skill-proposals.css").read_text(encoding="utf-8")
    assert "120ms" not in txt, "Hardcoded 120ms still in skill-proposals.css"


def test_no_hardcoded_800ms_in_skill_proposals():
    txt = (ROOT / "dashboard" / "styles" / "skill-proposals.css").read_text(encoding="utf-8")
    assert "800ms" not in txt, "Hardcoded 800ms still in skill-proposals.css"


# ── G8 · Command palette theme commands registered ──────────────────────────

def test_theme_commands_registered_in_app_js():
    content = APP_JS.read_text(encoding="utf-8")
    assert "action-theme-cycle" in content, "Theme cycle command missing from app.js ACTION_COMMANDS"
    assert "HermesThemeToggle" in content, "HermesThemeToggle not wired in app.js"
