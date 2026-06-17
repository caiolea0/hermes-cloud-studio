#!/usr/bin/env python3
"""P2 Hardening — patch hermes_api.py on VM.

Applies two patches:
  PATCH 1 (lifespan): migrations + perf_flush_loop before yield + teardown after yield.
  PATCH 2 (module): sys.path + DB_PATH patch + 4 router include_routers before main.

Run on VM: python3 _vm_p2_patcher.py
"""
from pathlib import Path

TARGET = Path.home() / ".hermes/scripts/hermes_api.py"
BAK = Path.home() / ".hermes/scripts/hermes_api.py.bak.p2"

content = TARGET.read_text(encoding="utf-8")

# Backup original
BAK.write_text(content, encoding="utf-8")
print(f"Backup: {BAK}")

# ============================================================================
# PATCH 1 — lifespan: migrations + perf_flush_loop
# ============================================================================
OLD_YIELD = """        print(f'[startup] orphan cleanup skipped: {_e}')
    yield"""

# Guard: ensure asyncio is imported (VM hermes_api.py should have it, but be safe)
NEW_YIELD = """        print(f'[startup] orphan cleanup skipped: {_e}')
    # P2 HARDENING 2026-06-17 -- Auto-apply F.6+F.8+F.9+F.7 migrations VM-side
    try:
        import asyncio as _p2_asyncio
        import sqlite3 as _p2_sqlite3
        _HERMES_REPO_MIG = Path.home() / "hermes-cloud-studio" / "migrations"
        _MIGRATIONS_VM = [
            "2026_06_brain_runs_decisions.sql",
            "2026_06_brain_runs_owner_comment.sql",
            "2026_06_observability.sql",
            "2026_06_pipeline_studio.sql",
            "2026_06_pipeline_clone_ab_compare.sql",
            "2026_06_cobaia_autotune_triggers.sql",
        ]
        _db_mig = _p2_sqlite3.connect(str(DB_PATH))
        for _m in _MIGRATIONS_VM:
            _mpath = _HERMES_REPO_MIG / _m
            if _mpath.exists():
                try:
                    _db_mig.executescript(_mpath.read_text(encoding="utf-8"))
                    _db_mig.commit()
                    print(f"[P2] migration applied: {_m}", flush=True)
                except Exception as _me:
                    print(f"[P2] migration warn {_m}: {_me}", flush=True)
        _db_mig.close()
    except Exception as _pe:
        print(f"[P2] migrations setup failed: {_pe}", flush=True)
    # P2 HARDENING -- perf_flush_loop (importable after sys.path wire at module level)
    _p2_perf_task = None
    try:
        import asyncio as _asyncio_p2
        from core.observability import perf_flush_loop as _p2_perf_flush
        _p2_perf_task = _asyncio_p2.ensure_future(_p2_perf_flush(DB_PATH))
        print("[P2] perf_flush_loop started", flush=True)
    except Exception as _pfl_e:
        print(f"[P2] perf_flush_loop WARN: {_pfl_e}", flush=True)
    yield
    if _p2_perf_task:
        try:
            _p2_perf_task.cancel()
        except Exception:
            pass"""

count = content.count(OLD_YIELD)
assert count == 1, f"PATCH 1 anchor count={count} (expected 1)"
content = content.replace(OLD_YIELD, NEW_YIELD)
print("PATCH 1 applied: lifespan migrations + perf_flush_loop")

# ============================================================================
# PATCH 2 — module level: sys.path + DB_PATH + 4 router wires
# ============================================================================
OLD_MAIN = """if __name__ == "__main__":
    import uvicorn"""

NEW_MAIN = """# ============================================================================
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
    _P2_READY = False

if _P2_READY:
    try:
        from api.observability import router as _p2_obs_router
        app.include_router(_p2_obs_router)
        print("[P2] observability_router wired OK", flush=True)
    except Exception as _p2_e:
        print(f"[P2] WARN observability: {_p2_e}", flush=True)

    try:
        from api.brain import router as _p2_brain_router
        app.include_router(_p2_brain_router)
        print("[P2] brain_router wired OK", flush=True)
    except Exception as _p2_e:
        print(f"[P2] WARN brain: {_p2_e}", flush=True)

    try:
        from api.pipeline_studio import router as _p2_pipeline_router
        app.include_router(_p2_pipeline_router)
        print("[P2] pipeline_studio_router wired OK", flush=True)
    except Exception as _p2_e:
        print(f"[P2] WARN pipeline_studio: {_p2_e}", flush=True)

    try:
        from vm_api.mcp_jobs import router as _p2_mcp_jobs_router
        app.include_router(_p2_mcp_jobs_router)
        print("[P2] mcp_jobs_router wired OK", flush=True)
    except Exception as _p2_e:
        print(f"[P2] WARN mcp_jobs: {_p2_e}", flush=True)


if __name__ == "__main__":
    import uvicorn"""

count = content.count(OLD_MAIN)
assert count == 1, f"PATCH 2 anchor count={count} (expected 1)"
content = content.replace(OLD_MAIN, NEW_MAIN)
print("PATCH 2 applied: sys.path + DB_PATH + 4 router wires")

# Write back
TARGET.write_text(content, encoding="utf-8")
lines = content.count("\n")
print(f"hermes_api.py patched! Lines: {lines}")
print("Verify with: grep -n 'P2 HARDENING' ~/.hermes/scripts/hermes_api.py")
