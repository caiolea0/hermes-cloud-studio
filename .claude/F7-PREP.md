# F.7 Cobaia Live Ops — PREP Checklist

**Criado:** 2026-06-16 (F.4.5 closeout)
**Próxima sub-sessão:** F.7 C1 (approx. 6 sub-sessions estimadas)
**Dependencies:** F.1 ✅ · F.2 ✅ · F.3 ✅ · F.5 ✅ · F.6 ✅ · F.8 ✅ · F.9 ✅ · F.4 ✅

---

## 1. Infra pré-requisitos (todos ✅)

| Chapter | Entregável relevante F.7                              | Status         |
|---------|-------------------------------------------------------|----------------|
| F.2     | Mission Control + WS broadcast real-time              | ✅ CLOSED       |
| F.3     | Lab Cockpit + stealth audit smoke E2E CreepJS 5/5     | ✅ CLOSED       |
| F.4     | Auto-Skill Loop + quarantine cron + GitHub PR deploy  | ✅ CLOSED       |
| F.5     | MCP Gateway :55401 + 3 custom MCPs + 5 public MCPs   | ✅ CLOSED       |
| F.6     | Brain.decide() 6 intents + FSM + safety gates         | ✅ CLOSED       |
| F.8     | Observability: mcp_calls + brain_runs + errors_inbox  | ✅ CLOSED       |
| F.9     | Pipeline Studio: CRUD + engine + A/B + UI             | ✅ CLOSED       |

---

## 2. Decisões pendentes owner (perguntar no início F.7 C1)

> **STATUS 2026-06-17 (P5 hardening)**: D1-D7 CRISTALIZADOS via 6 sub-sessions F.7 C1-C6 + P5 closeout. Histórico decisões abaixo preservado para referência. Ver `.claude/PLAN.md` F.7 CHAPTER CLOSED block para resumo executável.

### D1 — Conta cobaia LinkedIn  ✅ CRISTALIZADO
- [x] Nome: "Caio Leão" (nome real owner — não disposable)
- [x] Tipo: free tier
- [x] LI_AT: DEFERRED até owner finalizar profile All-Star + 50 conexões seed (~10 dias manual)
- [x] Profile completeness: TODO owner manual (badge All-Star + 50 conexões mínimo + 2-4 posts orgânicos antes Hermes ativar)
- **Action**: `.claude/F7-OWNER-ACTIONS.md` Pre-launch checklist owner manual

### D2 — Schedule warmup ramp-up  ✅ CRISTALIZADO (mem_mqgt0sf7)
- [x] D2.1: Warmup_days = 14 dias default
- [x] D2.2: Working hours = 07h–22h America/Cuiaba (randomização within window)
- [x] D2.3: Weekends DISABLE
- [x] DM count fases: lurking d0-6 zero connects + ramp d7-13 linear + normal d14+
- **Action**: `linkedin/config.py` CobaiaConfig defaults aplicado

### D3 — KPIs e thresholds de sucesso  ✅ CRISTALIZADO
- [x] D3.1: Reply rate threshold >8%
- [x] D3.2: Connect accept rate threshold >20%
- [x] D3.3: Profile view→connect >3%
- [x] D3.4: First skill = `linkedin-engagement` (soft touch lurking phase)
- **Action**: `core/cobaia_metrics.py` get_cobaia_today_metrics() + dashboard KPI

### D4 — Emergency stop UX  ✅ CRISTALIZADO + implementado F.7 C3
- [x] 1-click PAUSE ALL via `/api/linkedin/cobaia/emergency-stop`
- [x] Auto-pause: N=3 erros consecutivos → pause automático (config.py)
- [x] Telegram alert via `core/alert_aggregator.py` tríplice (Sentry+email+Telegram)
- **Action**: `api/cobaia.py` + dashboard cobaia tab UI

### D5 — Alert escalation  ✅ CRISTALIZADO + implementado F.7 C4
- [x] Sentry environment = `cobaia-live` (env tag separado de production)
- [x] Telegram throttle: 5 alerts/hour máximo (alert_aggregator dedup)
- [x] Email digest diário 09h BRT (daemon/email_digest.py)
- [x] Recipient único: EMAIL_TO=cleao.mkt@gmail.com
- **Action**: setup_telegram_bot.ps1 + setup_hunter_key.ps1 (P5)

