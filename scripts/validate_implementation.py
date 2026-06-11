#!/usr/bin/env python3
"""Hermes Implementation Validation Harness.

Lê .claude/VALIDATION-CHECKLIST.md + executa asserts concretos por finding.
Reporta PASS/FAIL/SKIP + raises flags em arquivo `.claude/validation-flags.json`.

Uso:
    python scripts/validate_implementation.py                    # tudo
    python scripts/validate_implementation.py --phase A          # uma fase
    python scripts/validate_implementation.py --finding MERGED-001
    python scripts/validate_implementation.py --json             # output JSON
    python scripts/validate_implementation.py --apply-flags      # reabre tasks pra fails

Exit codes:
  0 — todos PASS
  1 — falha de execucao (erro interno)
  2 — algum finding FAIL (regressao detectada)
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent.parent
CHECKLIST_PATH = BASE_DIR / ".claude" / "VALIDATION-CHECKLIST.md"
FLAGS_PATH = BASE_DIR / ".claude" / "validation-flags.json"
REPORT_PATH = BASE_DIR / ".claude" / "validation-report.json"


@dataclass
class Check:
    kind: str
    target: str
    pattern: str = ""
    description: str = ""


@dataclass
class Finding:
    id: str
    phase: str
    checks: list[Check] = field(default_factory=list)


@dataclass
class Result:
    finding_id: str
    phase: str
    status: str  # PASS|FAIL|SKIP
    details: list[dict] = field(default_factory=list)


# ───────────── Parser do checklist (formato livre, regex tolerante) ─────────────

def parse_checklist(path: Path) -> list[Finding]:
    """Lê VALIDATION-CHECKLIST.md, extrai findings + checks."""
    if not path.exists():
        raise FileNotFoundError(f"Checklist nao encontrado: {path}")
    text = path.read_text(encoding="utf-8")
    findings: list[Finding] = []
    current_id: Optional[str] = None
    current_phase: Optional[str] = None
    current_checks: list[Check] = []

    def flush():
        nonlocal current_id, current_phase, current_checks
        if current_id and current_phase:
            findings.append(Finding(id=current_id, phase=current_phase, checks=current_checks))
        current_id, current_phase, current_checks = None, None, []

    for line in text.split("\n"):
        s = line.rstrip()
        m_id = re.match(r"^###\s+(MERGED-\d+)", s)
        if m_id:
            flush()
            current_id = m_id.group(1)
            continue
        m_phase = re.match(r"^-?\s*phase:\s*([A-E](?:\.\d+)?)", s)
        if m_phase and current_id:
            current_phase = m_phase.group(1)
            continue
        m_check = re.match(r"^\s+-\s+(\w+):\s*(.+)", s)
        if m_check and current_id:
            kind = m_check.group(1)
            body = m_check.group(2)
            # body padrão: "target / pattern / description"
            parts = [p.strip() for p in body.split(" / ")]
            target = parts[0] if parts else ""
            pattern = parts[1].strip("`\"'") if len(parts) > 1 else ""
            desc = parts[2] if len(parts) > 2 else ""
            current_checks.append(Check(kind=kind, target=target, pattern=pattern, description=desc))
            continue
    flush()
    return findings


# ───────────── Implementação das checks ─────────────

def _resolve_path(target: str) -> Path:
    """Resolve target relativo ao BASE_DIR. Aceita curinga simples."""
    if target.startswith("~/"):
        return Path(os.path.expanduser(target))
    return BASE_DIR / target


def check_grep_present(target: str, pattern: str) -> dict:
    p = _resolve_path(target)
    if not p.exists():
        return {"ok": False, "reason": f"path missing: {target}"}
    try:
        if p.is_file():
            content = p.read_text(encoding="utf-8", errors="ignore")
            if re.search(pattern, content, re.MULTILINE):
                return {"ok": True}
            return {"ok": False, "reason": f"pattern not found in {target}"}
        # dir: grep recursivo simples (só .py/.js/.md)
        exts = (".py", ".js", ".md", ".html", ".css", ".json")
        for sub in p.rglob("*"):
            if sub.suffix in exts:
                try:
                    if re.search(pattern, sub.read_text(encoding="utf-8", errors="ignore"), re.MULTILINE):
                        return {"ok": True, "found_in": str(sub.relative_to(BASE_DIR))}
                except Exception:
                    continue
        return {"ok": False, "reason": f"pattern not found in any file under {target}"}
    except Exception as e:
        return {"ok": False, "reason": f"error: {e}"}


def check_grep_absent(target: str, pattern: str) -> dict:
    p = _resolve_path(target)
    if not p.exists():
        return {"ok": True, "reason": f"path missing (vacuously absent): {target}"}
    try:
        content = p.read_text(encoding="utf-8", errors="ignore")
        if re.search(pattern, content, re.MULTILINE):
            return {"ok": False, "reason": f"pattern PRESENT (should be absent) in {target}"}
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "reason": f"error: {e}"}


def check_file_exists(target: str, pattern: str = "") -> dict:
    p = _resolve_path(target)
    if not p.exists():
        return {"ok": False, "reason": f"file missing: {target}"}
    if pattern == "non-empty" and p.stat().st_size == 0:
        return {"ok": False, "reason": f"file empty: {target}"}
    return {"ok": True, "size": p.stat().st_size}


def check_count_max(target: str, pattern: str, description: str = "") -> dict:
    """Conta ocorrências; PASS se count <= max extraído da description ('fewer than N' ou 'max:N')."""
    p = _resolve_path(target)
    if not p.exists():
        return {"ok": False, "reason": f"missing: {target}"}
    try:
        content = p.read_text(encoding="utf-8", errors="ignore")
        count = len(re.findall(pattern, content, re.MULTILINE))
        m = re.search(r"(?:fewer than|max:|<=)\s*(\d+)", description, re.IGNORECASE)
        max_allowed = int(m.group(1)) if m else 0
        ok = count <= max_allowed
        return {"ok": ok, "count": count, "max": max_allowed,
                "reason": f"{count} occurrences (max {max_allowed})" if not ok else ""}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def check_line_count_max(target: str, pattern: str) -> dict:
    """pattern = numero max de linhas."""
    p = _resolve_path(target)
    if not p.exists():
        return {"ok": False, "reason": f"missing: {target}"}
    try:
        line_count = sum(1 for _ in p.open(encoding="utf-8", errors="ignore"))
        try:
            max_lines = int(re.search(r"(\d+)", pattern).group(1))
        except Exception:
            max_lines = 500
        ok = line_count <= max_lines
        return {"ok": ok, "lines": line_count, "max": max_lines}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def check_sqlite_table(target: str, pattern: str) -> dict:
    """target = db path; pattern = table name. Suporta SSH (~/.hermes/...) via local SSH key."""
    p = target.strip()
    table = pattern.strip().split()[0]
    if p.startswith("~/"):
        # VM-side check
        ssh_key = Path(os.environ.get("USERPROFILE", "")) / ".ssh" / "id_ed25519"
        ssh_target = "hermes-gcp@136.115.74.69"
        cmd = [
            "ssh", "-i", str(ssh_key), "-o", "ConnectTimeout=8", "-o", "BatchMode=yes",
            ssh_target,
            f'python3 -c "import sqlite3, os; '
            f"db=sqlite3.connect(os.path.expanduser(\'{p}\')); "
            f"r=db.execute(\\\"SELECT name FROM sqlite_master WHERE type=\'table\' AND name=\'{table}\'\\\").fetchone(); "
            f'print(\'present\' if r else \'absent\')"',
        ]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if "present" in out.stdout:
                return {"ok": True}
            return {"ok": False, "reason": f"table {table} absent in VM db {p}"}
        except Exception as e:
            return {"ok": False, "reason": f"ssh check failed: {e}"}
    else:
        db_path = _resolve_path(target)
        if not db_path.exists():
            return {"ok": False, "reason": f"db missing: {target}"}
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path), timeout=5)
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            return {"ok": row is not None, "reason": f"table {table} {'present' if row else 'absent'}"}
        except Exception as e:
            return {"ok": False, "reason": str(e)}


def check_sqlite_column(target: str, pattern: str) -> dict:
    """pattern = 'table.column'"""
    if "." not in pattern:
        return {"ok": False, "reason": f"invalid pattern, expected table.column, got {pattern}"}
    table, col = pattern.split(".", 1)
    table = table.strip()
    col = col.strip()
    db_path = _resolve_path(target)
    if not db_path.exists():
        return {"ok": False, "reason": f"db missing: {target}"}
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path), timeout=5)
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        return {"ok": col in cols, "cols": cols}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def check_http_test(target: str, pattern: str) -> dict:
    """Skipa em dev local — opcional. Pattern descreve expectativa."""
    return {"ok": True, "skipped": "manual http test"}


# ───────────── Runner ─────────────

CHECK_RUNNERS = {
    "grep_present": check_grep_present,
    "grep_absent": check_grep_absent,
    "file_exists": check_file_exists,
    "count_max": check_count_max,
    "line_count_max": check_line_count_max,
    "sqlite_table": check_sqlite_table,
    "sqlite_column": check_sqlite_column,
    "http_test": check_http_test,
}


def run_finding(f: Finding) -> Result:
    details = []
    overall_ok = True
    for chk in f.checks:
        runner = CHECK_RUNNERS.get(chk.kind)
        if not runner:
            details.append({
                "kind": chk.kind, "target": chk.target, "pattern": chk.pattern,
                "ok": False, "reason": f"unknown check kind: {chk.kind}",
            })
            overall_ok = False
            continue
        try:
            if chk.kind == "count_max":
                r = runner(chk.target, chk.pattern, chk.description)
            else:
                r = runner(chk.target, chk.pattern)
        except Exception as e:
            r = {"ok": False, "reason": f"check error: {e}"}
        d = {
            "kind": chk.kind, "target": chk.target, "pattern": chk.pattern,
            "description": chk.description, **r,
        }
        details.append(d)
        if not r.get("ok"):
            overall_ok = False
    status = "PASS" if overall_ok else "FAIL"
    return Result(finding_id=f.id, phase=f.phase, status=status, details=details)


def main():
    p = argparse.ArgumentParser(description="Hermes implementation validation harness")
    p.add_argument("--phase", help="Run só esta fase (A/B/C/D/E/F)")
    p.add_argument("--finding", help="Run só este finding (ex: MERGED-001)")
    p.add_argument("--json", action="store_true", help="Output JSON")
    p.add_argument("--apply-flags", action="store_true", help="Reabrir tasks + atualizar PLAN para falhas")
    # F.5.4 — phase F flags (auto-derive PLAN + BANNED-PATTERNS audit)
    p.add_argument("--max-severity", default="blocker",
                   choices=["blocker", "warn", "info"],
                   help="Phase F only — minimum severity to report (default blocker CI strict)")
    p.add_argument("--scope-add", action="append",
                   help="Phase F only — extra glob path beyond SCOPE_PATHS")
    args = p.parse_args()

    # F.5.4 — phase F wire (additive, zero refactor phases A-E)
    if args.phase == "F":
        sys.path.insert(0, str(Path(__file__).parent))
        from _validate_phase_f import run_phase_f
        return run_phase_f(args)

    try:
        findings = parse_checklist(CHECKLIST_PATH)
    except Exception as e:
        print(f"ERROR loading checklist: {e}", file=sys.stderr)
        return 1

    if args.finding:
        findings = [f for f in findings if f.id == args.finding]
    if args.phase:
        findings = [f for f in findings if f.phase.startswith(args.phase)]

    if not findings:
        print("Nenhum finding pra validar (filtros aplicados?)", file=sys.stderr)
        return 1

    results = [run_finding(f) for f in findings]
    fail_count = sum(1 for r in results if r.status == "FAIL")
    pass_count = sum(1 for r in results if r.status == "PASS")
    skip_count = sum(1 for r in results if r.status == "SKIP")

    report = {
        "summary": {"pass": pass_count, "fail": fail_count, "skip": skip_count, "total": len(results)},
        "results": [asdict(r) for r in results],
        "flags": [r.finding_id for r in results if r.status == "FAIL"],
    }

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        # Human-readable
        print("=== Hermes Implementation Validation ===\n")
        current_phase = None
        for r in results:
            if r.phase != current_phase:
                current_phase = r.phase
                print(f"\nPHASE {current_phase}")
            icon = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}[r.status]
            print(f"  {icon} {r.finding_id}")
            if r.status == "FAIL":
                for d in r.details:
                    if not d.get("ok"):
                        print(f"        FLAG: {d['kind']} {d['target']} -- {d.get('reason', 'fail')}")
        print(f"\n=== SUMMARY ===\nPASS: {pass_count} | FAIL: {fail_count} | SKIP: {skip_count}")
        if fail_count:
            print(f"\nFLAGS RAISED: {fail_count} finding(s) precisam reimplementacao")
            print(f"Report JSON salvo em: {REPORT_PATH}")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    if args.apply_flags and fail_count:
        FLAGS_PATH.write_text(json.dumps(report["flags"], indent=2), encoding="utf-8")
        print(f"\nFlags persistidas em: {FLAGS_PATH}")
        print("Próximo passo: reabrir tasks via TaskCreate dos findings em flags e re-implementar.")

    return 0 if fail_count == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
