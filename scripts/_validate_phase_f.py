"""F.5.4 Phase F validation — MCP HARD REQUIREMENTS + BANNED-PATTERNS audit.

S1 hard requirement enforcement layer (MCP-ENFORCEMENT-STRATEGY section 5.3).

D1 BANNED-PATTERNS.json per-chapter scoped (NAO regex flat global).
D2 REQUIRED_PER_PHASE auto-derive PLAN.md done_criteria + seed required_by_dc[]
    (single source of truth, cache invalidation por mtime hash).
D3 Severity 3-tier BLOCKER + WARN + INFO + flag --max-severity (default blocker CI).
D5 Scope: mcps/* + brain/* + skills/* + api/agent_zero.py + hermes_api_v2.py + vm_api/*
    (NAO codebase completo — lint world = noise).

Sync only (no asyncio — gotcha mem_mq7i9caw asyncio.gather TypeError swallow).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PLAN_PATH = ROOT / ".claude" / "PLAN.md"
SEED_PATH = ROOT / ".claude" / "mcp_registry_seed.json"
PATTERNS_PATH = ROOT / ".claude" / "MCP-BANNED-PATTERNS.json"
CACHE_PATH = ROOT / ".claude" / "_validate_required_cache.json"

# D5 — master scope allowlist (owner pode expandir via --scope-add)
SCOPE_PATHS = [
    "mcps/",
    "brain/",
    "skills/",
    "api/agent_zero.py",
    "hermes_api_v2.py",
    "vm_api/",
]

SEVERITY_RANK = {"INFO": 0, "WARN": 1, "BLOCKER": 2}
_SCOPED_EXTS = (".py", ".yaml", ".yml", ".json")


def get_required_per_phase() -> dict[str, list[dict]]:
    """D2 auto-derive REQUIRED_PER_PHASE PLAN.md done_criteria + seed cross-check.

    Cache invalidation: hash mtime PLAN.md + SEED. Cached em
    .claude/_validate_required_cache.json (gitignored .claude/_*.json).

    Returns:
        {chapter: [{requirement, source}]} ex: {"F.7": [...]}.
    """
    plan_mtime = PLAN_PATH.stat().st_mtime_ns if PLAN_PATH.exists() else 0
    seed_mtime = SEED_PATH.stat().st_mtime_ns if SEED_PATH.exists() else 0
    plan_hash = hashlib.sha256(f"{plan_mtime}:{seed_mtime}".encode()).hexdigest()[:16]

    if CACHE_PATH.exists():
        try:
            cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            if cache.get("plan_hash") == plan_hash:
                return cache["data"]
        except (json.JSONDecodeError, KeyError):
            pass  # cache corrupted, rebuild

    result: dict[str, list[dict]] = {}

    # Parse PLAN.md "MCP HARD REQUIREMENTS (F.X)" sections
    # F.5.5 D0 fix: capture lines pos-heading ate proxima section heading.
    # Negative lookahead (?!\+?\*\*) at line start STOPS quando proxima line
    # eh section heading (`**...` ou `+**...`). Post-process dropa blanks,
    # non-bullet lines, headers, e "Decisoes Cristalizadas" bullets `**D\d+`.
    if PLAN_PATH.exists():
        plan = PLAN_PATH.read_text(encoding="utf-8")
        pattern = (
            r"\*\*[^*\n]*MCP HARD REQUIREMENTS \(F\.(\d+(?:\.\d+)?)\)\*\*[^\n]*\n"
            r"((?:(?!\+?\*\*)[^\n]*\n)+)"
        )
        d_bullet_re = re.compile(r"^\*\*D\d+")
        for match in re.finditer(pattern, plan):
            chapter = f"F.{match.group(1)}"
            entries: list[dict] = []
            for raw_line in match.group(2).split("\n"):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                # D0 filter: PLAN.md diff-style `+- bullet` → strip leading +
                if stripped.startswith("+"):
                    stripped = stripped[1:].lstrip()
                if not stripped or stripped[0] not in "-*+":
                    continue
                body = stripped.lstrip("-+* ").strip()
                if not body:
                    continue
                # D0 filter: "Decisoes Cristalizadas" bullets (**D0**, **D1**, ...)
                if d_bullet_re.match(body):
                    continue
                entries.append({"requirement": body, "source": "PLAN.md"})
            if entries:
                result.setdefault(chapter, []).extend(entries)

    # Cross-check seed required_by_dc[]
    if SEED_PATH.exists():
        try:
            seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
            rows = seed.get("rows", seed if isinstance(seed, list) else [])
            for row in rows:
                for dc in row.get("required_by_dc", []) or []:
                    result.setdefault(dc, []).append({
                        "requirement": f"mcp.{row['server']} disponivel (tools: "
                                       f"{', '.join(row.get('tools', [])[:3])}{'...' if len(row.get('tools', [])) > 3 else ''})",
                        "source": "mcp_registry_seed.json",
                    })
        except (json.JSONDecodeError, KeyError):
            pass

    CACHE_PATH.write_text(
        json.dumps({"plan_hash": plan_hash, "data": result}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return result


def _walk_scope_paths(scope_strings: list[str]) -> list[Path]:
    """Walk paths em scope_strings. Cada string pode ser dir (brain/) ou file
    (api/agent_zero.py). Filter __pycache__ + dedupe.
    """
    files: set[Path] = set()
    for raw in scope_strings:
        rel = raw.strip().rstrip("/")
        if not rel:
            continue
        target = ROOT / rel
        if target.is_file():
            files.add(target)
        elif target.is_dir():
            for ext in _SCOPED_EXTS:
                files.update(target.rglob(f"*{ext}"))
    return sorted(f for f in files if "__pycache__" not in str(f) and ".git" not in str(f).split("\\"))


def audit_banned_patterns(extra_globs: list[str] | None = None) -> list[dict]:
    """D1 per-chapter scoped + D5 scope strict.

    Returns:
        List of violations {chapter, file, line, pattern, reason, severity, matched}.
    """
    if not PATTERNS_PATH.exists():
        print(f"WARN: {PATTERNS_PATH.name} not found, skipping banned-patterns audit", file=sys.stderr)
        return []

    try:
        patterns_doc = json.loads(PATTERNS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: {PATTERNS_PATH.name} invalid JSON: {exc}", file=sys.stderr)
        return []

    violations: list[dict] = []
    extra = extra_globs or []

    for chapter, pattern_list in patterns_doc.items():
        if chapter.startswith("_"):
            continue  # skip _meta
        if not isinstance(pattern_list, list):
            continue
        for p in pattern_list:
            if "scope" not in p or not p["scope"]:
                print(f"ERROR: pattern '{p.get('pattern')}' in chapter {chapter} missing 'scope' field (D5)", file=sys.stderr)
                continue
            scope_strings = [s.strip() for s in str(p["scope"]).split(",") if s.strip()]
            scope_strings.extend(extra)
            files = _walk_scope_paths(scope_strings)
            try:
                compiled = re.compile(p["pattern"])
            except re.error as exc:
                print(f"ERROR: pattern '{p['pattern']}' invalid regex: {exc}", file=sys.stderr)
                continue
            for f in files:
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                except (OSError, UnicodeDecodeError):
                    continue
                for line_no, line in enumerate(content.splitlines(), 1):
                    if compiled.search(line):
                        try:
                            rel = f.relative_to(ROOT)
                        except ValueError:
                            rel = f
                        violations.append({
                            "chapter": chapter,
                            "file": str(rel).replace("\\", "/"),
                            "line": line_no,
                            "pattern": p["pattern"],
                            "reason": p["reason"],
                            "severity": p["severity"].upper(),
                            "matched": line.strip()[:120],
                        })
    return violations


def run_phase_f(args: argparse.Namespace) -> int:
    """Phase F entry point. Wire em scripts/validate_implementation.py.

    Returns exit code: 0 (no BLOCKERS) | 1 (BLOCKER detected).
    """
    max_sev = (getattr(args, "max_severity", None) or "blocker").upper()
    if max_sev not in SEVERITY_RANK:
        print(f"ERROR: invalid --max-severity '{max_sev}' (use blocker|warn|info)", file=sys.stderr)
        return 1
    max_sev_rank = SEVERITY_RANK[max_sev]

    required = get_required_per_phase()
    req_count = sum(len(v) for v in required.values())
    print(f"Phase F: parsed {req_count} MCP HARD REQUIREMENTS from {len(required)} chapters")

    extra_globs = getattr(args, "scope_add", None) or []
    violations = audit_banned_patterns(extra_globs)

    by_sev: dict[str, list[dict]] = {"BLOCKER": [], "WARN": [], "INFO": []}
    for v in violations:
        by_sev.setdefault(v["severity"], []).append(v)

    has_blocker = False
    for sev in ("BLOCKER", "WARN", "INFO"):
        sev_rank = SEVERITY_RANK[sev]
        if sev_rank < max_sev_rank:
            continue
        icon = {"BLOCKER": "[BLOCKER]", "WARN": "[WARN]", "INFO": "[INFO]"}[sev]
        stream = sys.stderr if sev != "INFO" else sys.stdout
        for v in by_sev[sev]:
            print(f"{icon} [{v['chapter']}] {v['file']}:{v['line']} -- {v['reason']}", file=stream)
            print(f"           pattern: {v['pattern']}", file=stream)
            print(f"           matched: {v['matched']}", file=stream)
            if sev == "BLOCKER":
                has_blocker = True

    total_b = len(by_sev["BLOCKER"])
    total_w = len(by_sev["WARN"])
    total_i = len(by_sev["INFO"])
    print(f"\n=== PHASE F SUMMARY ===")
    print(f"PASS: 0 | FAIL: {1 if has_blocker else 0} | SKIP: 0")
    print(f"Phase F: BLOCKER={total_b} WARN={total_w} INFO={total_i} (max-severity={max_sev})")
    if extra_globs:
        print(f"Phase F: --scope-add {extra_globs}")

    return 1 if has_blocker else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hermes phase F validation (MCP HARD + BANNED-PATTERNS)")
    parser.add_argument("--max-severity", default="blocker",
                        choices=["blocker", "warn", "info"],
                        help="Minimum severity to report (default blocker for CI strict)")
    parser.add_argument("--scope-add", action="append",
                        help="Extra glob path beyond SCOPE_PATHS (F.future expansion)")
    args = parser.parse_args()
    sys.exit(run_phase_f(args))
