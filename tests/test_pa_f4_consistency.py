"""
PA-F4 consistency tests — font-size tokenization + backdrop-filter glass migration.

G1 BLACKLIST R2 INTACTO 73 SS
G2 pytest 535+ PASS 0 FAIL (529 + 6)
G3 orphan tokens added
G4 664 font-size tokenized (grep hardcoded → 0)
G5 backdrop-filter → glass vars/classes
"""
import re
import os
from pathlib import Path


TOKENS_CSS = Path("dashboard/styles/tokens.css")
DASHBOARD_DIR = Path("dashboard")

ORPHAN_TOKENS = {
    "--text-3xs":      "9px",
    "--text-2xs":      "10px",
    "--text-xxs":      "12px",
    "--text-sm-plus":  "15px",
    "--text-lg-plus":  "18px",
    "--text-xl-plus":  "22px",
    "--text-2xl-alt":  "26px",
    "--text-2xl-plus": "28px",
    "--text-3xl-alt":  "32px",
}

EXISTING_TOKENS = {
    "--text-xs":   "11px",
    "--text-sm":   "13px",
    "--text-base": "14px",
    "--text-lg":   "16px",
    "--text-xl":   "20px",
    "--text-2xl":  "24px",
    "--text-3xl":  "30px",
    "--text-4xl":  "36px",
    "--text-5xl":  "48px",
}

GLASS_BLUR_TOKENS = {
    "--glass-blur-xs":  "blur(4px)",
    "--glass-blur-sm":  "blur(6px)",
    "--glass-blur-md":  "blur(8px)",
    "--glass-blur-lg":  "blur(12px)",
    "--glass-blur-xl":  "blur(16px)",
    "--glass-blur-2xl": "blur(20px)",
    "--glass-blur-3xl": "blur(24px)",
}


def _read_dashboard_files(extensions=(".css", ".js", ".html"), skip_dirs=("vendor",)):
    """Read all non-vendor dashboard files matching extensions."""
    results = {}
    for root, dirs, files in os.walk(DASHBOARD_DIR):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            if Path(fname).suffix in extensions:
                p = os.path.join(root, fname)
                try:
                    results[p] = Path(p).read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    pass
    return results


def test_orphan_font_tokens_added():
    """All 9 orphan px values now have CSS custom properties in tokens.css."""
    content = TOKENS_CSS.read_text(encoding="utf-8")
    missing = []
    for token, px_val in ORPHAN_TOKENS.items():
        # Check token is declared with the exact px value
        pattern = re.compile(rf"{re.escape(token)}\s*:\s*{re.escape(px_val)}\s*;")
        if not pattern.search(content):
            missing.append(f"{token}: {px_val}")
    assert not missing, f"Missing orphan tokens in tokens.css: {missing}"


def test_font_token_values_preserve_exact():
    """Token values match EXACT original px — zero visual change (Opção A)."""
    content = TOKENS_CSS.read_text(encoding="utf-8")
    all_tokens = {**ORPHAN_TOKENS, **EXISTING_TOKENS}
    wrong = []
    for token, expected_px in all_tokens.items():
        pattern = re.compile(rf"{re.escape(token)}\s*:\s*([0-9]+px)\s*;")
        m = pattern.search(content)
        if m and m.group(1) != expected_px:
            wrong.append(f"{token}: expected {expected_px}, got {m.group(1)}")
        elif not m:
            wrong.append(f"{token}: NOT FOUND in tokens.css")
    assert not wrong, f"Token value mismatches (visual change risk): {wrong}"


def test_zero_hardcoded_font_size_css():
    """No hardcoded font-size:Xpx remaining in dashboard files (excl vendor)."""
    files = _read_dashboard_files()
    pattern = re.compile(r"font-size:\s*[0-9]+px")
    hits = []
    for path, content in files.items():
        for m in pattern.finditer(content):
            hits.append(f"{path}: {m.group(0)}")
    assert not hits, f"Hardcoded font-size px values found ({len(hits)}):\n" + "\n".join(hits[:20])


def test_all_px_values_have_token():
    """Every distinct pixel value that appeared in the codebase maps to a token."""
    px_to_token = {
        "9px":  "--text-3xs",
        "10px": "--text-2xs",
        "11px": "--text-xs",
        "12px": "--text-xxs",
        "13px": "--text-sm",
        "14px": "--text-base",
        "15px": "--text-sm-plus",
        "16px": "--text-lg",
        "18px": "--text-lg-plus",
        "20px": "--text-xl",
        "22px": "--text-xl-plus",
        "24px": "--text-2xl",
        "26px": "--text-2xl-alt",
        "28px": "--text-2xl-plus",
        "30px": "--text-3xl",
        "32px": "--text-3xl-alt",
        "36px": "--text-4xl",
        "48px": "--text-5xl",
    }
    content = TOKENS_CSS.read_text(encoding="utf-8")
    missing = []
    for px, token in px_to_token.items():
        if token not in content:
            missing.append(f"{token} ({px})")
    assert not missing, f"Tokens not defined in tokens.css: {missing}"


def test_glass_blur_tokens_added():
    """Glass blur CSS custom properties defined in tokens.css."""
    content = TOKENS_CSS.read_text(encoding="utf-8")
    missing = []
    for token in GLASS_BLUR_TOKENS:
        if token not in content:
            missing.append(token)
    assert not missing, f"Missing glass blur tokens: {missing}"


def test_backdrop_filter_uses_glass_vars():
    """
    No literal blur(Xpx) in backdrop-filter outside glass.css.
    CSS files: use var(--glass-blur-*).
    JS/HTML: no inline style= with backdrop-filter:blur( literal px.
    """
    files = _read_dashboard_files()
    # Check for literal blur(Npx) in backdrop-filter (not inside glass.css which defines them)
    literal_pattern = re.compile(r"backdrop-filter:\s*blur\([0-9]+px\)")
    hits = []
    for path, content in files.items():
        if path.endswith("glass.css"):
            continue
        for m in literal_pattern.finditer(content):
            hits.append(f"{path}: {m.group(0)}")
    assert not hits, (
        f"Literal backdrop-filter:blur(Xpx) found ({len(hits)}) — should use var(--glass-blur-*):\n"
        + "\n".join(hits[:20])
    )
