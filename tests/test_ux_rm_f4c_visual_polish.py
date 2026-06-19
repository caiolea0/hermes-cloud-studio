"""
UX-RM-F4-C — Liquid Glass + Micro-interactions + Motion patterns tests.
10 assertions covering glass primitives, interactions, motion completeness,
data-dense audit, and accessibility media queries.
"""
import re
from pathlib import Path

DASHBOARD = Path(__file__).parent.parent / "dashboard"
STYLES_DIR = DASHBOARD / "styles"
STYLES_CSS  = DASHBOARD / "styles.css"
MOTION_CSS  = STYLES_DIR / "motion.css"
GLASS_CSS   = STYLES_DIR / "glass.css"
INTER_CSS   = STYLES_DIR / "interactions.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ─── 1. glass.css exists ────────────────────────────────────────────────────

def test_glass_css_file_exists():
    assert GLASS_CSS.exists(), "dashboard/styles/glass.css must be created (F4-C)"


# ─── 2. 3 glass primitives defined ──────────────────────────────────────────

def test_3_glass_primitives_chrome_overlay_floating():
    css = _read(GLASS_CSS)
    assert ".glass-chrome" in css,   "glass.css must define .glass-chrome"
    assert ".glass-overlay" in css,  "glass.css must define .glass-overlay"
    assert ".glass-floating" in css, "glass.css must define .glass-floating"
    # Each primitive must have backdrop-filter
    for cls in (".glass-chrome", ".glass-overlay", ".glass-floating"):
        # Find the block after the selector
        idx = css.find(cls)
        block = css[idx : idx + 300]
        assert "backdrop-filter" in block, f"{cls} must declare backdrop-filter"


# ─── 3. Light theme glass variants present ───────────────────────────────────

def test_light_theme_glass_variants_present():
    css = _read(GLASS_CSS)
    assert '[data-theme="light"] .glass-chrome' in css,   "light theme .glass-chrome override required"
    assert '[data-theme="light"] .glass-overlay' in css,  "light theme .glass-overlay override required"
    assert '[data-theme="light"] .glass-floating' in css, "light theme .glass-floating override required"


# ─── 4. prefers-reduced-transparency media query ─────────────────────────────

def test_prefers_reduced_transparency_query():
    css = _read(GLASS_CSS)
    assert "@media (prefers-reduced-transparency: reduce)" in css, \
        "glass.css must contain @media (prefers-reduced-transparency: reduce) block"
    # Verify the file also explicitly disables backdrop-filter
    assert "backdrop-filter: none" in css, \
        "glass.css must set backdrop-filter: none within reduced-transparency block"


# ─── 5. interactions.css exists ─────────────────────────────────────────────

def test_interactions_css_file_exists():
    assert INTER_CSS.exists(), "dashboard/styles/interactions.css must be created (F4-C)"


# ─── 6. btn-base transition uses duration motion tokens ─────────────────────

def test_btn_base_transition_uses_motion_tokens():
    css = _read(INTER_CSS)
    assert ".btn-base" in css, "interactions.css must define .btn-base"
    idx = css.find(".btn-base")
    block = css[idx : idx + 400]
    assert "var(--duration-fast)" in block, \
        ".btn-base transition must use var(--duration-fast) from motion tokens"
    assert "var(--ease-out)" in block, \
        ".btn-base transition must use var(--ease-out) easing"


# ─── 7. card-interactive lift pattern ────────────────────────────────────────

def test_card_interactive_lift_pattern():
    css = _read(INTER_CSS)
    assert ".card-interactive" in css, "interactions.css must define .card-interactive"
    idx = css.find(".card-interactive")
    block = css[idx : idx + 600]
    assert "translateY(-2px)" in block, \
        ".card-interactive hover must lift with translateY(-2px)"
    assert "var(--shadow-lg)" in block, \
        ".card-interactive hover must apply var(--shadow-lg)"
    assert "var(--accent-l)" in block, \
        ".card-interactive hover must highlight with var(--accent-l) border"


# ─── 8. :focus-visible global rule present ───────────────────────────────────

def test_focus_visible_global_present():
    css = _read(INTER_CSS)
    assert ":focus-visible" in css, "interactions.css must define global :focus-visible rule"
    idx = css.find(":focus-visible")
    block = css[idx : idx + 200]
    assert "outline:" in block, ":focus-visible must set outline"
    assert "var(--accent)" in block, ":focus-visible outline must use var(--accent)"
    assert "outline-offset" in block, ":focus-visible must set outline-offset"


# ─── 9. Data-dense surfaces have NO backdrop-filter ──────────────────────────

DATA_DENSE_PATTERNS = [
    r"\.stat-card\s*\{[^}]*backdrop-filter",
    r"\.activity-item\s*\{[^}]*backdrop-filter",
    r"\.prospect-row\s*\{[^}]*backdrop-filter",
    r"\.data-table\s*\{[^}]*backdrop-filter",
    r"\.table-row\s*\{[^}]*backdrop-filter",
    r"\.kpi-card\s*\{[^}]*backdrop-filter",
]

def test_data_dense_surfaces_no_backdrop_filter():
    css = _read(STYLES_CSS)
    for pattern in DATA_DENSE_PATTERNS:
        match = re.search(pattern, css, re.DOTALL)
        assert match is None, \
            f"Data-dense selector matched {pattern!r} — remove backdrop-filter from dense surfaces"


# ─── 10. Motion patterns complete (fade-in/out, slide-up/right, scale-in) ────

def test_motion_patterns_complete():
    css = _read(MOTION_CSS)
    required = [
        ".motion-fade-in",
        ".motion-fade-out",
        ".motion-slide-up",
        ".motion-slide-right",
        ".motion-scale-in",
    ]
    for cls in required:
        assert cls in css, f"motion.css must define {cls} (F4-C adds slide-right + scale-in)"