### D6 — Review cadence primeira semana  ✅ CRISTALIZADO + PIVOT D6 implementado F.7 C4
- [x] Owner review manual: REPLACED PIVOT D6 → Bug Export endpoint autonomous
- [x] `/api/cobaia/bug-export?hours=24&format=json|markdown` → owner consume Telegram digest
- [x] Métricas dashboard: cobaia page 4-section (header + timeline + KPI + activity)
- [x] Semana 1: AUTONOMOUS com alertas (owner não precisa abrir dashboard cada dia)
- **Action**: `api/cobaia.py` bug-export + dashboard 4 sections

### D7 — Rollback bad skill em produção  ✅ CRISTALIZADO
- [x] Quarantine cron F.4.4 cobre (auto após 10 runs <50% success → quarantined)
- [x] Override manual via `/api/hermes/skills` PATCH active=false
- [x] Hard deadline: alert_aggregator detecta 3 erros consecutivos → pause + Telegram + Sentry
- **Action**: systemd hermes-skill-quarantine.timer active VM (F.4.4 C2)

### D8 — Daemon prioridade cobaia  ✅ CRISTALIZADO (F.7 C2 commit cc29c76)
- [x] TaskCategory.COBAIA P0 ABSOLUTE OVERRIDE (cobaia roda primeiro antes P1-P7)
- [x] `daemon/orchestrator.py` _get_cobaia_action()

### D9 — Live Ops dashboard layout  ✅ CRISTALIZADO (F.7 C3 commit 9d5f490)
- [x] Single-page 4 sections vertical (header + timeline + KPI + activity)
- [x] 5 IIFE components React-free (BLACKLIST R2 compliant)

### D10 — Auto-tune trigger semantics  ✅ CRISTALIZADO (F.7 C5 commit 3d5924f)
- [x] REACTIVE automatic (KPI breach → trigger auto, sem owner confirm)
- [x] Cooldown 72h por skill (anti-thrash)
- [x] PR review é gate humano (skill_proposals_studio F.4.3)

---

## 3. Riscos críticos F.7

### R1 — LinkedIn account ban (ALTO)
- Stealth modules `linkedin/` BLACKLIST R2 (25 sub-sessions intacto)
- Patchright + 11 JS patches + human.py (Bezier mouse + bigram typing)
- Residential SOCKS5 proxy obrigatório
- **Mitigation**: warmup 14 dias COMPLETO antes DM; working hours gate; rate limiter SQLite; cooldown 30min entre campaigns
- **Monitor**: `linkedin_health_monitor_loop` adaptive 60s–5min; challenge detection cooldown.py

### R2 — Ghost profile / zero replies
- Cobaia sem conexões → profile researcher não encontra alvo
- **Mitigation**: seed inicial 50+ conexões mínimo antes campanha fria; usar `linkedin-engagement` primeiro (comentar posts = soft touch)

### R3 — GitHub PR cascade skill ruins
- Auto-Skill Loop F.4 pode propor skill ruim → lab_passed (falso positivo) → PR merged → produção
- **Mitigation**: D4 lab_failed BLOCK PR (já implementado F.4.2); owner aceita MANUALMENTE via UI F.4.3; quarantine cron F.4.4 detecta regressão pós-deploy

### R4 — Brain decide() loop sem owner confirm
- Brain pode acumular decisions pendentes se owner não confirmar
- **Mitigation**: F.6 safety gates (requires_confirm=True para P1 críticas); Brain FSM reseta após timeout

### R5 — VM memory exhaustion com warmup 24/7
- Patchright browser process acumula RAM (700MB–1.5GB steady-state)
- VM e2-standard-4 = 16GB RAM (OK para 1 browser + Ollama qwen3:8b ~8GB)
- **Monitor**: `daemon/orchestrator.py` P4 discovery scans noturnos 0–6h; overlap com Patchright = risco

