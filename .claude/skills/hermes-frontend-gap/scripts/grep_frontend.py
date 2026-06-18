"""F.1 — grep_frontend.py — extract endpoint consumption from dashboard/app.js + components/*.js + HTML inline scripts.

Captures fetch() / api() helper / local helper (_apiPost, apiGet, _apiCall) / WS construction / event.type handlers.
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
DASHBOARD = ROOT / "dashboard"
COMPONENTS_DIR = DASHBOARD / "components"
APP_JS = DASHBOARD / "app.js"
INDEX_HTML = DASHBOARD / "index.html"
OUT_CONS = ROOT / ".claude" / "frontend-gap" / "frontend-consumption.json"
OUT_WS = ROOT / ".claude" / "frontend-gap" / "ws-events.json"


def get_js_sources() -> list[Path]:
    """Return app.js + all components/*.js files."""
    sources = [APP_JS]
    if COMPONENTS_DIR.is_dir():
        sources.extend(sorted(COMPONENTS_DIR.glob("*.js")))
    return [s for s in sources if s.exists()]


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
    # Generic helper: any func call where /api/ string is 1st arg, OR 2nd arg after METHOD string
    # Catches: _apiPost('/api/...'), apiGet('/api/...'), _apiCall("GET", `/api/${expr}/path`), etc.
    # Note: [^'"`\n] (no ) exclusion) to allow template exprs like ${encodeURIComponent(x)}/path
    re.compile(r"""\b\w+\(\s*(?:['"][A-Z]+['"]\s*,\s*)?['"`](/api/[^'"`\n]+)['"`]"""),
]

# Inline <script> block detection (no src= attribute)
SCRIPT_BLOCK_RE = re.compile(
    r"<script(?![^>]*\bsrc\b)[^>]*>(.*?)</script>",
    re.DOTALL | re.IGNORECASE,
)

# Path param normalization: ${id} → {id}, /:id → /{id}
PARAM_RE = re.compile(r"""\$\{[^}]+\}""")
COLON_PARAM_RE = re.compile(r"""/:([a-zA-Z_][a-zA-Z0-9_]*)""")
QUERY_RE = re.compile(r"""\?.*$""")


def normalize_endpoint(raw: str) -> str:
    """Trim query, normalize path params to {param} form."""
    s = QUERY_RE.sub("", raw)
    s = PARAM_RE.sub("{param}", s)
    s = COLON_PARAM_RE.sub(r"/{\1}", s)
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
    seen: set[tuple[str, int]] = set()  # dedup (ep, lineno) per file
    for lineno, line in enumerate(lines, start=1):
        for pat in ENDPOINT_PATTERNS:
            for m in pat.finditer(line):
                raw = m.group(1)
                if not raw.startswith("/"):
                    continue
                ep = normalize_endpoint(raw)
                if not ep.startswith(("/api/", "/ws", "/_bootstrap")):
                    continue
                key = (ep, lineno)
                if key in seen:
                    continue
                seen.add(key)
                consumed[ep].append({
                    "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "line": lineno,
                    "snippet": line.strip()[:120],
                })
    return dict(consumed)


def extract_html_inline_scripts(html_path: Path) -> dict[str, list[dict]]:
    """Extract endpoint refs from <script>...</script> blocks in HTML files."""
    try:
        text = html_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[grep_frontend] ERR cannot read {html_path}: {e}", file=sys.stderr)
        return {}
    try:
        file_label = str(html_path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        file_label = html_path.name
    consumed: dict[str, list[dict]] = defaultdict(list)
    seen: set[tuple[str, int]] = set()
    for m in SCRIPT_BLOCK_RE.finditer(text):
        script_content = m.group(1)
        script_start_line = text.count("\n", 0, m.start(1)) + 1
        for i, line in enumerate(script_content.splitlines()):
            lineno = script_start_line + i
            for pat in ENDPOINT_PATTERNS:
                for pm in pat.finditer(line):
                    raw = pm.group(1)
                    if not raw.startswith("/"):
                        continue
                    ep = normalize_endpoint(raw)
                    if not ep.startswith(("/api/", "/ws", "/_bootstrap")):
                        continue
                    key = (ep, lineno)
                    if key in seen:
                        continue
                    seen.add(key)
                    consumed[ep].append({
                        "file": file_label,
                        "line": lineno,
                        "snippet": line.strip()[:120],
                    })
    return dict(consumed)


def merge_consumption(source_dicts: list[dict[str, list[dict]]]) -> dict[str, list[dict]]:
    """Merge endpoint consumption dicts from multiple sources."""
    merged: dict[str, list[dict]] = defaultdict(list)
    for source in source_dicts:
        for endpoint, calls in source.items():
            merged[endpoint].extend(calls)
    return dict(merged)


# WS event extraction
WS_HANDLER_RE = re.compile(r"""event\.type\s*===?\s*['"]([a-zA-Z0-9_]+)['"]""")
BROADCAST_RE = re.compile(r"""ws_manager\.broadcast\(\s*\{\s*['"]type['"]\s*:\s*['"]([a-zA-Z0-9_]+)['"]""")


def extract_ws_handlers(paths: list[Path]) -> set[str]:
    """Extract WS event.type handler strings from all given JS files."""
    handlers: set[str] = set()
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        handlers.update(WS_HANDLER_RE.findall(text))
    return handlers


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
        if parts & {".git", "node_modules", "__pycache__", "linkedin_data", "channels_data", "logs"}:
            continue
        if not (parts & {"api", "loops", "channels", "core", "daemon", "vm_api", "vm_core"} or rel.name in ("server.py", "hermes_api_v2.py")):
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for m in BROADCAST_RE.finditer(line):
                ev = m.group(1)
                found[ev].append({
                    "file": str(rel).replace("\\", "/"),
                    "line": lineno,
                    "snippet": line.strip()[:120],
                })
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

    js_sources = get_js_sources()

    source_dicts = [extract_js_consumption(src) for src in js_sources]
    if INDEX_HTML.exists():
        source_dicts.append(extract_html_inline_scripts(INDEX_HTML))

    consumed = merge_consumption(source_dicts)

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

    handlers = extract_ws_handlers(js_sources)
    broadcasts = extract_ws_broadcasts(ROOT)
    hash_routes = extract_hash_routes(INDEX_HTML)

    emitted = set(broadcasts.keys())
    orphan_broadcasts = sorted(emitted - handlers)
    dead_handlers = sorted(handlers - emitted)
    matched = sorted(emitted & handlers)

    source_files = [str(s.relative_to(ROOT)).replace("\\", "/") for s in js_sources]
    if INDEX_HTML.exists():
        source_files.append(str(INDEX_HTML.relative_to(ROOT)).replace("\\", "/"))

    OUT_CONS.parent.mkdir(parents=True, exist_ok=True)
    OUT_CONS.write_text(json.dumps({
        "generated_at": time.time(),
        "sources": source_files,
        "sources_count": len(source_files),
        "total_endpoints": len(consumed),
        "total_calls": sum(len(v) for v in consumed.values()),
        "consumed": {k: v for k, v in sorted(consumed.items())},
        "hash_routes": hash_routes,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    OUT_WS.write_text(json.dumps({
        "generated_at": time.time(),
        "handlers_in_frontend": sorted(handlers),
        "broadcasts_in_backend": {k: v for k, v in sorted(broadcasts.items())},
        "matched": matched,
        "orphan_broadcasts": orphan_broadcasts,
        "dead_handlers": dead_handlers,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    dt = time.time() - t0
    print(f"[grep_frontend] sources: {len(js_sources)} JS files + HTML inline ({len(source_files)} total)")
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
