# ROLLBACK FASE F — Procedures por Chapter

> **Documento operacional** — procedimentos determinísticos de rollback por chapter F.1-F.9.
> Owner solo. Trigger: regressão detectada (validate_implementation.py cai abaixo de 20/22 PASS, daemon trava, broadcast WS quebra, LinkedIn ban risk, ou crash em produção).
> **Princípio**: rollback SEMPRE restaura baseline 20/22 PASS Fases A-E + LinkedIn lab healthy + Caio account untouched.
> **Persistência obrigatória pós-rollback**: Telegram alert + `memory_save` tipo `rollback` + `mark_chapter "Phase F.X rolled back — <root cause>"`.

---

## Convenções globais

### Pré-flight (TODO rollback)
```bash
# 1. Snapshot estado atual antes de qualquer ação destrutiva
git status
git stash push -m "rollback-FASE-F-$(date +%Y%m%d-%H%M%S)-WIP"
git log --oneline -20 > /tmp/rollback-log-snapshot.txt

# 2. Backup DB (PC + VM se aplicável)
cp data/hermes.db data/hermes.db.rollback-$(date +%Y%m%d-%H%M%S).bak
ssh vm "cp /var/hermes/hermes.db /var/hermes/hermes.db.rollback-$(date +%Y%m%d-%H%M%S).bak"

# 3. Capturar logs últimos 5min pra forensics
tail -n 500 logs/hermes.log > /tmp/rollback-pre-log.txt
ssh vm "journalctl -u hermes-vm --since '5 min ago' --no-pager" > /tmp/rollback-pre-vm.txt
```

### Tags git canônicas (criadas no INÍCIO de cada chapter)
- `f1-baseline` — antes da primeira mudança F.1
- `f2-baseline` — antes da primeira mudança F.2
- ... até `f9-baseline`
- `fX-rollback-YYYYMMDD-HHMMSS` — marcador pós-rollback

### Validate gate (pós-rollback OBRIGATÓRIO)
```bash
python scripts/validate_implementation.py --phase A B C D E --json | \
  python -c "import sys,json; r=json.load(sys.stdin); \
    assert r['summary']['pass']==20 and r['summary']['fail']==2, \
    f'ROLLBACK FALHOU — esperado 20/22 PASS, atual {r[\"summary\"]}'; \
    print('OK baseline 20/22 restaurado')"
```

### Persistência pós-rollback (TODA execução)
```bash
# 1. Telegram alert
curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
  -d chat_id="${TG_OWNER_CHAT}" \
  -d parse_mode=Markdown \
  -d text="*ROLLBACK F.X executado* %0A Root cause: \`<causa>\` %0A Baseline restaurado: 20/22 PASS %0A Tag: \`fX-rollback-$(date +%Y%m%d-%H%M%S)\`"

# 2. memory_save tipo rollback (via agentmemory MCP)
#   content: "hermes F.X rollback — <root cause em 1-2 frases> — baseline restaurado"
#   concepts: [hermes, phase-fX, rollback, <subsistema afetado>]

# 3. mark_chapter "Phase F.X rolled back — <root cause>"

# 4. git commit registrando rollback
git tag "f${X}-rollback-$(date +%Y%m%d-%H%M%S)"
git commit --allow-empty -m "rollback(fase-f.${X}): <root cause> — baseline 20/22 restaurado"
```

### Quando NÃO fazer rollback (escalation)
- Regressão A (auth fail-closed): NÃO rollback parcial. **Parar Hermes inteiro** (`systemctl stop hermes-pc hermes-vm`), avisar owner, investigar antes de qualquer git revert.
- Caio account em risco (ban LinkedIn): pause ALL loops imediatamente (`POST /api/daemon/pause`), rollback completo até f1-baseline ou anterior, NÃO retomar até auditoria stealth manual.
- DB corruption: NÃO sobrescrever .bak. Restaurar do backup mais recente PRÉ-fase corrompida, exportar snapshot diff pra investigação forense.

---

## F.1 — Backend↔Frontend Gap Audit

### Escopo do rollback
F.1 é puramente análise (`.claude/FRONTEND-GAP.md` + skill `.claude/skills/hermes-frontend-gap/` + slash command). **Zero código MADURO tocado**. Rollback é trivial.

### Trigger de rollback
- Parser AST gerou inventário < 120 rotas (parser bugado)
- Sanity check dos 11 fantasmas falhou (algum não apareceu em ORPHAN/STUB-ONLY)
- FRONTEND-GAP.md corrompido (encoding, markdown malformado)

