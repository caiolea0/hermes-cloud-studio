#!/usr/bin/env python3
"""P2c Hardening -- add perf_middleware install to P2 wire block."""
from pathlib import Path

TARGET = Path.home() / ".hermes/scripts/hermes_api.py"

content = TARGET.read_text(encoding="utf-8")

OLD = """        print(f"[P2] WARN mcp_jobs: {_p2_e}", flush=True)


if __name__ == "__main__":"""

NEW = """        print(f"[P2] WARN mcp_jobs: {_p2_e}", flush=True)

    try:
        from core.observability import install_perf_middleware as _p2_install_perf
        _p2_install_perf(app)
        print("[P2] perf_middleware installed OK", flush=True)
    except Exception as _p2_e:
        print(f"[P2] WARN perf_middleware: {_p2_e}", flush=True)


if __name__ == "__main__":"""

count = content.count(OLD)
assert count == 1, f"Anchor count={count} (expected 1)"
content = content.replace(OLD, NEW)

TARGET.write_text(content, encoding="utf-8")
print(f"PATCH 2c applied: perf_middleware install. Lines: {content.count(chr(10))}")
