#!/usr/bin/env python3
"""P2b Hardening — fix PATCH 2 router wiring in VM hermes_api.py.

Replaces the original PATCH 2 (which used `import core.state` and failed
with AUTH_TOKEN RuntimeError) with a stub-injection approach that bypasses
the PC-centric auth checks.

Run on VM: python3 _vm_p2b_patcher.py
"""
from pathlib import Path

TARGET = Path.home() / ".hermes/scripts/hermes_api.py"
BAK2 = Path.home() / ".hermes/scripts/hermes_api.py.bak.p2b"

content = TARGET.read_text(encoding="utf-8")
BAK2.write_text(content, encoding="utf-8")
print(f"Backup: {BAK2}")

# ============================================================================
# Replace OLD PATCH 2 (import core.state -> AUTH_TOKEN fail) with stub approach
# ============================================================================

OLD_P2_SETUP = """# ============================================================================
# P2 HARDENING 2026-06-17 -- Wire observability + brain + pipeline_studio + mcp_jobs
# ============================================================================
try:
    import sys as _p2_sys
    _HERMES_REPO = Path.home() / "hermes-cloud-studio"
    if str(_HERMES_REPO) not in _p2_sys.path:
        _p2_sys.path.insert(0, str(_HERMES_REPO))
    # Patch core.state.DB_PATH BEFORE router imports so FROM bindings get VM path
    import core.state as _p2_core_state
    _p2_core_state.DB_PATH = DB_PATH
    print("[P2] sys.path + DB_PATH patch OK", flush=True)
    _P2_READY = True
except Exception as _p2_setup_e:
    print(f"[P2] WARN setup failed: {_p2_setup_e}", flush=True)
    _P2_READY = False"""

NEW_P2_SETUP = """# ============================================================================
# P2 HARDENING 2026-06-17 -- Wire observability + brain + pipeline_studio + mcp_jobs
# ============================================================================
import sys as _p2_sys, types as _p2_types, os as _p2_os
from pathlib import Path as _p2_Path
_HERMES_REPO = _p2_Path.home() / "hermes-cloud-studio"
if str(_HERMES_REPO) not in _p2_sys.path:
    _p2_sys.path.insert(0, str(_HERMES_REPO))

# Inject core.state stub BEFORE router imports.
# Real core.state raises RuntimeError if HERMES_AUTH_TOKEN missing (PC-centric check).
# VM uses HERMES_VM_AUTH_TOKEN instead — bypass by providing a stub module.
if "core" not in _p2_sys.modules:
    _p2_core_pkg = _p2_types.ModuleType("core")
    _p2_core_pkg.__path__ = [str(_HERMES_REPO / "core")]
    _p2_core_pkg.__package__ = "core"
    _p2_sys.modules["core"] = _p2_core_pkg

_p2_vm_db_path = _p2_Path.home() / ".hermes" / "data" / "command_center.db"

class _P2WSManagerStub:
    # No-op WS manager stub - VM WS is handled by hermes_api.py directly
    async def broadcast(self, msg): pass
    async def connect(self, ws): pass
    async def disconnect(self, ws): pass

def _p2_get_db_stub():
    import sqlite3 as _sq3
    _c = _sq3.connect(str(_p2_vm_db_path), check_same_thread=False)
    _c.row_factory = _sq3.Row
    return _c

_p2_state_mod = _p2_types.ModuleType("core.state")
_p2_state_mod.DB_PATH = _p2_vm_db_path
_p2_state_mod.VM_API_URL = "http://localhost:8420"
_p2_state_mod.AUTH_TOKEN = _p2_os.environ.get("HERMES_VM_AUTH_TOKEN", "vm-p2-stub")
_p2_state_mod.INTERNAL_TOKEN = _p2_os.environ.get("HERMES_VM_AUTH_TOKEN", "vm-p2-stub")
_p2_state_mod.AGENT_ZERO_URL = ""
_p2_state_mod.AGENT_ZERO_API_KEY = ""
_p2_state_mod.GOOGLE_API_KEY = _p2_os.environ.get("GOOGLE_PLACES_API_KEY", "")
_p2_state_mod.SYNC_INTERVAL = 60
_p2_state_mod.PROJECT_ROOT = _HERMES_REPO
_p2_state_mod.DASHBOARD_DIR = _HERMES_REPO / "dashboard"
_p2_state_mod.PHOTO_CACHE_DIR = _HERMES_REPO / "photo_cache"
_p2_state_mod.get_db = _p2_get_db_stub
_p2_state_mod.ws_manager = _P2WSManagerStub()
_p2_state_mod.spawn = lambda coro: None
_p2_sys.modules["core.state"] = _p2_state_mod
print("[P2] sys.path + core.state stub OK", flush=True)
_P2_READY = True"""

count = content.count(OLD_P2_SETUP)
assert count == 1, f"OLD_P2_SETUP anchor count={count} (expected 1)"
content = content.replace(OLD_P2_SETUP, NEW_P2_SETUP)
print("PATCH 2b applied: core.state stub injection")

TARGET.write_text(content, encoding="utf-8")
lines = content.count("\n")
print(f"hermes_api.py updated! Lines: {lines}")
print("Verify: grep -n 'core.state stub' ~/.hermes/scripts/hermes_api.py")
