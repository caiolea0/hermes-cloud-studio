# PLAN.md F.7 Patch Suggestion (post f7-schedule-arch-analysis)

Workflow: `f7-schedule-arch-analysis`
Data análise: 2026-06-10
Decisão registrada em: `.claude/F7-SCHEDULE-ARCH-DECISION.md`

---

## Bloco a substituir (PLAN.md linhas ~388-420)

Localizar e remover o bloco placeholder atual que começa com header tipo:

`🚨 DECISÃO ARQUITETURAL PENDENTE — Schedule Infrastructure`

Inclui:
- Tabela das 8 alternativas (A-H) com scores hipotéticos
- Lista 5 critérios de avaliação (regression_risk, complexity_roi, cross_platform, future_proof, observability)
- Linha "Recommendation default: TBD pós-workflow f7-schedule-arch-analysis"
- Qualquer TODO/FIXME referenciando workflow pendente

Range aproximado: linhas 388-420 (validar offset exato via Read antes do Edit — file pode ter drifted).

---

## Bloco novo (substituição)

```markdown
### Schedule Infrastructure — Decisão Final (workflow f7-schedule-arch-analysis 2026-06-10)

**Primary**: B) APScheduler in-process daemon (AsyncIOScheduler embedded em `daemon/orchestrator.py` + `hermes_api_v2.py` lifespan) — 3 tasks F.7 (métricas 1h, stop gates 30min, Telegram 19h) compartilham state com daemon (warmup_state cache, `linkedin/limiter.acceptance_cooldown` PATCH-014 singleton, cobaia_daily_metrics) e in-process elimina IPC/HTTP bridge. `CronTrigger(timezone=ZoneInfo('America/Cuiaba'))` resolve constraint F.7 "NUNCA asyncio.sleep até 19h DST-fragile" em 1 linha. Observability `add_listener(EVENT_JOB_ERROR|EXECUTED|MISSED)` integra F.5 Sentry + F.8 Cost&Perf grátis. Zero infra nova (aproveita `hermes-daemon.service` systemd unit), única dep ~600KB tolerável (13→14 deps).

**Fallback**: D-híbrido) asyncio loop check 60s inline daemon (Tasks 2+3a) + systemd --user timer VM (Task 4 Telegram 19h `OnCalendar='19:00:00' Persistent=true`) — acionado se APScheduler 3.x mostrar bug crítico durante F.7 (conflito event loop com loops MERGED-015 spawn, tzdata Windows flake, EVENT_JOB_MISSED race). Custo: +1 sessão F.7 reescrever 3 callables como inline checks + perde observability nativa.

**Long-term migration**: B → migração futura F.future para APScheduler 4.x quando estável (post-2026) OU Temporal.io se Hermes escalar multi-tenant (10+ schedulers concurrent). Migração 3.11→4.x é mecânica (classes movidas `apscheduler.AsyncScheduler`, sync interfaces já não usadas — Hermes async-only). Solo owner F.7→F.9 não precisa Temporal.

**F.7 Tasks 2/3/4 implementation**: ver `.claude/F7-SCHEDULE-ARCH-DECISION.md` sections 5-6 (pseudo-code completo + migration checklist 12 steps).

**Dependencies novas**:
- `apscheduler>=3.11.0,<4.0` (pin explícito anti 4.0aX)
- `tzdata>=2024.1` (Windows tz fallback robusto)

**F.7 sessions impact**: base 5 → 6 sessões reais (+1 sessão dedicada `core/scheduler.py` singleton + wire-up `HermesDaemon.start/shutdown` + endpoints `/api/scheduler/jobs`).

**Success criteria**: ver `.claude/F7-SCHEDULE-ARCH-DECISION.md` section 10 (8 critérios — smoke prod 3 jobs registered, 24h métricas streak, gate trigger <30min, Telegram 7d streak, regression 20/22 PASS preservada, daemon heartbeat <60s, fail-closed verificado, Sentry capture verified).

**Rollback plan**: ver `.claude/F7-SCHEDULE-ARCH-DECISION.md` section 11 (procedimento 15-30min preservando warmup state cobaia 14d intacto — remove_job runtime + git revert seletivo + migrate fallback D-híbrido +1 sessão).

**Guardrails adicionados**:
- NUNCA upgradar `apscheduler` para 4.0aX em produção (pin `<4.0` em requirements.txt)
- Callables NUNCA instanciam `AccountProfile.load()` ou `Settings()` nova — reusar `self.account_profile`/`self.settings` do daemon (anti state drift)
- Inline `_check_stop_gates()` no P1-P7 loop body PRESERVADO (constraint L1191-1204) — APScheduler 30min é double-check fallback, NÃO substitui inline
```

