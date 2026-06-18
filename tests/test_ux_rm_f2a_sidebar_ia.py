"""UX-RM-F2-A — Sidebar consolidation 17→8 groups + breadcrumbs

Gates:
  G3: grep "class=\"nav-item\"" dashboard/index.html → no nav-page items (only footer)
  G4: 8 nav-group/single entries present
  G5: all 17 old pages still routable
  G6: breadcrumb-mount div present
  G7: HermesBreadcrumbs + toggleNavGroup in app.js
"""
from pathlib import Path
import re

ROOT = Path(__file__).parent.parent
INDEX_HTML = ROOT / "dashboard" / "index.html"
APP_JS = ROOT / "dashboard" / "app.js"
BREADCRUMBS_JS = ROOT / "dashboard" / "components" / "breadcrumbs.js"
STYLES_CSS = ROOT / "dashboard" / "styles.css"

OLD_PAGES = [
    "control", "dashboard", "prospects", "proposals", "audit",
    "pipeline-studio", "tasks", "skills", "skill-proposals", "linkedin",
    "cobaia", "lab", "memory", "missions", "claude", "mcp-gateway", "observability",
]

EXPECTED_GROUPS = ["operations", "outreach", "intelligence", "devtools"]
EXPECTED_SINGLES = ["dashboard", "missions", "observability"]


def _html() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def _appjs() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_no_flat_nav_item_pages_in_html():
    """G3: .nav-item[data-page] divs replaced — only nav-single/nav-sub-item/nav-group remain."""
    html = _html()
    # Old pattern: <div class="nav-item" ... data-page=
    flat_page_divs = re.findall(r'<div[^>]+class="nav-item[^"]*"[^>]+data-page=', html)
    flat_page_divs += re.findall(r'<div[^>]+data-page=[^>]+class="nav-item[^"]*"', html)
    assert flat_page_divs == [], (
        f"Found {len(flat_page_divs)} old .nav-item[data-page] divs still in HTML: {flat_page_divs}"
    )


def test_8_nav_groups_present_in_html():
    """G4: 4 collapsible groups + 3 nav-singles (Dashboard/Missions/Observability) = 7 top-level items.
    Footer G8 (Settings) counts separately — total sidebar entries = 8."""
    html = _html()
    groups = re.findall(r'data-group="(\w+)"', html)
    singles = re.findall(r'class="nav-single"[^>]+data-page="(\w[\w-]*)"', html)
    singles += re.findall(r'data-page="(\w[\w-]*)"[^>]+class="nav-single"', html)

    for g in EXPECTED_GROUPS:
        assert g in groups, f"nav-group data-group='{g}' missing from HTML"
    for s in EXPECTED_SINGLES:
        assert s in singles, f"nav-single data-page='{s}' missing from HTML"


def test_all_17_old_pages_have_entry_points():
    """G5: every old data-page value still present as a routable entry in the new nav."""
    html = _html()
    found = set(re.findall(r'data-page="([\w-]+)"', html))
    missing = [p for p in OLD_PAGES if p not in found]
    assert missing == [], f"These page IDs missing from new nav: {missing}"


def test_breadcrumb_mount_present():
    """G6: breadcrumb-mount div in index.html between header and main content."""
    html = _html()
    assert 'id="breadcrumb-mount"' in html, "breadcrumb-mount div missing from index.html"
    assert 'breadcrumb-bar' in html, ".breadcrumb-bar class missing"


def test_nav_group_js_functions_present():
    """G7: toggleNavGroup + _expandNavGroup + _restoreNavGroups + HermesBreadcrumbs in app.js/breadcrumbs.js."""
    appjs = _appjs()
    assert 'function toggleNavGroup' in appjs, "toggleNavGroup() missing from app.js"
    assert 'function _expandNavGroup' in appjs, "_expandNavGroup() missing from app.js"
    assert 'function _restoreNavGroups' in appjs, "_restoreNavGroups() missing from app.js"
    assert '_PAGE_TO_GROUP' in appjs, "_PAGE_TO_GROUP mapping missing from app.js"
    assert 'hermes.nav.expanded_groups' in appjs, "localStorage key missing from app.js"

    assert BREADCRUMBS_JS.exists(), "dashboard/components/breadcrumbs.js not created"
    bc = BREADCRUMBS_JS.read_text(encoding="utf-8")
    assert 'HermesBreadcrumbs' in bc, "HermesBreadcrumbs class missing from breadcrumbs.js"
    assert 'update(' in bc, "update() method missing from breadcrumbs.js"