### Procedure
```bash
# 1. Pré-flight (global acima)

# 2. Git revert seletivo — apenas .claude/ tocado em F.1
git revert --no-commit f1-baseline..HEAD -- \
  .claude/FRONTEND-GAP.md \
  .claude/skills/hermes-frontend-gap/ \
  .claude/commands/hermes-frontend-gap.md \
  .claude/frontend-gap/

# OU rollback duro se commits limpos
git reset --hard f1-baseline

# 3. Remover diretórios criados
rm -rf .claude/skills/hermes-frontend-gap/
rm -rf .claude/frontend-gap/
rm -f .claude/commands/hermes-frontend-gap.md
rm -f .claude/FRONTEND-GAP.md

# 4. Reverter settings.local.json permissions adicionadas
git checkout f1-baseline -- .claude/settings.local.json

# 5. NÃO há systemd stop (zero código produção tocado)
# 6. NÃO há DROP TABLE (zero migration)
# 7. NÃO há feature flag (skill desativada por ausência de arquivo)
```

### Validate
```bash
# Baseline 20/22 (esperado já que zero código produção tocado — sanity check trivial)
python scripts/validate_implementation.py --phase A B C D E --json | \
  python -c "import sys,json; r=json.load(sys.stdin); \
    assert r['summary']['pass']==20 and r['summary']['fail']==2; print('OK 20/22')"

# Skill removida do registry
test ! -f .claude/skills/hermes-frontend-gap/SKILL.md && echo "OK skill removida"
test ! -f .claude/FRONTEND-GAP.md && echo "OK report removido"
```

### Persistência
- Telegram: `ROLLBACK F.1 — parser AST inventário inválido (<X rotas) — baseline restaurado`
- memory_save: `hermes F.1 rollback — parser falhou sanity check 11 fantasmas, refazer com regex tolerante a path params`
- mark_chapter: `Phase F.1 rolled back — parser bug`

---

## F.2 — Mission Control Real-Time + Design System Polish

### Escopo do rollback
F.2 toca `dashboard/app.js` (+~800 linhas), `dashboard/styles.css` (design tokens), `loops/sync.py` (WS broadcast subsystem health — MADURO), `api/daemon.py` (novos endpoints `/api/daemon/subsystems` + pause/resume — MADURO). **Risco MÉDIO** — regressão A (WS auth) ou D (loops resilience) possível.

### Trigger de rollback
- WS broadcasts causam loop crash (logger.exception em loops/sync.py)
- `/api/daemon/subsystems/{name}/pause` corrompe runtime_state
- Dashboard quebra renderização (XSS regression em telemetria nova)
- validate_implementation.py --phase A B D cai abaixo do baseline
- Owner reporta UI travada / WS desconectado > 60s

### Procedure
```bash
# 1. Pré-flight (global acima)

# 2. Feature flag OFF imediato (se chapter ativou flag)
# Em config.py: HERMES_FEATURE_MISSION_CONTROL_V2 = False
python -c "
import json
with open('config/feature_flags.json', 'r+') as f:
    d = json.load(f)
    d['mission_control_v2'] = False
    d['ws_subsystem_broadcast'] = False
    f.seek(0); json.dump(d, f, indent=2); f.truncate()
print('flags OFF')
"

# 3. Stop services pra revert seguro
sudo systemctl stop hermes-pc
ssh vm "sudo systemctl stop hermes-vm"

# 4. Git revert por arquivo (preservar progresso F.1)
git checkout f2-baseline -- \
  dashboard/app.js \
  dashboard/styles.css \
  dashboard/components/ \
  loops/sync.py \
  api/daemon.py \
  core/state.py  # se tocado pra subsystem registry

# OU revert range commits F.2
git revert --no-commit f2-baseline..HEAD
git commit -m "rollback(fase-f.2): revert mission control v2"

# 5. SE migration aplicada (subsystem_pause_state table)
sqlite3 data/hermes.db "ALTER TABLE runtime_state RENAME TO runtime_state_f2_rollback_$(date +%s)"
sqlite3 data/hermes.db < migrations/rollback/f2-down.sql
# OU se table nova isolada:
sqlite3 data/hermes.db "DROP TABLE IF EXISTS subsystem_pause_state"

# Backup já está em data/hermes.db.rollback-*.bak

# 6. Restart services
sudo systemctl start hermes-pc
ssh vm "sudo systemctl start hermes-vm"
sleep 5

# 7. Health check
curl -fsS http://localhost:8000/health || echo "PC DOWN"
curl -fsS http://localhost:8001/health || echo "VM tunnel DOWN"
```

### Validate
```bash
# A baseline preservado
python scripts/validate_implementation.py --phase A B D --json | \
  python -c "import sys,json; r=json.load(sys.stdin); \
    assert r['summary']['fail']<=2, f'FAIL: {r[\"summary\"]}'; print('OK A B D')"

# WS handshake funciona
python -c "
import asyncio, websockets, json, os
async def t():
    async with websockets.connect(f'ws://localhost:8000/ws?token={os.environ[\"HERMES_WS_TOKEN\"]}') as ws:
        await ws.send(json.dumps({'type':'ping'}))
        r = await asyncio.wait_for(ws.recv(), 5)
        print('OK WS:', r[:80])
asyncio.run(t())
"

# Loops todos UP
curl -s http://localhost:8000/api/daemon/state | python -c "import sys,json; d=json.load(sys.stdin); assert d.get('healthy'), d; print('OK daemon healthy')"
```

