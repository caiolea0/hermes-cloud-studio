"""F.1 — grep_frontend.py — extract endpoint consumption from dashboard/app.js.

Captures fetch() / api() helper / WS construction / event.type handlers.
Cross-references against backend broadcast events (channels/*.py + loops/*.py + api/*.py).

Outputs:
  .claude/frontend-gap/frontend-consumption.json
  .claude/frontend-gap/ws-events.json
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
APP_JS = ROOT / "dashboard" / "app.js"
INDEX_HTML = ROOT / "dashboard" / "index.html"
OUT_CONS = ROOT / ".claude" / "frontend-gap" / "frontend-consumption.json"
OUT_WS = ROOT / ".claude" / "frontend-gap" / "ws-events.json"

# Regex patterns for endpoint references in JS
# Group 1 = endpoint path (always starts with /api/ or /ws)
ENDPOINT_PATTERNS = [
    # api('/api/...', ...) or api(`/api/...`, ...)
    re.compile(r"""\bapi\(\s*['"`](/[^'"`]+)['"`]"""),
    # fetch('/api/...') with literal
    re.compile(r"""\bfetch\(\s*['"`](/(?:api|ws)/[^'"`]+)['"`]"""),
    # fetch(VM_API + '/api/...') or fetch(`${VM_API}/api/...`)
    re.compile(r"""\bfetch\(\s*(?:VM_API|API_BASE|API_URL|`\$\{[^}]+\})\s*\+?\s*['"`](/(?:api|ws|_bootstrap)/?[^'"`]*)['"`]"""),
    re.compile(r"""\bfetch\(\s*`\$\{[^}]+\}(/(?:api|ws)/[^`]+)`"""),
    # new WebSocket(...?token=)
    re.compile(r"""new\s+WebSocket\([^)]*?(/ws)\??"""),
]

# Path param normalization: ${id} → {id}, /:id → /{id}
PARAM_RE = re.compile(r"""\$\{[^}]+\}""")
COLON_PARAM_RE = re.compile(r"""/:([a-zA-Z_][a-zA-Z0-9_]*)""")
QUERY_RE = re.compile(r"""\?.*$""")


def normalize_endpoint(raw: str) -> str:
    """Trim query, normalize path params to {param} form."""
    s = QUERY_RE.sub("", raw)
    s = PARAM_RE.sub("{param}", s)
    s = COLON_PARAM_RE.sub(r"/{\1}", s)
    # Trim trailing slash unless root
    if len(s) > 1 and s.endswith("/"):
        s = s.rstrip("/")
    return s


def extract_js_consumption(path: Path) -> dict[str, list[dict]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        print(f"[grep_frontend] ERR cannot read {path}: {e}", file=sys.stderr)
        return {}
    consumed: dict[str, list[dict]] = defaultdict(list)
    for lineno, line in enumerate(lines, start=1):
        for pat in ENDPOINT_PATTERNS:
            for m in pat.finditer(line):
                raw = m.group(1)
                if not raw.startswith("/"):
                    continue
                ep = normalize_endpoint(raw)
                # Skip stylesheet/svg refs accidentally caught
                if ep.startswith(("/api/", "/ws", "/_bootstrap")):
                    consumed[ep].append({
                        "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                        "line": lineno,
                        "snippet": line.strip()[:120],
                    })
    return dict(consumed)


# WS event extraction
WS_HANDLER_RE = re.compile(r"""event\.type\s*===?\s*['"]([a-zA-Z0-9_]+)['"]""")
BROADCAST_RE = re.compile(r"""ws_manager\.broadcast\(\s*\{\s*['"]type['"]\s*:\s*['"]([a-zA-Z0-9_]+)['"]""")


def extract_ws_handlers(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return set()
    return set(WS_HANDLER_RE.findall(text))


BROADCAST_MULTILINE_RE = re.compile(
    r"""(?:ws_manager\.broadcast|self\._broadcast|_broadcast)\(\s*\{\s*[^}]*?["']type["']\s*:\s*["']([a-zA-Z0-9_]+)["']""",
    re.DOTALL,
)


def extract_ws_broadcasts(root: Path) -> dict[str, list[dict]]:
    """Scan PC .py files for broadcast({'type': ...}). Handles single + multiline dicts."""
    found: dict[str, list[dict]] = defaultdict(list)
    for py in root.rglob("*.py"):
        rel = py.relative_to(root)
        parts = set(rel.parts)
        # Skip noise dirs
        if parts & {".git", "node_modules", "__pycache__", "linkedin_data", "channels_data", "logs"}:
            continue
        # Limit to dirs that emit WS
        if not (parts & {"api", "loops", "channels", "core", "daemon", "vm_api", "vm_core"} or rel.name in ("server.py", "hermes_api_v2.py")):
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except Exception:
            continue
        # Single-line patterns (precise line numbers)
        for lineno, line in enumerate(text.splitlines(), start=1):
            for m in BROADCAST_RE.finditer(line):
                ev = m.group(1)
                found[ev].append({
                    "file": str(rel).replace("\\", "/"),
                    "line": lineno,
                    "snippet": line.strip()[:120],
                })
        # Multiline dict patterns (file-level scan; approximate line via offset)
        for m in BROADCAST_MULTILINE_RE.finditer(text):
            ev = m.group(1)
            lineno = text.count("\n", 0, m.start()) + 1
            existing = {(c["file"], c["line"]) for c in found[ev]}
            key = (str(rel).replace("\\", "/"), lineno)
            if key not in existing:
                found[ev].append({
                    "file": key[0],
                    "line": lineno,
                    "snippet": text.splitlines()[lineno - 1].strip()[:120] if lineno <= len(text.splitlines()) else "",
                })
    return dict(found)


def extract_hash_routes(path: Path) -> list[str]:
    """Scan index.html for data-page / hash route hints."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []
    return sorted(set(re.findall(r"""data-page=['"]([a-zA-Z0-9_-]+)['"]""", text)))


def main() -> int:
    t0 = time.time()
    consumed = extract_js_consumption(APP_JS)

    # Inline sanity: 8 known patterns MUST appear
    known_must = [
        "/api/prospects",
        "/api/dashboard",
        "/api/hermes/status",
        "/api/tunnel/status",
        "/api/audit/status",
        "/api/activities",
        "/api/tasks",
        "/ws",
    ]
    missing = [k for k in known_must if k not in consumed]
    if missing:
        print(f"[grep_frontend] SANITY FAIL — missing known consumed endpoints: {missing}", file=sys.stderr)
        sys.exit(2)

    handlers = extract_ws_handlers(APP_JS)
    broadcasts = extract_ws_broadcasts(ROOT)
    hash_routes = extract_hash_routes(INDEX_HTML)

    # Diff WS: emitted but never handled (orphan broadcast) vs handler with no emitter (dead handler)
    emitted = set(broadcasts.keys())
    orphan_broadcasts = sorted(emitted - handlers)
    dead_handlers = sorted(handlers - emitted)
    matched = sorted(emitted & handlers)

    OUT_CONS.parent.mkdir(parents=True, exist_ok=True)
    OUT_CONS.write_text(json.dumps({
        "generated_at": time.time(),
        "source": "dashboard/app.js",
        "total_endpoints": len(consumed),
        "total_calls": sum(len(v) for v in consumed.values()),
        "consumed": {k: v for k, v in sorted(consumed.items())},
        "hash_routes": hash_routes,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    OUT_WS.write_text(json.dumps({
        "generated_at": time.time(),
        "handlers_in_app_js": sorted(handlers),
        "broadcasts_in_backend": {k: v for k, v in sorted(broadcasts.items())},
        "matched": matched,
        "orphan_broadcasts": orphan_broadcasts,
        "dead_handlers": dead_handlers,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    dt = time.time() - t0
    print(f"[grep_frontend] {len(consumed)} endpoints, {sum(len(v) for v in consumed.values())} calls in {dt:.2f}s")
    print(f"[grep_frontend] WS handlers: {len(handlers)} | broadcasts: {len(emitted)} | matched: {len(matched)}")
    if orphan_broadcasts:
        print(f"[grep_frontend] orphan broadcasts (emitted, no handler): {orphan_broadcasts}")
    if dead_handlers:
        print(f"[grep_frontend] dead handlers (no emitter): {dead_handlers}")
    print(f"[grep_frontend] hash routes (dashboard pages): {hash_routes}")
    print(f"[grep_frontend] output: {OUT_CONS.name}, {OUT_WS.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