### R6 — Skill YAML encoding issues (histórico)
- Skills YAML sem acentos (decisão arquitetural legacy)
- Quarantine cron escapa paths via `pathlib.Path.stem` — safe
- **Monitor**: skill_runs.status='error' com rate alta → quarantine cron captura

---

## 4. Componentes F.7 a implementar (6 sub-sessions estimadas)

### C1 — Cobaia account bootstrap + warmup scheduler
- Configurar conta cobaia no `linkedin/config.py`
- Warmup state seed em `linkedin/limiter.py` (SQLite `warmup_state` table)
- Endpoint `POST /api/linkedin/cobaia/start-warmup` (backend PC)
- Dashboard "Cobaia Status" card na página linkedin (working_days + phase + today_counts)
- APScheduler job: `cobaia_warmup_daily_check` (09h BRT — per DECISION.md F.3.4)

### C2 — Brain + Daemon cobaia integration
- `daemon/orchestrator.py` P1 cobaia override: pending replies primeira
- Brain.decide() intent `cobaia_warmup_next_action` (F.6 REUSE)
- Metrics tracking: `cobaia_daily_metrics` table (view_count, connect_sent, reply_received per day)

### C3 — Live Ops dashboard page
- Nova page `cobaia` em dashboard (data-page="cobaia")
- Timeline 14 dias warmup visual (barra progress dia-a-dia)
- KPI cards: reply_rate, accept_rate, views_hoje
- Activity feed filtrado apenas cobaia actions
- Emergency stop button `POST /api/linkedin/cobaia/emergency-stop`

### C4 — Alert system integration
- Sentry environments `cobaia-live` + custom tags
- Telegram bot F.7 alerts (challenge detected, cooldown hit, ban suspected)
- `POST /api/linkedin/cobaia/health` endpoint com score 0–100

### C5 — Skill auto-tune for cobaia
- F.4 integration: `linkedin-profile-researcher` + `linkedin-connection-sender` skills ativas cobaia
- Auto-tune via Brain: se reply_rate baixo → Brain sugere skill revision → F.4 loop
- Quarantine cron F.4.4 protege: skill ruim quarantinad automático após 10 runs

### C6 — 14d review + closeout
- Final metrics report gerado pela Brain (intent=`weekly_report`)
- Owner review dashboard screenshot capturado
- F.7 CHAPTER CLOSED

---

## 5. Pre-flight day-1 cobaia (checklist de execução)

Execute estes checks ANTES de ativar warmup:

```bash
# 1. Webhook production still live
curl -s -o /dev/null -w "%{http_code}" -X POST https://hermes-api.caioleao.com/api/skills/webhook/pr-merged \
  -H "Content-Type: application/json" -d "{}" 
# Expected: 401

# 2. Quarantine cron timer active
ssh hermes-gcp 'systemctl --user is-active hermes-skill-quarantine.timer'
# Expected: active

# 3. Brain.decide() sanity (6 intents)
curl -s http://localhost:8500/api/agent-zero/decide \
  -H "X-Hermes-Token: $TOKEN" \
  -d '{"message": "status update"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('intent'))"

# 4. MCP Gateway health
curl -s http://localhost:55401/health | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])"
# Expected: ok

# 5. Skills all active (non-quarantined)
curl -s http://localhost:8500/api/hermes/skills -H "X-Hermes-Token: $TOKEN" | \
  python3 -c "import sys,json; s=json.load(sys.stdin); print([x['name'] for x in s if x.get('active')])"

# 6. LinkedIn health probe
curl -s http://localhost:8500/api/linkedin/health -H "X-Hermes-Token: $TOKEN" | python3 -c "
import sys,json; d=json.load(sys.stdin); print(d.get('overall_status'))"
# Expected: ok OR cooldown (NOT challenge OR blocked)

# 7. Observability DB tables exist
python3 -c "
import sqlite3; conn=sqlite3.connect('hermes_local.db')
tables=['mcp_calls','brain_runs','errors_inbox','skill_runs','skill_proposals']
for t in tables:
    n=conn.execute(f\"SELECT COUNT(*) FROM {t}\").fetchone()[0]
    print(f'{t}: {n} rows')
"

# 8. Sentry SDK receiving (if configured)
python3 -c "import sentry_sdk; sentry_sdk.capture_message('F.7 cobaia pre-flight'); print('Sentry OK')"
```