### Persistência
- Telegram: `ROLLBACK F.2 — <WS crash | UI broken | A regression> — Mission Control v1 restaurado`
- memory_save: `hermes F.2 rollback — <root cause concreto> — separar UI polish (CSS tokens isolado) de WS broadcast (loops MADURO) em retry`
- mark_chapter: `Phase F.2 rolled back — <root cause>`

---

## F.3 — Lab Cockpit

### Escopo do rollback
Nova página `dashboard/lab` + novos endpoints `/api/lab/runs|start|{run_id}/artifacts` + wrapper Python `linkedin/lab/lab_runner.py` (MADURO — refatorado mas core preservado). **Risco MÉDIO-BAIXO** — isolado em namespace lab, NÃO toca conta Caio.

### Trigger de rollback
- Lab runs corrompem fingerprint baseline (overwrite acidental)
- `/api/lab/start` spawn process que não morre (zombie patchright)
- UI lab vaza screenshots de outras runs (path traversal)
- Disco enche com artifacts (sem rotation policy)

### Procedure
```bash
# 1. Pré-flight (global)

# 2. KILL processos lab vivos
pkill -f "lab_runner.py" || true
pkill -f "patchright.*lab" || true
ssh vm "pkill -f 'lab_runner.py' || true"

# 3. Feature flag OFF
python -c "
import json
with open('config/feature_flags.json', 'r+') as f:
    d = json.load(f); d['lab_cockpit_ui'] = False
    f.seek(0); json.dump(d, f, indent=2); f.truncate()
"

# 4. Stop services
sudo systemctl stop hermes-pc

# 5. Revert código
git checkout f3-baseline -- \
  dashboard/lab.html \
  dashboard/app.js \
  api/lab.py \
  linkedin/lab/lab_runner.py
rm -rf dashboard/components/lab/

# 6. Migration rollback (lab_runs table)
sqlite3 data/hermes.db "DROP TABLE IF EXISTS lab_runs"
sqlite3 data/hermes.db "DROP TABLE IF EXISTS lab_artifacts_index"

# 7. Artifacts NÃO deletar (forensics) — apenas mover
mv artifacts/lab artifacts/lab.rollback-$(date +%Y%m%d-%H%M%S)/

# 8. Restart
sudo systemctl start hermes-pc
sleep 3
```

### Validate
```bash
python scripts/validate_implementation.py --phase A B C D E --json | \
  python -c "import sys,json; r=json.load(sys.stdin); \
    assert r['summary']['pass']==20; print('OK 20/22')"

# /api/lab/* não existem mais (404)
test "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/lab/runs)" = "404" && echo "OK lab endpoints removidos"

# CLI lab_runner ainda roda (não regrediu shell tool)
python linkedin/lab/lab_runner.py --dry-run && echo "OK CLI lab preservado"
```

### Persistência
- Telegram: `ROLLBACK F.3 — <zombie process | artifact leak | disk full> — lab cockpit removido, CLI preservado`
- memory_save: `hermes F.3 rollback — adicionar rotation policy artifacts antes de retry`
- mark_chapter: `Phase F.3 rolled back`

---

## F.4 — Auto-Skill Loop W3 (Meta-Recursivo)

### Escopo do rollback
**RISCO ALTO** — Hermes escreve próprio código. Workflow `hermes-skill-forge.js` + GitHub MCP PR-based deploy + auto-disable via Sentry MCP. Skills geradas vivem em `.claude/skills/` mas podem ter código Python perigoso.

