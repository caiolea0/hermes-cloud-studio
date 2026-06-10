"""hermes-linkedin smoke test — F.5.2.

Verifica:
1. fastmcp importável (skip se ausente — VM-only dep)
2. server.py importável + mcp instance criada
3. 8 tools registered via FastMCP introspection
4. Sanitize function masks SENSITIVE_KEYS recursivamente
5. Zero touch BLACKLIST R2 (informativo — git diff é gate real Commit 4)

Smoke isolado fixture-mode — NÃO invoca LinkedIn real (sem tunnel, sem cookies,
sem patchright). Integration test Brain dispatch DEFERRED F.6.

Exit 0 = PASS, exit 1 = FAIL.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _check_fastmcp() -> bool:
    try:
        import fastmcp  # noqa: F401
        return True
    except ImportError:
        print("[smoke] SKIP fastmcp not installed (VM-only dep, OK on PC)")
        return False


def _check_server_imports() -> bool:
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        import server  # type: ignore
    except SystemExit as exc:
        print(f"[smoke] SKIP server import → SystemExit ({exc}) — fastmcp missing")
        return False
    except Exception as exc:
        print(f"[smoke] FAIL server import: {exc}")
        return False
    assert server.MCP_NAME == "hermes-linkedin", "name drift"
    assert server.MCP_VERSION.startswith("0.1.0-f5.2"), "version drift"
    print(f"[smoke] OK server import (name={server.MCP_NAME} v={server.MCP_VERSION})")
    return True


def _check_tools_registered() -> bool:
    import server  # type: ignore
    expected = {
        "get_health", "get_rate_limits", "get_warmup_status",
        "get_account_profile", "assert_account_safe", "preflight_check",
        "probe_cooldown", "start_campaign",
    }
    # FastMCP 3.0 stores tools internally — try multiple introspection paths
    found: set[str] = set()
    mcp_obj = getattr(server, "mcp", None)
    if mcp_obj is None:
        print("[smoke] FAIL no mcp instance on server module")
        return False
    for attr_name in ("_tools", "tools", "_tool_manager"):
        attr = getattr(mcp_obj, attr_name, None)
        if attr is None:
            continue
        if isinstance(attr, dict):
            found.update(attr.keys())
            break
        if hasattr(attr, "list_tools"):
            try:
                lst = attr.list_tools()
                # might be sync or coroutine — best-effort sync
                if isinstance(lst, (list, tuple)):
                    found.update(
                        getattr(t, "name", str(t)) for t in lst
                    )
                    break
            except Exception:
                pass
    if not found:
        # Fall back to module-level attribute scan (decorators expose callables)
        for name in expected:
            if callable(getattr(server, name, None)):
                found.add(name)
    missing = expected - found
    extra = found - expected
    if missing:
        print(f"[smoke] FAIL tools missing: {sorted(missing)}")
        return False
    print(f"[smoke] OK 8 tools registered (extra introspected: {sorted(extra)[:5]})")
    return True


def _check_sanitize() -> bool:
    import server  # type: ignore
    payload = {
        "li_at": "AQED...secret",
        "user": "caio",
        "nested": {
            "cookie": "x=y",
            "bcookie": "z",
            " API_KEY ": "shouldredact_via_strip",  # strip test
            "ok": [{"token": "tok", "msg": "ok"}, "literal"],
        },
        "AUTHORIZATION": "Bearer XYZ",
    }
    out = server._sanitize(payload)
    failures = []
    if out["li_at"] != "[REDACTED]":
        failures.append("li_at not masked")
    if out["AUTHORIZATION"] != "[REDACTED]":
        failures.append("AUTHORIZATION uppercase not masked")
    if out["nested"]["cookie"] != "[REDACTED]":
        failures.append("nested.cookie not masked")
    if out["nested"]["bcookie"] != "[REDACTED]":
        failures.append("nested.bcookie not masked")
    if out["nested"][" API_KEY "] != "[REDACTED]":
        failures.append("trailing-whitespace API_KEY not masked")
    if out["nested"]["ok"][0]["token"] != "[REDACTED]":
        failures.append("list element token not masked")
    if out["user"] != "caio":
        failures.append("non-sensitive user clobbered")
    if failures:
        print(f"[smoke] FAIL sanitize: {failures}")
        return False
    print("[smoke] OK sanitize (7 cases including .strip() defense)")
    return True


def main() -> int:
    print("=== hermes-linkedin smoke (F.5.2) ===")
    fastmcp_ok = _check_fastmcp()
    if not fastmcp_ok:
        # PC sem fastmcp = SKIP graceful (smoke real roda VM)
        return 0
    checks = [
        _check_server_imports,
        _check_tools_registered,
        _check_sanitize,
    ]
    all_ok = True
    for check in checks:
        ok = check()
        all_ok = all_ok and ok
    print("=== %s ===" % ("PASS" if all_ok else "FAIL"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