---

## 6. Owner weekly review checklist (semanas 1–2)

Verificar diariamente às 09h BRT:

| Métrica | Onde ver | Threshold alerta |
|---------|----------|-----------------|
| Warmup phase | Dashboard cobaia card | Regressão = bug |
| Daily view count | `linkedin_engagements` | 0 = daemon parou |
| Connect sent | `linkedin_campaigns` | >limite diário = URGENTE |
| Reply received | `activities` filter cobaia | >0 = sinal positivo |
| Skill error rate | `/api/skills/health` | success_rate < 0.5 → quarantined auto |
| Brain decision queue | `/api/daemon/decisions` | Pendentes > 5 = review |
| Sentry errors | Sentry dashboard | Any P1 = fix immediate |

---

## 7. APScheduler decisions cristalizadas (DECISION.md F.3.4)

Per decisão arquitetural commit a0d3eb0:
- **Warmup daily check**: `cobaia_warmup_daily_check` job → 09h BRT (America/Cuiaba)
- **Night discovery**: P4 daemon `0–6h` slot (já implementado orchestrator.py)
- **Skill quarantine**: systemd timer `hermes-skill-quarantine.timer` hourly (F.4.4 C2 ✅ ACTIVE)
- **Weekly report**: P7 daemon domingo 19h–21h (Brain intent=weekly_report)
- **NOT cron**: skill synthesis auto-trigger (D6 PIVOT F.4.2 — manual API only)

---

## 8. Files F.7 NOVO (estimado)

| File | Tipo | Descrição |
|------|------|-----------|
| `api/cobaia.py` | NOVO | REST endpoints cobaia ops |
| `dashboard/components/cobaia_live_ops.js` | NOVO | Live ops UI page |
| `migrations/2026_06_cobaia_metrics.sql` | NOVO | `cobaia_daily_metrics` table |
| `daemon/cobaia_warmup.py` | NOVO | Warmup scheduler logic |
| `tests/test_cobaia_warmup.py` | NOVO | Unit tests warmup state machine |
| `linkedin/config.py` | MATURE | Add cobaia account config |
| `daemon/orchestrator.py` | MATURE | P1 cobaia override |
| `server.py` | MATURE | Register `/api/cobaia` router |

---

## 9. Estimativa esforço F.7

| Sub-sessão | Foco | Tokens estimado |
|-----------|------|-----------------|
| C1 | Account bootstrap + warmup scheduler | ~70k |
| C2 | Brain + Daemon cobaia integration | ~80k |
| C3 | Live Ops dashboard page | ~90k |
| C4 | Alert system (Sentry + Telegram) | ~50k |
| C5 | Skill auto-tune + F.4 integration | ~60k |
| C6 | 14d review + closeout | ~30k |
| **Total** | | **~380k** |

**Banda histórica**: 50–150k tokens/sessão owner solo → **3–8 dias calendário** (ritmo 1 sessão/dia).

---

## 10. F.7 BLACKLIST extensão

F.7 estende BLACKLIST R2 com restrições adicionais:
- `linkedin/` SOMENTE modificações para cobaia config (NÃO production account)
- `linkedin/stealth.py` FROZEN (11 patches validados — qualquer mudança requer lab E2E)
- `linkedin/human.py` FROZEN (timing calibrado — não alterar sem creepJS re-audit)
- Cobaia campaigns devem usar `headless=False + xvfb-run` (NUNCA headless=True em produção)
- Rate limits são LAW: `linkedin/config.py` limits NÃO aumentar sem warmup completo

---

*Cross-ref: PLAN.md § F.7 · DECISION.md F.3.4 APScheduler · linkedin/config.py LinkedInConfig · F.4.4 C2 quarantine cron (auto-protection skill quality)*
