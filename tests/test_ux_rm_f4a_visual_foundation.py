"""UX-RM-F4-A: OKLCH tokens + Geist typography + scale system."""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
TOKENS = ROOT / "dashboard" / "styles" / "tokens.css"
TYPOGRAPHY = ROOT / "dashboard" / "styles" / "typography.css"
FONTS_DIR = ROOT / "dashboard" / "static" / "fonts"
INDEX = ROOT / "dashboard" / "index.html"
STYLES_CSS = ROOT / "dashboard" / "styles.css"


def test_tokens_css_exists():
    assert TOKENS.exists(), "dashboard/styles/tokens.css missing"


def test_typography_css_exists():
    assert TYPOGRAPHY.exists(), "dashboard/styles/typography.css missing"


def test_all_oklch_color_tokens_present():
    content = TOKENS.read_text(encoding="utf-8")
    count = content.count("oklch(")
    assert count >= 20, f"Expected ≥20 oklch() tokens, found {count}"


def test_space_scale_8px_base_present():
    content = TOKENS.read_text(encoding="utf-8")
    for token in ("--space-2:", "--space-4:", "--space-6:", "--space-8:", "--space-12:"):
        assert token in content, f"Missing {token} in tokens.css"
    assert "8px" in content, "--space-2 (8px) not found"
    assert "16px" in content, "--space-4 (16px) not found"


def test_radius_scale_present():
    content = TOKENS.read_text(encoding="utf-8")
    for token in ("--radius-xs:", "--radius-sm:", "--radius-md:", "--radius-lg:", "--radius-xl:", "--radius-2xl:", "--radius-full:"):
        assert token in content, f"Missing {token} in tokens.css"


def test_shadow_scale_present():
    content = TOKENS.read_text(encoding="utf-8")
    for token in ("--shadow-sm:", "--shadow-md:", "--shadow-lg:", "--shadow-xl:"):
        assert token in content, f"Missing {token} in tokens.css"


def test_z_index_scale_present():
    content = TOKENS.read_text(encoding="utf-8")
    for token in ("--z-base:", "--z-overlay:", "--z-drawer:", "--z-modal:", "--z-toast:", "--z-tooltip:"):
        assert token in content, f"Missing {token} in tokens.css"


def test_geist_fonts_self_hosted():
    sans = FONTS_DIR / "geist-sans-variable.woff2"
    mono = FONTS_DIR / "geist-mono-variable.woff2"
    assert sans.exists(), "geist-sans-variable.woff2 not found"
    assert mono.exists(), "geist-mono-variable.woff2 not found"
    assert sans.stat().st_size > 10_000, "geist-sans-variable.woff2 suspiciously small"
    assert mono.stat().st_size > 10_000, "geist-mono-variable.woff2 suspiciously small"


def test_font_scale_8_steps_present():
    content = TOKENS.read_text(encoding="utf-8")
    for token in ("--text-xs:", "--text-sm:", "--text-base:", "--text-lg:", "--text-xl:", "--text-2xl:", "--text-3xl:", "--text-4xl:"):
        assert token in content, f"Missing {token} in tokens.css"


def test_h1_h2_h3_h4_global_styles_present():
    content = TYPOGRAPHY.read_text(encoding="utf-8")
    for tag in ("h1", "h2", "h3", "h4"):
        assert f"\n{tag} {{" in content or f"\n{tag} " in content, f"Global {tag} style missing in typography.css"


def test_geist_font_face_in_typography():
    content = TYPOGRAPHY.read_text(encoding="utf-8")
    assert "font-family: 'Geist Sans'" in content, "Geist Sans @font-face missing"
    assert "font-family: 'Geist Mono'" in content, "Geist Mono @font-face missing"
    assert "font-display: swap" in content, "font-display: swap missing (FOIT risk)"
    assert "woff2-variations" in content, "Variable font format 'woff2-variations' missing"


def test_index_html_preload_fonts():
    content = INDEX.read_text(encoding="utf-8")
    assert "geist-sans-variable.woff2" in content, "Geist Sans preload missing in index.html"
    assert "geist-mono-variable.woff2" in content, "Geist Mono preload missing in index.html"
    assert 'rel="preload"' in content, 'preload rel missing in index.html'
    assert 'as="font"' in content, 'as="font" missing in index.html'


def test_typography_css_loaded_in_index():
    content = INDEX.read_text(encoding="utf-8")
    assert "typography.css" in content, "typography.css not linked in index.html"


def test_google_fonts_cdn_removed():
    content = INDEX.read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in content, "Google Fonts CDN still present (privacy + perf violation)"


def test_supports_fallback_present():
    content = TOKENS.read_text(encoding="utf-8")
    assert "@supports (color: oklch(" in content, "@supports oklch block missing — old browser fallback broken"


def test_tokens_not_in_styles_css():
    content = STYLES_CSS.read_text(encoding="utf-8")
    assert "--bg: #" not in content, "--bg hex literal still in styles.css (should be in tokens.css only)"
    assert "--accent: #" not in content, "--accent hex literal still in styles.css"


def test_body_uses_font_token():
    content = STYLES_CSS.read_text(encoding="utf-8")
    assert "font-family: var(--font-sans)" in content, "body font-family not using var(--font-sans) token"


def test_semantic_intent_tokens_present():
    content = TOKENS.read_text(encoding="utf-8")
    for token in ("--success:", "--warning:", "--error:", "--info:"):
        assert token in content, f"Missing semantic intent token {token}"


def test_text_scale_aliases_present():
    content = TOKENS.read_text(encoding="utf-8")
    for token in ("--text:", "--text-1:", "--text-2:", "--text-3:", "--text-4:"):
        assert token in content, f"Missing text alias {token} in tokens.css"
