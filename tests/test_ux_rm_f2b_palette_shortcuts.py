"""
UX-RM-F2-B — Command Palette + Keyboard Shortcuts + Filter Persistence
Tests: static analysis of JS files (no browser required).
"""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
DASH = ROOT / "dashboard"
COMP = DASH / "components"


# ── G1: file existence ─────────────────────────────────────────────────────

def test_command_palette_file_exists():
    assert (COMP / "command_palette.js").exists(), "command_palette.js not found"


def test_keyboard_shortcuts_file_exists():
    assert (COMP / "keyboard_shortcuts.js").exists(), "keyboard_shortcuts.js not found"


def test_shortcuts_help_overlay_file_exists():
    assert (COMP / "shortcuts_help_overlay.js").exists(), "shortcuts_help_overlay.js not found"


def test_filter_persistence_file_exists():
    assert (COMP / "filter_persistence.js").exists(), "filter_persistence.js not found"


# ── G2: script tags in index.html ──────────────────────────────────────────

def _index_html():
    return (DASH / "index.html").read_text(encoding="utf-8-sig")


def test_index_html_includes_command_palette():
    assert "command_palette.js" in _index_html()


def test_index_html_includes_keyboard_shortcuts():
    assert "keyboard_shortcuts.js" in _index_html()


def test_index_html_includes_filter_persistence():
    assert "filter_persistence.js" in _index_html()


# ── G3: command palette implementation ────────────────────────────────────

def _palette_js():
    return (COMP / "command_palette.js").read_text(encoding="utf-8")


def test_command_palette_exposes_global():
    src = _palette_js()
    assert "window.HermesCommandPalette" in src


def test_command_palette_register_method():
    src = _palette_js()
    assert "register(" in src or "register (" in src


def test_command_palette_cmd_k_binding():
    src = _palette_js()
    assert "key === 'k'" in src
    assert "metaKey" in src or "ctrlKey" in src


def test_command_palette_arrow_navigation():
    src = _palette_js()
    assert "ArrowDown" in src
    assert "ArrowUp" in src


def test_command_palette_escape_close():
    src = _palette_js()
    assert "Escape" in src
    assert "close()" in src or "this.close()" in src


def test_command_palette_wcag_aria():
    src = _palette_js()
    assert 'role', 'dialog' in src
    assert "aria-modal" in src
    assert "aria-label" in src


def test_command_palette_focus_trap():
    src = _palette_js()
    assert "_prevFocused" in src or "prevFocused" in src
    assert "focus()" in src


# ── G4: keyboard shortcuts ─────────────────────────────────────────────────

def _shortcuts_js():
    return (COMP / "keyboard_shortcuts.js").read_text(encoding="utf-8")


def test_keyboard_shortcuts_exposes_global():
    src = _shortcuts_js()
    assert "window.HermesKeyboardShortcuts" in src


def test_keyboard_shortcuts_register_method():
    src = _shortcuts_js()
    assert "register(" in src or "register (" in src


def test_keyboard_shortcuts_g_prefix_logic():
    src = _shortcuts_js()
    assert "_gPressed" in src
    assert "setTimeout" in src


def test_keyboard_shortcuts_skip_input():
    src = _shortcuts_js()
    # Must skip when focused on input/textarea
    assert "INPUT" in src
    assert "TEXTAREA" in src


def test_keyboard_shortcuts_question_mark_help():
    src = _shortcuts_js()
    assert "key === '?'" in src
    assert "HermesShortcutsHelp" in src


# ── G5: shortcuts help overlay ────────────────────────────────────────────

def _help_js():
    return (COMP / "shortcuts_help_overlay.js").read_text(encoding="utf-8")


def test_shortcuts_help_overlay_exposes_global():
    src = _help_js()
    assert "window.HermesShortcutsHelp" in src


def test_shortcuts_help_overlay_show_hide():
    src = _help_js()
    assert "function show" in src
    assert "function hide" in src


def test_shortcuts_help_overlay_wcag():
    src = _help_js()
    # role=dialog can be set via setAttribute or inline HTML
    assert "dialog" in src and ("role" in src)
    assert "aria-modal" in src
    assert "aria-labelledby" in src


# ── G6: filter persistence ─────────────────────────────────────────────────

def _fp_js():
    return (COMP / "filter_persistence.js").read_text(encoding="utf-8")


def test_filter_persistence_exposes_global():
    src = _fp_js()
    assert "window.HermesFilterPersistence" in src


def test_filter_persistence_localStorage_namespace():
    src = _fp_js()
    assert "hermes.filters" in src


def test_filter_persistence_get_set_clear():
    src = _fp_js()
    assert "function get" in src
    assert "function set" in src
    assert "function clear" in src


# ── G7: app.js wiring ─────────────────────────────────────────────────────

def _app_js():
    return (DASH / "app.js").read_text(encoding="utf-8-sig")


def test_app_js_registers_hermes_commands():
    src = _app_js()
    assert "_registerHermesCommands" in src


def test_app_js_wires_filter_persistence():
    src = _app_js()
    assert "_wireFilterPersistence" in src


def test_app_js_nav_commands_count():
    src = _app_js()
    # At least 9 NAV_COMMANDS registered
    nav_entries = re.findall(r"id: 'go-", src)
    assert len(nav_entries) >= 9, f"Expected >=9 nav commands, got {len(nav_entries)}"


def test_app_js_g_prefix_shortcuts_count():
    src = _app_js()
    # At least 9 G-prefix shortcuts registered
    shortcut_entries = re.findall(r"\['g [a-z]'", src)
    assert len(shortcut_entries) >= 9, f"Expected >=9 g-prefix shortcuts, got {len(shortcut_entries)}"


def test_app_js_panic_button_quick_action():
    src = _app_js()
    assert "action-panic" in src
    assert "HermesPanicButton" in src


def test_app_js_cobaia_pause_resume_actions():
    src = _app_js()
    assert "action-cobaia-pause" in src
    assert "action-cobaia-resume" in src


def test_app_js_filter_persistence_restore_in_load_filters():
    src = _app_js()
    # Restore logic must be inside loadFilters
    load_filters_idx = src.find("async function loadFilters")
    assert load_filters_idx != -1
    restore_idx = src.find("HermesFilterPersistence", load_filters_idx)
    # Must appear BEFORE next function after loadFilters
    next_func_idx = src.find("async function loadProspects", load_filters_idx)
    assert restore_idx != -1 and restore_idx < next_func_idx, \
        "HermesFilterPersistence restore not found inside loadFilters"


def test_app_js_startpage_calls_register():
    src = _app_js()
    # _registerHermesCommands must appear inside checkAuth's startPage closure
    check_auth_idx = src.find("async function checkAuth")
    assert check_auth_idx != -1
    register_idx = src.find("_registerHermesCommands", check_auth_idx)
    # Must appear before startPage closes (roughly within 500 chars of startPage)
    start_page_idx = src.find("const startPage", check_auth_idx)
    assert register_idx != -1 and register_idx > start_page_idx, \
        "_registerHermesCommands not called from startPage"