---

## Git command sequence (owner aplica manualmente)

Owner faz revisão crítica antes do commit. Sequência sugerida:

- **Step 1**: Read completo `.claude/F7-SCHEDULE-ARCH-DECISION.md` (entender decisão arquitetural antes de patchear PLAN)
- **Step 2**: Marcar approval checklist section 13 do F7-SCHEDULE-ARCH-DECISION.md (todos itens checados)
- **Step 3**: Edit `.claude/PLAN.md` — substituir bloco placeholder "🚨 DECISÃO ARQUITETURAL PENDENTE — Schedule Infrastructure" pelo bloco novo acima
- **Step 4**: `git add .claude/PLAN.md .claude/F7-SCHEDULE-ARCH-DECISION.md .claude/PLAN-F7-PATCH-SUGGESTION.md`
- **Step 5**: `git commit -m "docs(plan): F.7 schedule infra decisão final (APScheduler in-process, workflow f7-schedule-arch-analysis)"`
- **Step 6**: `git push origin master`

---

## Instruções para owner Claude da sessão F.7 dedicada

ANTES de iniciar sessão F.7 implementation:

1. **Read** `.claude/F7-SCHEDULE-ARCH-DECISION.md` completo (decisão arquitetural canônica — pseudo-code Tasks 2/3/4, migration checklist 12 steps, risk mitigation 5 blockers, success criteria, rollback)
2. **Confirm** PLAN.md F.7 section "Schedule Infrastructure" reflete decisão final (não placeholder antigo — se ver "🚨 DECISÃO ARQUITETURAL PENDENTE" patch não foi aplicado, ABORT e aplicar primeiro)
3. **Confirm** `requirements.txt` tem `apscheduler>=3.11.0,<4.0` + `tzdata>=2024.1` (Primary B requer); se ausente: adicionar como Step 1 da sessão F.7
4. **Use** F.7 Tasks 2/3/4 implementation plan (F7-SCHEDULE-ARCH-DECISION.md section 5-6) como base canônica — NÃO improvisar callables, NÃO recalcular `acceptance_cooldown` (fonte canônica PATCH-014 obrigatória), NÃO remover inline `_check_stop_gates()` do P1-P7 loop body
5. **Pre-deploy gate** obrigatório: `bash scripts/validate_implementation.py phases A B C D E` deve manter 20/22 PASS; se cair para <20, ROLLBACK imediato + migrar fallback D-híbrido
6. **Canary 2h prod** obrigatório pós-deploy: `ssh hermes-gcp 'journalctl --user -fu hermes-daemon -n 100 | grep -E "(scheduler|cobaia)"'` — abort se ERROR no listener nas primeiras 2h

---

## Referências cruzadas

- `.claude/F7-SCHEDULE-ARCH-DECISION.md` — decisão arquitetural completa (rank table 8 opções, pseudo-code, rollback)
- `.claude/PLAN.md` — IMPLEMENTATION-PLAN canônico (F.7 section atualizada via este patch)
- `.claude/DEPLOY-FASE-F.md` §2 — systemd units canônicos (hermes-warmup.timer pattern para fallback D)
- `linkedin/limiter.py` PATCH-014 — fonte canônica `acceptance_cooldown()` (proibido recalcular)
- `daemon/orchestrator.py` L1191-1204 — constraint inline `_check_stop_gates()` no P1-P7 loop (preservar)