### Trigger de rollback
- Skill gerada causa crash em loop produção (loops/*.py imports skill)
- PR criado tem código malicioso/quebrado mergeado por engano
- Sentry auto-disable falha → skill bad continua rodando
- Feedback loop runaway (Hermes gera 100 skills/h)

### Procedure
```bash
# 1. PARAR HERMES IMEDIATO (skill pode estar rodando)
sudo systemctl stop hermes-pc
ssh vm "sudo systemctl stop hermes-vm"

# 2. Feature flag OFF — bloqueia geração futura
python -c "
import json
with open('config/feature_flags.json', 'r+') as f:
    d = json.load(f)
    d['auto_skill_forge'] = False
    d['skill_auto_disable'] = False
    d['github_mcp_pr_deploy'] = False
    f.seek(0); json.dump(d, f, indent=2); f.truncate()
print('FORGE DESLIGADO')
"

# 3. Listar skills geradas POR Hermes (não as do owner) — diff vs f4-baseline
git diff --name-only f4-baseline HEAD -- .claude/skills/ | \
  grep -v 'hermes-' > /tmp/hermes-generated-skills.txt
cat /tmp/hermes-generated-skills.txt

# 4. Reverter cada skill gerada (preservar owner-authored)
while IFS= read -r f; do
  echo "Removendo skill auto-gerada: $f"
  rm -f "$f"
done < /tmp/hermes-generated-skills.txt

# 5. Revert workflow forge
git checkout f4-baseline -- \
  .claude/workflows/hermes-skill-forge.js \
  daemon/skill_evaluator.py \
  api/skills.py

# 6. Fechar PRs abertos pelo Hermes (via gh CLI)
gh pr list --author "hermes-bot" --state open --json number -q '.[].number' | \
  while read pr; do
    gh pr close "$pr" -c "Rollback F.4 — auto-skill loop disabled"
  done

# 7. Migration: limpar skill_runs + skill_scores tables
sqlite3 data/hermes.db "DELETE FROM skill_runs WHERE created_at >= (SELECT MIN(created_at) FROM skill_runs WHERE skill_source='auto_forge')"
sqlite3 data/hermes.db "DROP TABLE IF EXISTS skill_eval_pending"

# 8. Restart serviços (sem forge)
sudo systemctl start hermes-pc
ssh vm "sudo systemctl start hermes-vm"
sleep 5

# 9. Audit últimos commits Hermes-authored
git log --author="hermes-bot" --since="7 days ago" --oneline
```

### Validate
```bash
python scripts/validate_implementation.py --phase A B C D E --json | \
  python -c "import sys,json; r=json.load(sys.stdin); \
    assert r['summary']['pass']==20; print('OK 20/22')"

# Nenhuma skill auto-gerada ativa
test -z "$(ls .claude/skills/ | grep -v hermes- 2>/dev/null)" && echo "OK skills owner-only"

# Forge endpoint 404 ou retorna flag off
curl -s http://localhost:8000/api/skills/forge/status | grep -q '"enabled":false' && echo "OK forge off"
```

### Persistência (CRÍTICO — auditoria forense obrigatória)
- Telegram URGENTE: `ROLLBACK F.4 CRÍTICO — auto-skill forge desligado — <runaway | bad merge | crash loop> — auditoria manual de N skills geradas necessária`
- memory_save tipo `rollback-critical`: `hermes F.4 rollback — <root cause> — antes de retry: sandbox exec skills geradas + dry-run obrigatório + rate-limit 1 skill/dia + owner approval gate manual`
- mark_chapter: `Phase F.4 rolled back — CRITICAL meta-recursion failure`
- **Bug spawn task**: investigar cada skill gerada, listar side-effects em DB/state

---

## F.5 — MCP Gateway + 3 MCPs Custom (LinkedIn / Prospects / Skills)

### Escopo do rollback
IBM ContextForge gateway na VM (porta nova) + 3 servers MCP custom (FastMCP 3.0). **Risco MÉDIO-ALTO** — gateway entre Brain e tools, falha = Hermes cego.

### Trigger de rollback
- Gateway crash → todas tool calls falham
- OAuth 2.1 token bug → auth rejected em loop
- Rate-limit gateway barra calls legítimas
- MCPs custom expõem dados sensíveis (token, cookies LinkedIn)

### Procedure
```bash
# 1. Pré-flight + backup config gateway
ssh vm "cp -r /opt/mcp-gateway/config /opt/mcp-gateway/config.rollback-$(date +%Y%m%d-%H%M%S)"

# 2. Feature flag OFF — Brain volta a chamar tools diretas
python -c "
import json
with open('config/feature_flags.json', 'r+') as f:
    d = json.load(f)
    d['mcp_gateway_enabled'] = False
    d['mcp_linkedin_custom'] = False
    d['mcp_prospects_custom'] = False
    d['mcp_skills_custom'] = False
    f.seek(0); json.dump(d, f, indent=2); f.truncate()
"

# 3. Stop gateway + MCPs custom
ssh vm "sudo systemctl stop mcp-gateway mcp-hermes-linkedin mcp-hermes-prospects mcp-hermes-skills"
ssh vm "sudo systemctl disable mcp-gateway"

# 4. Stop Hermes pra revert seguro
sudo systemctl stop hermes-pc
ssh vm "sudo systemctl stop hermes-vm"

# 5. Revert código integração
git checkout f5-baseline -- \
  daemon/mcp_client.py \
  daemon/orchestrator.py \
  config/mcp_routes.yaml \
  vm_api/mcp_proxy.py

# 6. Revert systemd units MCP (VM)
ssh vm "sudo rm /etc/systemd/system/mcp-gateway.service"
ssh vm "sudo rm /etc/systemd/system/mcp-hermes-*.service"
ssh vm "sudo systemctl daemon-reload"

# 7. Remover MCPs custom code (VM)
ssh vm "rm -rf /opt/hermes/mcps/hermes-linkedin"
ssh vm "rm -rf /opt/hermes/mcps/hermes-prospects"
ssh vm "rm -rf /opt/hermes/mcps/hermes-skills"

# 8. Migration: token storage gateway
sqlite3 data/hermes.db "DROP TABLE IF EXISTS mcp_oauth_tokens"
sqlite3 data/hermes.db "DROP TABLE IF EXISTS mcp_tool_audit_log"

# 9. Restart Hermes (modo direct-tools, pré-gateway)
sudo systemctl start hermes-pc
ssh vm "sudo systemctl start hermes-vm"
sleep 5
```

### Validate
```bash
python scripts/validate_implementation.py --phase A B C D E --json | \
  python -c "import sys,json; r=json.load(sys.stdin); \
    assert r['summary']['pass']==20; print('OK 20/22')"

# Gateway DOWN
ssh vm "curl -s -o /dev/null -w '%{http_code}' http://localhost:4444/health" | grep -qE "000|connection refused" && echo "OK gateway DOWN"

# Brain volta a usar tools diretas
curl -s http://localhost:8000/api/daemon/state | python -c "import sys,json; d=json.load(sys.stdin); print('OK daemon:', d.get('mode'))"
```

### Persistência
- Telegram: `ROLLBACK F.5 — <gateway crash | oauth bug | token leak> — Brain volta a direct-tools (sem multiplex)`
- memory_save: `hermes F.5 rollback — antes retry: pinning version ContextForge + canary 1% Brain calls + audit log review semanal`
- mark_chapter: `Phase F.5 rolled back`

---

## F.6 — Cérebro Hermes Orquestrador NL (intent classifier + multi-agent)

### Escopo do rollback
Substitui `daemon/orchestrator.py::decide_next_action()` rule-based por classifier Ollama + chat UI. **Risco ALTO** — coração de decisão Hermes. Bug = ações erradas em produção (envio prematuro, deletar prospect, etc).

### Trigger de rollback
- Classifier confunde intents (envia LinkedIn ao invés de email)
- Brain entra em loop (chama mesma tool 100x)
- Cost runaway (Ollama calls explodem)
- Owner reporta "Hermes fez algo que não pedi"

### Procedure
```bash
# 1. PARAR DAEMON IMEDIATO (decisão errada = dano real)
curl -X POST http://localhost:8000/api/daemon/pause -H "X-Internal-Token: $HERMES_INTERNAL_TOKEN"
sleep 2

# 2. Feature flag OFF — volta rule-based
python -c "
import json
with open('config/feature_flags.json', 'r+') as f:
    d = json.load(f)
    d['brain_nl_classifier'] = False
    d['brain_chat_ui'] = False
    d['brain_multi_agent'] = False
    f.seek(0); json.dump(d, f, indent=2); f.truncate()
print('CÉREBRO NL OFF — voltando rule-based')
"

# 3. Stop services
sudo systemctl stop hermes-pc
ssh vm "sudo systemctl stop hermes-vm"

# 4. Audit ações executadas pelo brain NL nas últimas 24h
sqlite3 data/hermes.db "
SELECT timestamp, action, target, reasoning
FROM brain_decisions
WHERE timestamp >= datetime('now', '-24 hours')
  AND source = 'nl_classifier'
ORDER BY timestamp DESC
" > /tmp/brain-nl-audit-$(date +%Y%m%d).csv
echo "Audit gravado: /tmp/brain-nl-audit-$(date +%Y%m%d).csv"

# 5. Revert orchestrator
git checkout f6-baseline -- \
  daemon/orchestrator.py \
  daemon/intent_classifier.py \
  daemon/brain_router.py \
  api/brain.py \
  dashboard/brain.html \
  dashboard/app.js

# 6. Remover componentes UI brain
rm -rf dashboard/components/brain/

# 7. Migration: brain_conversations + brain_decisions tables
# NÃO DROP — preservar pra forensics, apenas marcar inativo
sqlite3 data/hermes.db "ALTER TABLE brain_conversations RENAME TO brain_conversations_f6_rollback_$(date +%s)"
sqlite3 data/hermes.db "DROP TABLE IF EXISTS brain_intent_cache"

# 8. Restart serviços
sudo systemctl start hermes-pc
ssh vm "sudo systemctl start hermes-vm"
sleep 5

# 9. Resume daemon (rule-based ativo)
curl -X POST http://localhost:8000/api/daemon/resume -H "X-Internal-Token: $HERMES_INTERNAL_TOKEN"
```

### Validate
```bash
python scripts/validate_implementation.py --phase A B C D E --json | \
  python -c "import sys,json; r=json.load(sys.stdin); \
    assert r['summary']['pass']==20; print('OK 20/22')"

# Daemon volta rule-based
curl -s http://localhost:8000/api/daemon/state | python -c "
import sys,json
d=json.load(sys.stdin)
assert d.get('decision_mode') == 'rule_based', d
print('OK rule_based active')
"

# /api/brain/chat 404 ou disabled
curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/brain/chat | grep -qE "404|503" && echo "OK brain endpoints off"
```

### Persistência (auditoria obrigatória)
- Telegram URGENTE: `ROLLBACK F.6 — Cérebro NL desligado — <wrong intent | runaway | cost> — auditoria brain_decisions 24h em /tmp/brain-nl-audit-*.csv`
- memory_save tipo `rollback-critical`: `hermes F.6 rollback — <root cause> — retry exige: dry-run mode 7d + owner approval gate cada decision + cost cap Ollama + integration test 50 intents conhecidos`
- mark_chapter: `Phase F.6 rolled back — Brain NL deactivated`
- Spawn task review audit CSV

---

## F.7 — Cobaia Live Ops (warmup 14d milgrauz.exe + enrichment Apollo/Hunter)

### Escopo do rollback
Loop warmup 14d na conta cobaia `milgrauz.exe@gmail.com` (LinkedIn + email) + enrichment pipeline Apollo/Hunter/Firecrawl. **Risco BAIXO pra Caio (cobaia isolada)** mas ALTO pra cobaia (ban = lab base perdida).

### Trigger de rollback
- Cobaia ban LinkedIn (HTTP 999, captcha persistente)
- Email cobaia em blacklist (Hunter verifier rejeita > 10%)
- Apollo/Hunter quota explodida (custo)
- Enrichment pipeline trava (Firecrawl timeout cascading)

### Procedure
```bash
# 1. PAUSE LOOPS COBAIA IMEDIATO
curl -X POST http://localhost:8000/api/daemon/subsystems/linkedin/pause \
  -d '{"reason":"F.7 rollback","duration_minutes":1440}' \
  -H "X-Internal-Token: $HERMES_INTERNAL_TOKEN"
curl -X POST http://localhost:8000/api/daemon/subsystems/email/pause \
  -d '{"reason":"F.7 rollback","duration_minutes":1440}' \
  -H "X-Internal-Token: $HERMES_INTERNAL_TOKEN"

# 2. Feature flag OFF
python -c "
import json
with open('config/feature_flags.json', 'r+') as f:
    d = json.load(f)
    d['cobaia_warmup_loop'] = False
    d['enrichment_apollo'] = False
    d['enrichment_hunter'] = False
    d['enrichment_firecrawl'] = False
    f.seek(0); json.dump(d, f, indent=2); f.truncate()
"

# 3. Stop loops específicos (NÃO Hermes inteiro — Caio mantém)
ssh vm "sudo systemctl stop hermes-warmup-loop hermes-enrichment-loop"

# 4. Snapshot cobaia state pra forensics
ssh vm "cp -r /var/hermes/profiles/milgrauz.exe /var/hermes/profiles/milgrauz.exe.rollback-$(date +%Y%m%d)"
sqlite3 data/hermes.db "
SELECT * FROM warmup_actions
WHERE account='milgrauz.exe@gmail.com'
  AND timestamp >= datetime('now','-14 days')
" > /tmp/cobaia-warmup-history-$(date +%Y%m%d).csv

# 5. Revert código
git checkout f7-baseline -- \
  loops/warmup.py \
  loops/enrichment.py \
  linkedin/cobaia_actions.py \
  daemon/enrichment_pipeline.py \
  api/cobaia.py

# 6. Migration: warmup_actions + enrichment_jobs (preservar histórico)
sqlite3 data/hermes.db "ALTER TABLE warmup_actions RENAME TO warmup_actions_f7_rollback_$(date +%s)"
sqlite3 data/hermes.db "ALTER TABLE enrichment_jobs RENAME TO enrichment_jobs_f7_rollback_$(date +%s)"

# 7. Revoke API keys externas (rotação preventiva se token vazou)
echo "MANUAL: revogar Apollo + Hunter + Firecrawl keys via dashboard providers"

# 8. Restart só Hermes core (sem loops cobaia)
ssh vm "sudo systemctl restart hermes-vm"
sleep 5
```

### Validate
```bash
python scripts/validate_implementation.py --phase A B C D E --json | \
  python -c "import sys,json; r=json.load(sys.stdin); \
    assert r['summary']['pass']==20; print('OK 20/22')"

# Loops cobaia parados
ssh vm "systemctl is-active hermes-warmup-loop" | grep -q "inactive" && echo "OK warmup loop OFF"
ssh vm "systemctl is-active hermes-enrichment-loop" | grep -q "inactive" && echo "OK enrichment loop OFF"

# Caio account NÃO afetado
curl -s http://localhost:8000/api/linkedin/health -H "X-Internal-Token: $HERMES_INTERNAL_TOKEN" | \
  python -c "import sys,json; d=json.load(sys.stdin); assert d['caio_account']['status']=='healthy', d; print('OK Caio preservado')"
```

### Persistência
- Telegram: `ROLLBACK F.7 — cobaia milgrauz.exe pausada 24h — <ban | bounce | quota> — Caio account intocado — histórico em /tmp/cobaia-*.csv`
- memory_save: `hermes F.7 rollback — <root cause> — retry exige: warmup rate menor + Hunter verifier ANTES envio + Apollo coverage check Brasil PME + fallback scraping local`
- mark_chapter: `Phase F.7 rolled back — cobaia ops paused`

---

## F.8 — Observability (Sentry MCP + OpenTelemetry traces + dashboard metrics)

### Escopo do rollback
Sentry MCP + OTel tracing em loops + dashboard metrics page. **Risco BAIXO** — observability é side-channel, não afeta lógica produção. Único risco: overhead OTel derruba latência.

### Trigger de rollback
- OTel overhead > 200ms p99 em loops (telemetria virou bottleneck)
- Sentry MCP falha → daemon trava aguardando upload
- Dashboard metrics page crash browser (volume dados)

### Procedure
```bash
# 1. Pré-flight (global)

# 2. Feature flag OFF (Sentry MCP + OTel)
python -c "
import json
with open('config/feature_flags.json', 'r+') as f:
    d = json.load(f)
    d['sentry_mcp_enabled'] = False
    d['otel_tracing'] = False
    d['metrics_dashboard_v2'] = False
    f.seek(0); json.dump(d, f, indent=2); f.truncate()
"

# 3. Stop Sentry MCP (se VM-local)
ssh vm "sudo systemctl stop sentry-mcp || true"

# 4. Stop services pra remover OTel injection
sudo systemctl stop hermes-pc
ssh vm "sudo systemctl stop hermes-vm"

# 5. Revert código
git checkout f8-baseline -- \
  daemon/observability.py \
  core/tracing.py \
  loops/*.py \
  api/metrics.py \
  dashboard/metrics.html

# Reverter requirements (OTel pkgs)
git checkout f8-baseline -- requirements.txt requirements-vm.txt
pip install -r requirements.txt --force-reinstall
ssh vm "cd /opt/hermes && pip install -r requirements-vm.txt --force-reinstall"

# 6. Migration: otel_spans cache table
sqlite3 data/hermes.db "DROP TABLE IF EXISTS otel_spans"
sqlite3 data/hermes.db "DROP TABLE IF EXISTS sentry_event_queue"

# 7. Restart
sudo systemctl start hermes-pc
ssh vm "sudo systemctl start hermes-vm"
sleep 5
```

### Validate
```bash
python scripts/validate_implementation.py --phase A B C D E --json | \
  python -c "import sys,json; r=json.load(sys.stdin); \
    assert r['summary']['pass']==20; print('OK 20/22')"

# OTel imports gone
python -c "
import importlib, sys
for mod in ['opentelemetry','sentry_sdk']:
    try: importlib.import_module(mod)
    except ImportError: print(f'OK {mod} removed')
"

# Latência loops volta baseline
curl -s http://localhost:8000/api/daemon/state | python -c "
import sys,json
d=json.load(sys.stdin)
for loop in d.get('loops',[]):
    assert loop.get('p99_ms', 0) < 200, f'{loop[\"name\"]} ainda lento: {loop[\"p99_ms\"]}ms'
print('OK loops latency restored')
"
```

### Persistência
- Telegram: `ROLLBACK F.8 — observability removida — <overhead | sentry crash | dashboard crash> — métricas voltam logs locais`
- memory_save: `hermes F.8 rollback — antes retry: OTel sampling 1% + Sentry queue async + dashboard pagination`
- mark_chapter: `Phase F.8 rolled back`

---

## F.9 — Pipeline Studio (Visual DAG editor + execution UI)

### Escopo do rollback
Nova página `dashboard/pipeline-studio` editor visual DAG + backend executor `pipelines/runner.py`. **Risco MÉDIO** — pipelines podem invocar ações cross-channel se gerados errados.

### Trigger de rollback
- Pipeline gerado visual envia email pra prospect errado
- DAG runner trava (deadlock entre steps)
- UI editor crash browser (canvas memory leak)
- Pipeline definitions corrompidas (JSON malformed)

### Procedure
```bash
# 1. PARAR EXECUTOR IMEDIATO
curl -X POST http://localhost:8000/api/pipelines/runner/stop-all \
  -H "X-Internal-Token: $HERMES_INTERNAL_TOKEN" || true

# 2. Feature flag OFF
python -c "
import json
with open('config/feature_flags.json', 'r+') as f:
    d = json.load(f)
    d['pipeline_studio_ui'] = False
    d['pipeline_runner_v2'] = False
    f.seek(0); json.dump(d, f, indent=2); f.truncate()
"

# 3. Stop services
sudo systemctl stop hermes-pc
ssh vm "sudo systemctl stop hermes-vm"

# 4. Snapshot pipelines criados pelo owner pra preservar trabalho
sqlite3 data/hermes.db ".dump pipeline_definitions" > /tmp/pipelines-backup-$(date +%Y%m%d).sql
cp -r pipelines/definitions pipelines/definitions.rollback-$(date +%Y%m%d)

# 5. Revert código
git checkout f9-baseline -- \
  dashboard/pipeline-studio.html \
  dashboard/components/pipeline/ \
  dashboard/app.js \
  pipelines/runner.py \
  pipelines/dag_validator.py \
  api/pipelines.py

# 6. Migration
sqlite3 data/hermes.db "ALTER TABLE pipeline_definitions RENAME TO pipeline_definitions_f9_rollback_$(date +%s)"
sqlite3 data/hermes.db "ALTER TABLE pipeline_runs RENAME TO pipeline_runs_f9_rollback_$(date +%s)"
sqlite3 data/hermes.db "DROP TABLE IF EXISTS pipeline_step_cache"

# 7. Restart
sudo systemctl start hermes-pc
ssh vm "sudo systemctl start hermes-vm"
sleep 5
```

### Validate
```bash
python scripts/validate_implementation.py --phase A B C D E --json | \
  python -c "import sys,json; r=json.load(sys.stdin); \
    assert r['summary']['pass']==20; print('OK 20/22')"

# /api/pipelines/* 404
test "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/pipelines/runs)" = "404" && echo "OK pipelines endpoints off"

# Pipeline definitions preservadas (backup)
test -f /tmp/pipelines-backup-$(date +%Y%m%d).sql && echo "OK backup gerado"
```

### Persistência
- Telegram: `ROLLBACK F.9 — pipeline studio removido — <wrong send | deadlock | crash> — definitions salvas em /tmp/pipelines-backup-*.sql`
- memory_save: `hermes F.9 rollback — retry: dry-run obrigatório DAG + step timeout 30s + owner approval gate pra cross-channel pipelines`
- mark_chapter: `Phase F.9 rolled back`

---

## Apêndice A — Matriz de risco por chapter

| Chapter | Risco | Reversibilidade | Caio expostion | Time-to-rollback |
|---------|-------|----------------|----------------|------------------|
| F.1 | BAIXO | Trivial | Zero | <5 min |
| F.2 | MÉDIO | Alta (revert files) | Zero | 10-15 min |
| F.3 | MÉDIO-BAIXO | Alta (lab isolado) | Zero | 10 min |
| F.4 | **ALTO** | Média (audit skills geradas) | Indireto | 30-60 min + auditoria |
| F.5 | MÉDIO-ALTO | Média (gateway VM) | Indireto | 20-30 min |
| F.6 | **ALTO** | Alta (revert orchestrator) | Direto (decisões erradas) | 15-30 min + audit CSV |
| F.7 | BAIXO p/ Caio, ALTO p/ cobaia | Alta (pause loops) | Zero (cobaia só) | 10 min |
| F.8 | BAIXO | Trivial | Zero | 10 min |
| F.9 | MÉDIO | Alta (preservar pipelines) | Indireto | 15 min |

---

## Apêndice B — Checklist universal pós-rollback

- [ ] `git status` limpo (ou stash registrado)
- [ ] `validate_implementation.py --phase A B C D E` retorna 20/22 PASS
- [ ] PC `curl /health` HTTP 200
- [ ] VM `curl /health` HTTP 200 via tunnel
- [ ] WS `/ws?token=...` handshake OK
- [ ] Daemon state `healthy: true`
- [ ] LinkedIn Caio account `status: healthy`
- [ ] DB integrity: `PRAGMA integrity_check;` retorna `ok`
- [ ] Logs últimos 5min sem `ERROR|CRITICAL`
- [ ] Telegram alert enviado
- [ ] `memory_save` tipo `rollback` executado
- [ ] `mark_chapter` registrado
- [ ] Git tag `fX-rollback-YYYYMMDD-HHMMSS` criado
- [ ] Backup DB `.bak` arquivado (NÃO deletar antes 30d)
- [ ] Artifacts forensics movidos pra `.rollback-*` (não deletados)

---

## Apêndice C — Escalation matrix

| Sintoma | Ação imediata | Quem notificar |
|---------|--------------|----------------|
| Caio LinkedIn ban risk | `POST /daemon/pause` ALL loops + rollback F.7 + F.2 (subsystems) | Owner via Telegram URGENTE |
| DB corruption | NÃO sobrescrever — restaurar backup pré-fase + diff snapshot | Owner + spawn task forense |
| Auth A regression | `systemctl stop` ambos lados + rollback ATÉ baseline anterior | Owner URGENTE |
| Meta-recursion runaway (F.4) | KILL `hermes-bot` PID + flag OFF + audit 24h commits | Owner + spawn task review skills |
| Brain decisão errada produção (F.6) | `daemon/pause` + rollback F.6 + audit CSV brain_decisions | Owner URGENTE |
| Cost runaway (Ollama/Apollo/Hunter) | Revogar API keys + flag OFF enrichment/brain | Owner |

---

**Documento atualizado**: 2026-06-08
**Versão**: 1.0
**Owner**: cleao.mkt@gmail.com (solo)
**Próxima revisão**: após cada chapter F.X fechado (adicionar lições aprendidas)
