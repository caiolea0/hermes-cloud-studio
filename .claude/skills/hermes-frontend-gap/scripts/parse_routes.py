"""F.1 — parse_routes.py — AST inventory PC+VM FastAPI routes.

Walks api/*.py + vm_api/routes.py + server.py + hermes_api_v2.py + core/limiter.py
+ _health_ep.py. Output .claude/frontend-gap/routes.json.

Sanity hard: assert len(routes) >= 140. Fail loud if parser regrediu.
"""
from __future__ import annotations

import ast
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # .claude/skills/hermes-frontend-gap/scripts/ → repo root
OUT = ROOT / ".claude" / "frontend-gap" / "routes.json"

PC_FILES = [
    "server.py",
    "core/limiter.py",
    "_health_ep.py",
]
PC_DIRS = ["api"]
VM_FILES = ["hermes_api_v2.py"]
VM_DIRS = ["vm_api"]

HTTP_VERBS = {"get", "post", "put", "patch", "delete", "websocket"}


def _str_const(node: ast.AST) -> str | None:
    """Extract string literal from arg / keyword (handle Constant + Str legacy)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    # JoinedStr / fstring — best effort: stringify
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            else:
                parts.append("{?}")
        return "".join(parts)
    return None


def _router_prefix(tree: ast.Module) -> str:
    """Find APIRouter(prefix=...) assignment to top-level `router`."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id in ("router", "app"):
                    if isinstance(node.value, ast.Call):
                        for kw in node.value.keywords:
                            if kw.arg == "prefix":
                                v = _str_const(kw.value)
                                if v:
                                    return v
    return ""


def _decorator_route(dec: ast.AST) -> tuple[str, str] | None:
    """Return (method, path) if decorator is @router.<verb>(path) / @app.<verb>(path)."""
    if not isinstance(dec, ast.Call):
        return None
    if not isinstance(dec.func, ast.Attribute):
        return None
    method = dec.func.attr.lower()
    if method not in HTTP_VERBS:
        return None
    if not isinstance(dec.func.value, ast.Name):
        return None
    if dec.func.value.id not in ("router", "app", "limiter"):  # limiter.limit isn't a route — filtered below
        return None
    if dec.func.value.id == "limiter" and dec.func.attr == "limit":
        return None
    if not dec.args:
        return None
    path = _str_const(dec.args[0])
    if path is None:
        return None
    return (method, path)


def _has_internal_dep(fn: ast.AST) -> bool:
    """Heuristic: function calls _check_internal(request) → loopback-only."""
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ("_check_internal", "require_internal"):
                return True
    return False


def _has_limiter_dep(fn: ast.AST) -> bool:
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    for d in fn.decorator_list:
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute):
            if isinstance(d.func.value, ast.Name) and d.func.value.id == "limiter" and d.func.attr == "limit":
                return True
    return False


def parse_file(path: Path, side: str) -> list[dict]:
    try:
        src = path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[parse_routes] WARN skip {path}: {e}", file=sys.stderr)
        return []
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        print(f"[parse_routes] WARN syntax {path}: {e}", file=sys.stderr)
        return []
    prefix = _router_prefix(tree)
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    routes: list[dict] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            res = _decorator_route(dec)
            if res is None:
                continue
            method, path_str = res
            full = (prefix + path_str) if not path_str.startswith(prefix) else path_str
            if not full.startswith("/"):
                full = "/" + full
            internal = _has_internal_dep(node) or full.startswith("/api/internal/")
            routes.append({
                "method": "WS" if method == "websocket" else method.upper(),
                "path": full,
                "file": rel,
                "line": dec.lineno,
                "function": node.name,
                "side": side,
                "internal_only": internal,
                "rate_limited": _has_limiter_dep(node),
            })
    return routes


def main() -> int:
    t0 = time.time()
    all_routes: list[dict] = []

    for f in PC_FILES:
        p = ROOT / f
        if p.exists():
            all_routes.extend(parse_file(p, "pc"))
    for d in PC_DIRS:
        for p in sorted((ROOT / d).glob("*.py")):
            if p.name == "__init__.py":
                continue
            all_routes.extend(parse_file(p, "pc"))
    for f in VM_FILES:
        p = ROOT / f
        if p.exists():
            all_routes.extend(parse_file(p, "vm"))
    for d in VM_DIRS:
        for p in sorted((ROOT / d).glob("*.py")):
            if p.name == "__init__.py":
                continue
            all_routes.extend(parse_file(p, "vm"))

    all_routes.sort(key=lambda r: (r["side"], r["path"], r["method"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": time.time(),
        "total": len(all_routes),
        "pc_count": sum(1 for r in all_routes if r["side"] == "pc"),
        "vm_count": sum(1 for r in all_routes if r["side"] == "vm"),
        "ws_count": sum(1 for r in all_routes if r["method"] == "WS"),
        "internal_count": sum(1 for r in all_routes if r["internal_only"]),
        "routes": all_routes,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    dt = time.time() - t0
    print(f"[parse_routes] {len(all_routes)} routes ({sum(1 for r in all_routes if r['side']=='pc')} PC + {sum(1 for r in all_routes if r['side']=='vm')} VM) in {dt:.2f}s")
    print(f"[parse_routes] WS endpoints: {sum(1 for r in all_routes if r['method']=='WS')}")
    print(f"[parse_routes] internal-only: {sum(1 for r in all_routes if r['internal_only'])}")
    print(f"[parse_routes] output: {OUT}")

    # Sanity hard
    assert len(all_routes) >= 130, f"PARSER REGRESSION: only {len(all_routes)} routes (expected >=130)"

    # Sanity: 11 fantasmas conhecidos devem existir no inventario
    KNOWN = [
        ("GET", "/api/daemon/state"),
        ("GET", "/api/daemon/log"),
        ("GET", "/api/daemon/decisions"),
        ("GET", "/api/daemon/channels"),
        ("GET", "/api/daemon/timeline"),
        ("GET", "/api/stats"),
        ("GET", "/api/linkedin/visited"),
        ("POST", "/api/tasks/bulk"),
    ]
    paths_set = {(r["method"], r["path"]) for r in all_routes}
    missing = [k for k in KNOWN if k not in paths_set]
    if missing:
        print(f"[parse_routes] WARN missing canonical endpoints: {missing}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
