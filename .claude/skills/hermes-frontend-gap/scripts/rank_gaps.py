"""F.1 — rank_gaps.py — diff routes vs consumed, rank, render FRONTEND-GAP.md.

Reads .claude/frontend-gap/{routes,frontend-consumption,ws-events}.json.
Writes .claude/FRONTEND-GAP.md + .claude/frontend-gap/diff-vs-known.md.

Sanity asserts (hard fail = abort, preserve old FRONTEND-GAP.md):
  - known phantoms not consumed AND not in backend routes → AssertionError (route deleted)
  - routes total >= 130
  - consumed endpoints >= 30
  - total elapsed <90s
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
ROUTES_JSON = ROOT / ".claude" / "frontend-gap" / "routes.json"
CONS_JSON = ROOT / ".claude" / "frontend-gap" / "frontend-consumption.json"
WS_JSON = ROOT / ".claude" / "frontend-gap" / "ws-events.json"
OUT_MD = ROOT / ".claude" / "FRONTEND-GAP.md"
DIFF_MD = ROOT / ".claude" / "frontend-gap" / "diff-vs-known.md"
BAK_MD = ROOT / ".claude" / "frontend-gap" / "FRONTEND-GAP.previous.md"

PARAM_BRACE_RE = re.compile(r"""\{[^}]+\}""")

# Known orphan phantoms — backend routes with no frontend UI.
# daemon/* removed: consumed by F.2 Mission Control (CHAPTER CLOSED).
# Update this set when a route gets a UI (remove) or a new orphan is identified (add).
KNOWN_PHANTOMS = {
    "/api/prospects/{prospect_id}/resolve-conflict",
    "/api/tasks/bulk",
    "/api/stats",
    "/api/linkedin/visited",
    "/api/linkedin/comment/edit",
    "/api/linkedin/comment/delete",
    "/api/agent-zero/status",
}


def normalize_for_match(p: str) -> str:
    """Replace any {var} or {param} with '*' so backend and frontend variants match."""
    return PARAM_BRACE_RE.sub("*", p).rstrip("/")


def chapter_for(path: str, method: str) -> str:
    p = path.lower()
    if "/api/daemon/" in p or p.endswith("/api/stats"):
        return "F.2"
    if "/api/lab/" in p or "/lab/" in p:
        return "F.3"
    if "/api/skills/proposals" in p or "/api/skill-proposals" in p:
        return "F.4"
    if "/api/mcp/" in p or "/api/gateway/" in p:
        return "F.5"
    if "/api/agent-zero" in p or "/api/brain/" in p or "/api/claude" in p:
        return "F.6"
    if "/api/cobaia" in p or "/api/linkedin/visited" in p or "/api/linkedin/comment" in p:
        return "F.7"
    if "/api/observability" in p:
        return "F.8"
    if "/api/pipeline-studio" in p or "/api/pipeline-builder" in p:
        return "F.9"
    if "resolve-conflict" in p or "/api/prospects/" in p and method in ("PUT", "DELETE", "POST"):
        return "F.6"
    if "/api/tasks/bulk" in p:
        return "F.6"
    if "/api/linkedin" in p:
        return "F.3"
    return "F.6"


def cli_replaced_for(path: str, method: str) -> str:
    p = path.lower()
    table = [
        ("/api/daemon/log", "ssh vm 'tail -f /var/hermes/daemon.log'"),
        ("/api/daemon/state", "ssh vm 'cat ~/.hermes/data/daemon_state.json'"),
        ("/api/daemon/timeline", "ssh vm 'sqlite3 ~/.hermes/data/command_center.db \"SELECT * FROM daemon_decisions ORDER BY ts DESC LIMIT 50\"'"),
        ("/api/daemon/decisions", "idem timeline + filter ação"),
        ("/api/daemon/channels", "ssh vm 'cat ~/.hermes/data/channels_state.json'"),
        ("/api/linkedin/visited", "ssh vm 'sqlite3 linkedin_data/rate_limits.db \"SELECT * FROM linkedin_visited\"'"),
        ("/api/linkedin/comment", "curl + edição manual via DOM extension"),
        ("/api/stats", "ssh vm + agregação SQL manual"),
        ("/api/tasks/bulk", "loop curl por task"),
        ("/api/prospects/{id}/resolve-conflict", "UPDATE manual hermes_local.db"),
        ("/api/agent-zero/status", "curl + parse JSON em PowerShell"),
        ("/api/agent-zero/chat", "curl POST + parse stream manual"),
        ("/api/lab/", "ssh vm + xvfb-run python3 -m linkedin.lab.lab_runner"),
        ("/api/skills/proposals", "ssh vm + cat ~/.hermes/skills/*.yaml + diff manual"),
    ]
    for needle, cmd in table:
        if needle in p:
            return cmd
    if method == "GET":
        return f"curl {path}"
    return f"curl -X {method} {path}"


def owner_pain_for(path: str, method: str) -> int:
    """Heuristic 1-5. Higher = more painful CLI dependency today."""
    p = path.lower()
    if "log" in p or "tail" in p or "timeline" in p:
        return 5  # live tail without UI = constant ssh
    if "/daemon/" in p:
        return 5
    if "linkedin/visited" in p or "linkedin/comment" in p:
        return 4
    if "resolve-conflict" in p:
        return 4
    if "/agent-zero" in p or "/brain" in p:
        return 4
    if "/tasks/bulk" in p or "/api/stats" in p:
        return 3
    if "/lab/" in p:
        return 3
    if method in ("POST", "PUT", "DELETE", "PATCH"):
        return 3
    return 2


def ws_needed_for(path: str, method: str) -> bool:
    p = path.lower()
    return any(needle in p for needle in (
        "/daemon/timeline", "/daemon/log", "/daemon/state", "/daemon/decisions",
        "/daemon/channels", "/lab/", "/agent-zero/chat", "/brain", "/observability",
    ))


def ux_blurb(path: str) -> str:
    p = path.lower()
    if "/daemon/broadcast" in p:
        return "Trigger broadcast WS arbitrário (devtool) — escondido pra owner, expose só em modo debug"
    if "/daemon/pause" in p:
        return "Botão pause daemon (timeout N min) no header Mission Control"
    if "/daemon/resume" in p:
        return "Botão resume daemon junto do pause"
    if "/audit/batch" in p:
        return "Botão 'rodar auditoria em lote' na lista de prospects qualificados"
    if "/api/daemon/state" in p:
        return "Snapshot daemon (estado, energia, último heartbeat) na Mission Control"
    if "/daemon/log" in p:
        return "Live tail logs daemon — substitui SSH tail -f"
    if "/daemon/timeline" in p:
        return "Timeline visual de decisões/eventos 24h"
    if "/daemon/decisions" in p:
        return "Auditoria de decisões P1-P7 (Brain F.6 grava aqui)"
    if "/daemon/channels" in p:
        return "Estado por canal (linkedin/email/scraper/audit)"
    if "/stats" in p:
        return "Counters agregados (prospects, deals, replies) — KPIs dashboard"
    if "/linkedin/visited" in p:
        return "Lista de perfis já visitados (cooldown debug)"
    if "/linkedin/comment" in p:
        return "Edit/delete comentários LinkedIn sem abrir browser"
    if "/tasks/bulk" in p:
        return "Bulk update tasks (priorize/cancele 20 de uma vez)"
    if "/resolve-conflict" in p:
        return "Botão dismiss conflict no row de prospect"
    if "/agent-zero/status" in p:
        return "Status Agent Zero (model, context_id, last_invoked)"
    if "/agent-zero/chat" in p:
        return "Chat AI no dashboard — substitui CLI Agent Zero"
    return path


def _detect_phase_baseline() -> str:
    """Grep PLAN.md for the last 'F.x CHAPTER CLOSED' marker."""
    plan = ROOT / ".claude" / "PLAN.md"
    try:
        text = plan.read_text(encoding="utf-8")
    except Exception:
        return "F.1"
    matches = re.findall(r"(F\.\d+)\s+CHAPTER CLOSED", text)
    if matches:
        return f"post {matches[-1]}"
    return "F.1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank frontend gaps vs backend routes.")
    parser.add_argument(
        "--phase-baseline", default=None,
        help="Override phase baseline label. If omitted, auto-detect from PLAN.md last CHAPTER CLOSED.",
    )
    args = parser.parse_args()

    t0 = time.time()
    if not ROUTES_JSON.exists() or not CONS_JSON.exists() or not WS_JSON.exists():
        print(f"[rank_gaps] FAIL — missing inputs. Run parse_routes.py + grep_frontend.py first.", file=sys.stderr)
        return 2

    routes_blob = json.loads(ROUTES_JSON.read_text(encoding="utf-8"))
    cons_blob = json.loads(CONS_JSON.read_text(encoding="utf-8"))
    ws_blob = json.loads(WS_JSON.read_text(encoding="utf-8"))

    routes = routes_blob["routes"]
    consumed = cons_blob["consumed"]
    consumed_norm = {normalize_for_match(k) for k in consumed.keys()}

    # Diff
    orphans = []
    consumed_routes = []
    for r in routes:
        if r["internal_only"]:
            continue
        key = normalize_for_match(r["path"])
        # Match: route consumed if its normalized form OR any path prefix appears
        is_consumed = key in consumed_norm
        if not is_consumed:
            # Fuzzy: consumer might call /api/foo when backend exposes /api/foo/{id}
            for ck in consumed_norm:
                if ck == key:
                    is_consumed = True
                    break
                if key.startswith(ck + "/") or ck.startswith(key + "/"):
                    # only count when they share verb-base; keep strict to avoid false positives
                    continue
        if is_consumed:
            consumed_routes.append(r)
        else:
            orphans.append(r)

    # Rank orphans by owner_pain (desc), then by method (POST/DELETE before GET), then path
    def rank_key(r):
        pain = owner_pain_for(r["path"], r["method"])
        method_weight = 0 if r["method"] in ("POST", "PUT", "DELETE", "PATCH") else 1
        return (-pain, method_weight, r["path"])

    orphans.sort(key=rank_key)
    top10 = orphans[:10]

    # Sanity hard: known phantoms must be somewhere (orphan OR consumed).
    # If missing from BOTH → backend route deleted unexpectedly → raise.
    orphan_paths = {normalize_for_match(o["path"]) for o in orphans}
    phantoms_normalized = {normalize_for_match(p) for p in KNOWN_PHANTOMS}
    missing_phantoms = phantoms_normalized - orphan_paths
    if missing_phantoms:
        # Distinguish: consumed (frontend built UI) vs truly gone (route deleted)
        consumed_norm_set = {normalize_for_match(k) for k in consumed.keys()}
        progress_consumed = missing_phantoms & consumed_norm_set
        truly_missing = missing_phantoms - consumed_norm_set
        if progress_consumed:
            print(
                f"[rank_gaps] PROGRESS: {len(progress_consumed)} known phantoms now consumed by frontend: {sorted(progress_consumed)}",
                file=sys.stderr,
            )
        if truly_missing:
            raise AssertionError(
                f"[rank_gaps] SANITY FAIL — {len(truly_missing)} known phantom(s) vanished from both orphans AND consumed:\n"
                f"  missing: {sorted(truly_missing)}\n"
                f"  Possible causes: backend route deleted, path changed, or parser regression.\n"
                f"  Fix: verify route still exists; if removed intentionally, update KNOWN_PHANTOMS."
            )

    # Backup existing FRONTEND-GAP.md before overwrite
    if OUT_MD.exists():
        BAK_MD.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OUT_MD, BAK_MD)

    # Build diff-vs-known.md
    diff_lines = ["# FRONTEND-GAP diff vs previous run", ""]
    if BAK_MD.exists():
        try:
            prev = BAK_MD.read_text(encoding="utf-8")
            prev_orphans = set(re.findall(r"\| `([A-Z]+)` \| `(/[^\s|`]+)`", prev))
            curr_orphans = {(o["method"], o["path"]) for o in orphans}
            became_consumed = sorted(prev_orphans - curr_orphans)
            regressed = sorted(curr_orphans - prev_orphans)
            diff_lines.append(f"## Orphans → Consumed (vitórias)\n")
            for m, p in became_consumed:
                diff_lines.append(f"- ✅ `{m} {p}`")
            diff_lines.append(f"\n## New orphans (regressões / backend novo sem UI)\n")
            for m, p in regressed:
                diff_lines.append(f"- 🆕 `{m} {p}`")
        except Exception as e:
            diff_lines.append(f"_(diff parse failed: {e})_")
    else:
        diff_lines.append("_(first execution — no previous baseline)_")
    DIFF_MD.parent.mkdir(parents=True, exist_ok=True)
    DIFF_MD.write_text("\n".join(diff_lines) + "\n", encoding="utf-8")

    # Render FRONTEND-GAP.md
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    phase_baseline = args.phase_baseline or _detect_phase_baseline()
    pc_total = routes_blob["pc_count"]
    vm_total = routes_blob["vm_count"]
    total = routes_blob["total"]
    internal_total = routes_blob["internal_count"]
    consumed_total = len(consumed_routes)
    orphan_total = len(orphans)
    consumption_pct = (consumed_total / max(1, total - internal_total)) * 100

    md = []
    md.append(f"# FRONTEND-GAP — Backend↔Frontend audit")
    md.append("")
    md.append(f"- **last_updated**: {now}")
    md.append(f"- **phase_baseline**: {phase_baseline}")
    md.append(f"- **routes_total**: {total} ({pc_total} PC + {vm_total} VM, {internal_total} internal-only excluded)")
    md.append(f"- **consumed**: {consumed_total} ({consumption_pct:.1f}% of public)")
    md.append(f"- **orphans**: {orphan_total}")
    md.append(f"- **top_10_priority**: see §4")
    md.append("")
    md.append("> Auditoria determinística cruzando AST routes FastAPI com consumo `dashboard/app.js`.")
    md.append("> Re-rodável: `python .claude/skills/hermes-frontend-gap/scripts/rank_gaps.py`.")
    md.append("> Re-execução ao fechar QUALQUER chapter F.2-F.9 é termômetro UX (GUARDRAILS §F.1).")
    md.append("")

    # §1 Inventário
    md.append("## §1 Inventário routes (PC + VM)")
    md.append("")
    md.append(f"- Total: **{total}** rotas FastAPI ({pc_total} PC, {vm_total} VM)")
    md.append(f"- WS endpoints: {routes_blob['ws_count']}")
    md.append(f"- Internal-only (loopback): {internal_total} (excluídos do gap)")
    md.append("")
    by_file = defaultdict(int)
    for r in routes:
        by_file[r["file"]] += 1
    md.append("| Arquivo | Rotas |")
    md.append("|---|---|")
    for f, n in sorted(by_file.items(), key=lambda kv: -kv[1]):
        md.append(f"| `{f}` | {n} |")
    md.append("")

    # §2 Mapa consumo dashboard
    md.append("## §2 Mapa consumo `dashboard/app.js`")
    md.append("")
    md.append(f"- Endpoints únicos consumidos: **{consumed_total}**")
    md.append(f"- Total fetch/api calls: {cons_blob['total_calls']}")
    md.append(f"- Hash routes (páginas SPA): {', '.join(cons_blob['hash_routes'])}")
    md.append("")
    md.append("| Endpoint | Chamadas | Locais (file:line) |")
    md.append("|---|---|---|")
    top_consumed = sorted(consumed.items(), key=lambda kv: -len(kv[1]))[:20]
    for ep, calls in top_consumed:
        locs = ", ".join(f"{c['file'].split('/')[-1]}:{c['line']}" for c in calls[:3])
        md.append(f"| `{ep}` | {len(calls)} | {locs} |")
    md.append("")

    # §3 Órfãos
    md.append(f"## §3 Órfãos — {orphan_total} endpoints sem UI")
    md.append("")
    md.append("Backend expõe mas dashboard não consome. Owner depende de CLI/curl/SSH.")
    md.append("")
    md.append("| Method | Path | Side | File | Auth |")
    md.append("|---|---|---|---|---|")
    for o in orphans:
        auth = "rate-limited" if o["rate_limited"] else "token"
        md.append(f"| `{o['method']}` | `{o['path']}` | {o['side']} | `{o['file']}:{o['line']}` | {auth} |")
    md.append("")

    # §4 TOP 10
    md.append("## §4 TOP 10 priorizado")
    md.append("")
    md.append("Ranking: owner_pain_score (5=tail/decisions live) → method (write > read) → path.")
    md.append("")
    md.append("| Rank | Endpoint | Método | Side | Chapter destino | WS needed | CLI hoje | Owner pain (1-5) |")
    md.append("|---|---|---|---|---|---|---|---|")
    for i, o in enumerate(top10, start=1):
        ch = chapter_for(o["path"], o["method"])
        ws = "✅" if ws_needed_for(o["path"], o["method"]) else "—"
        cli = cli_replaced_for(o["path"], o["method"])
        pain = owner_pain_for(o["path"], o["method"])
        md.append(f"| {i} | `{o['path']}` | `{o['method']}` | {o['side']} | {ch} | {ws} | `{cli[:60]}` | {pain} |")
    md.append("")
    md.append("**Justificativa por linha**:")
    md.append("")
    for i, o in enumerate(top10, start=1):
        md.append(f"{i}. **`{o['method']} {o['path']}`** — {ux_blurb(o['path'])}")
    md.append("")

    # §5 Quick Wins UX
    md.append("## §5 Quick Wins UX (1 fetch + 1 toast / 1 botão)")
    md.append("")
    md.append("Implementação <1h cada — alta razão impacto/esforço:")
    md.append("")
    qw_targets = [
        ("/api/prospects/{id}/resolve-conflict", "POST", "Botão 'resolver conflito' no row do prospect quando `conflict_at IS NOT NULL`"),
        ("/api/stats", "GET", "Card de KPIs no topo do dashboard (prospects total, deals won, replies 24h)"),
        ("/api/daemon/state", "GET", "Tile snapshot Mission Control — polling 5s ou WS sub"),
        ("/api/tasks/bulk", "POST", "Toolbar com 'priorize selecionados' / 'cancelar selecionados' em /tasks"),
        ("/api/agent-zero/status", "GET", "Badge no header com modelo/context_id ativo"),
    ]
    matched_qw = []
    paths_in_orphans = {(o["method"], normalize_for_match(o["path"])) for o in orphans}
    for path, method, desc in qw_targets:
        key = (method, normalize_for_match(path))
        if key in paths_in_orphans:
            matched_qw.append((path, method, desc))
    for path, method, desc in matched_qw:
        md.append(f"- `{method} {path}` — {desc}")
    md.append("")

    # §6 Mission Control endpoints (WS-needed)
    md.append("## §6 Mission Control endpoints (WS broadcasts + streaming)")
    md.append("")
    md.append("Endpoints que F.2 deve consumir com canais WS dedicados:")
    md.append("")
    md.append("| Endpoint | WS event sugerido | Comentário |")
    md.append("|---|---|---|")
    mc_targets = [
        ("/api/daemon/state", "daemon_state", "Já emitido (sync.py + daemon/orchestrator.py)"),
        ("/api/daemon/timeline", "daemon_timeline_update", "Broadcast inexistente — criar em loops/sync.py"),
        ("/api/daemon/decisions", "decision", "Já emitido (daemon orchestrator log_decision)"),
        ("/api/daemon/channels", "channel_update", "Já emitido (daemon orchestrator)"),
        ("/api/daemon/log", "daemon_log_line", "Broadcast inexistente — rolling buffer 500 lines F.2"),
        ("/api/lab/runs/{id}/screenshot", "lab_screenshot_new", "Polling 2s ou WS push (F.3)"),
        ("/api/brain/chat", "brain_token / brain_action", "Stream tokens + tool events (F.6)"),
    ]
    matched_events = set(ws_blob.get("matched", []))
    for ep, event, comment in mc_targets:
        status = "✅ ativo" if event in matched_events else "🔨 a criar"
        md.append(f"| `{ep}` | `{event}` | {comment} ({status}) |")
    md.append("")
    md.append("### WS events backend vs handlers `dashboard/app.js`")
    md.append("")
    md.append(f"- Handlers em `app.js`: {len(ws_blob['handlers_in_app_js'])} ({', '.join(ws_blob['handlers_in_app_js'])})")
    md.append(f"- Broadcasts no backend: {len(ws_blob['broadcasts_in_backend'])} ({', '.join(sorted(ws_blob['broadcasts_in_backend']))})")
    md.append(f"- ✅ Matched (emitido + handler): {', '.join(ws_blob['matched'])}")
    if ws_blob["orphan_broadcasts"]:
        md.append(f"- ⚠️ Orphan broadcasts (emitido sem handler): {', '.join(ws_blob['orphan_broadcasts'])}")
    if ws_blob["dead_handlers"]:
        md.append(f"- 🪦 Dead handlers (handler sem emitter local): {', '.join(ws_blob['dead_handlers'])}")
    md.append("")

    md.append("---")
    md.append("")
    md.append("Gerado por `.claude/skills/hermes-frontend-gap/scripts/rank_gaps.py`.")
    md.append(f"Reproduzir: `python .claude/skills/hermes-frontend-gap/scripts/{{parse_routes,grep_frontend,rank_gaps}}.py`")
    md.append("")

    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    dt = time.time() - t0
    print(f"[rank_gaps] orphans={orphan_total} consumed={consumed_total} top10={len(top10)} in {dt:.2f}s")
    print(f"[rank_gaps] consumption: {consumption_pct:.1f}% of {total - internal_total} public endpoints")
    print(f"[rank_gaps] output: {OUT_MD}")

    # Hard sanity — restore from backup if regression detected
    try:
        assert total >= 130, f"routes regression: only {total} routes (expected >=130)"
        assert consumed_total >= 30, f"consumption regression: only {consumed_total} consumed (expected >=30)"
        assert dt < 90, f"timeout: {dt:.1f}s exceeds 90s limit"
    except AssertionError:
        if BAK_MD.exists():
            shutil.copy2(BAK_MD, OUT_MD)
            print(f"[rank_gaps] RESTORED previous FRONTEND-GAP.md from {BAK_MD}", file=sys.stderr)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
