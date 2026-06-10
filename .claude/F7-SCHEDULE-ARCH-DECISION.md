# F.7 Schedule Infrastructure — Decisão Arquitetural Final

> **Status**: DECIDIDO — aguarda owner approval checklist §13
> **Data**: 2026-06-09
> **Owner**: Caio Leão
> **Trigger**: PLAN.md F.7 bloco "🚨 DECISÃO ARQUITETURAL PENDENTE" (L393-422)
> **Escopo**: F.7 Tasks 2 (métricas 1h), 3a (stop gates 30min), 4 (Telegram 19h) — schedule infra

---

## 1. Context (origem decisão)

Descoberta F.3.4 (2026-06-10 commit c3c24d3) confirmou grep zero matches `APScheduler|crontab|celery|cron` em `daemon/orchestrator.py` + cross-ref memory `mem_mq7fh8qa` (Hermes deps inventory) + `mem_mq7eyrio` (F.7 task slicing 4→6 sessões). PLAN.md L393-422 cristalizou que 3 das 6 tasks F.7 dependem de schedule infra com state shared no daemon — sem decisão arquitetural prévia, owner Claude da sessão F.7 vai improvisar ad-hoc e potencialmente regredir 20/22 PASS regression suite phases A-E.

**Stack atual de schedule** (baseline): 6 asyncio loops com `sleep()` manual:
- `loops/sync.py` sleep(60) | `loops/linkedin_sync.py` sleep(10) | `loops/linkedin_scheduler.py` sleep(30) com `_compute_schedule_state()` re-check gates
- `loops/linkedin_session.py` sleep(3600) | `loops/linkedin_health.py` sleep(180) | `loops/vm_watchdog.py` sleep(30)
- `daemon/orchestrator.py` main loop P1-P7 cascade com `BR_HOLIDAYS` hardcoded + `ERROR_PAUSE_SECONDS=600` circuit breaker

**Constraint inviolável F.7**: NUNCA `asyncio.sleep` até horário absoluto (19h) — DST-fragile + restart-fragile. Pattern obrigatório: trigger nativo timezone-aware OU loop check 60s com `datetime.now(tz).hour==19 and not sent_today` flag-protected.

---

## 2. Sumário Executivo

- **Primary recommendation**: **Opção B — APScheduler in-process daemon** (`AsyncIOScheduler` embedded em `daemon/orchestrator.py` + `hermes_api_v2.py` lifespan)
- **Rationale (3 frases)**: 3 tasks F.7 compartilham state com daemon (`warmup_state` cache, `linkedin/limiter.acceptance_cooldown` PATCH-014 singleton, `cobaia_daily_metrics`) e in-process elimina IPC/HTTP bridge necessário pra crontab — jobs invocam `self._method()` direto sem cold-start. `CronTrigger(timezone=ZoneInfo('America/Cuiaba'))` resolve constraint "NUNCA `asyncio.sleep` até 19h DST-fragile" em 1 linha. Observability nativa `add_listener(EVENT_JOB_ERROR|EXECUTED|MISSED)` integra F.5 Sentry + F.8 Cost&Perf grátis sem touch nas callables.
- **F.7 sessions impact**: base 6 → **6 (zero overhead)** vs Opção A crontab (+1 sessão pra wrappers bash + scripts standalone reinit deps from disk)
- **Dependencies novas**: `apscheduler>=3.11.0,<4.0` (~600KB) + `tzdata>=2024.1` (~5MB, Windows zoneinfo fallback) — total 13 deps → 14 (+10% venv size, aceitável)
- **Mature files touched**: 6 (`daemon/orchestrator.py`, `hermes_api_v2.py`, `linkedin/limiter.py`, `linkedin/account_profile.py`, `core/state.py`, `vm_api/routes.py`) — regression risk MÉDIO (score 6/10) mitigado via `add_job()` ANTES de `run_forever()` (P1-P7 loop body intacto)

---

## 3. 8 Alternativas Avaliadas

| Rank | Option | Total Score | Regression | Complexity | Cross-Platform | Future-Proof | Accepted ≥3/4 |
|------|--------|-------------|------------|------------|----------------|--------------|---------------|
| 🥇 1 | **B — APScheduler in-process daemon** | **16** | 6 | 3 | 4 | 3 | ✅ |
| 🥈 2 | G — systemd --user timers VM | 18 | 4 | 4 | 4 | 6 | ✅ |
| 🥉 3 | A — Linux crontab VM | 21 | 6 | 3 | 4 | 8 | ❌ (2/4) |
| 4 | H — Daemon main loop time-check | 22 | 7 | 4 | 4 | 7 | ❌ |
| 5 | D — asyncio.create_task + sleep loop | 23 | 5 | 5 | 4 | 9 | ❌ |
| 6 | F — MCP scheduled-tasks server | 24 | 5 | 5 | 6 | 8 | ❌ |
| 7 | C — FastAPI BackgroundTasks | 28 | 8 | 5 | 5 | 10 | ❌ |
| 8 | E — Celery + Redis | 32 | 7 | 9 | 6 | 10 | ❌ |

**Critério "Accepted"**: ≥3 das 4 lenses (regression_risk, complexity_roi, cross_platform, future_proof) com `valid=true`. Lower score = melhor. Opção B vence por future_proof excepcional (3/10 — listeners nativos F.5/F.8 + add_job API programática F.9 + migration path 4.x mecânica).

---

## 4. Análise Detalhada Primary Option (B)

### 4.1 Pros decisivos
- **Async-native**: `AsyncIOScheduler` roda no MESMO event loop do daemon — zero thread overhead, compatível 100% com `httpx` async + `linkedin/*` atual
- **Shared state trivial**: jobs invocam `self._method()` da instância `HermesDaemon` direto — acesso natural a `warmup_state`, `limiter.acceptance_cooldown`, `cobaia_daily_metrics` SEM IPC/HTTP bridge
- **DST-safe elegante**: `CronTrigger(hour=19, timezone=ZoneInfo('America/Cuiaba'))` resolve constraint F.7 em 1 linha vs Opção D loop check 60s + flag manual
- **Observability nativa**: `add_listener(EVENT_JOB_ERROR|EXECUTED|MISSED)` → F.8 ganha duration + failure_rate grátis, F.5 Sentry integra em 5 linhas
- **Zero infra nova**: aproveita `hermes-daemon.service` systemd unit JÁ existente; deploy = `pip install` + reload
- **Endpoint observability trivial**: `GET /api/scheduler/jobs` lista next_run_time + last_error real-time pra dashboard Task 5
- **Restart-safe**: `misfire_grace_time=300` + `coalesce=True` resolve restart-edge — daemon down 18:55-19:05 → CronTrigger 19h misfire detectado → dispara 1x assim que sobe

### 4.2 Cons aceitos
- Nova dep ~600KB + tzdata ~5MB (+10% venv, owner aceita)
- Single-process: daemon crash não-recuperado = 3 jobs param silenciosamente — mitigação via `hermes-daemon.service Restart=always` + `OnFailure` Telegram alert + `vm_watchdog_loop` PC-side
- MemoryJobStore perde job definitions em restart — mitigação: `register_jobs()` SEMPRE no `daemon.start()` com `replace_existing=True` (jobs vivem como código, não dados)
- APScheduler 4.x ainda alpha (4.0.0a6 Jun/2026) — pin `<4.0`, migração futura mecânica quando estável (2027+)
- Touch 6 mature files — regression risk MÉDIO (gate `bash scripts/validate_implementation.py phases A B C D E` 20/22 PASS inviolável)

### 4.3 Cross-platform support
**VM_only** declarado. Honra GUARDRAILS linha 12-16 (LinkedIn/patchright VM-only). Daemon JÁ roda VM-side (`hermes-daemon.service` systemd `--user` + `loginctl enable-linger`). PC server.py loops continuam intactos — cobaia 100% VM-isolated, zero cross-machine coordination needed. Owner laptop fechado: VM GCP 24/7 continua coletando + reportando independente de PC state.

### 4.4 Dependencies required
```
apscheduler>=3.11.0,<4.0  # 3.x estável, 4.x ainda alpha 2026
tzdata>=2024.1            # Windows zoneinfo fallback America/Cuiaba
```
Zero Redis, zero SQLAlchemy, zero Docker. Reusa stdlib `sqlite3` + httpx existente.

---

## 5. F.7 Tasks 2/3/4 Implementation Plan

### 5.1 Pré-requisitos (ANTES Tasks 2/3/4)
1. `pip install apscheduler>=3.11.0,<4.0 tzdata>=2024.1` em venv VM
2. `migrations/0XX_cobaia_warmup_tables.sql` aplicada — `cobaia_daily_metrics PK(date,account)` + `cobaia_actions_log` + `cobaia_pause_events` + `ALTER warmup_state ADD COLUMN paused INT DEFAULT 0 + paused_reason TEXT`
3. `linkedin/account_profile.challenges_in_last_24h()` helper criado (rolling window via `cobaia_actions_log`)
4. `linkedin/limiter.acceptance_cooldown()` exposto como função pública — **FONTE CANÔNICA PATCH-014, proibido recalcular**

### 5.2 `core/scheduler.py` (NEW — singleton ~60 linhas)
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED
from zoneinfo import ZoneInfo
import logging, time
from core.state import set_runtime_state

log = logging.getLogger("hermes.scheduler")
TZ_CUIABA = ZoneInfo("America/Cuiaba")  # DST off since 2019 mas explícito
_scheduler: AsyncIOScheduler | None = None

def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            timezone=TZ_CUIABA,
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
        )
        _scheduler.add_listener(_on_job_event, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED | EVENT_JOB_MISSED)
    return _scheduler

def _on_job_event(event):
    job_id = event.job_id
    if event.exception:
        log.error(f"job {job_id} crashed: {event.exception}", exc_info=event.exception)
        try:
            import sentry_sdk; sentry_sdk.capture_exception(event.exception)
        except ImportError: pass
        set_runtime_state(f"scheduler.{job_id}.last_error",
                          {"ts": time.time(), "msg": str(event.exception)[:500]})
    else:
        set_runtime_state(f"scheduler.{job_id}.last_run", {"ts": time.time(), "ok": True})
```

### 5.3 `daemon/orchestrator.py` — TOUCH MADURO (HermesDaemon.start/shutdown)
```python
from core.scheduler import get_scheduler, TZ_CUIABA
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

class HermesDaemon:
    async def start(self):
        await self._init_db()
        await self._restore_state()
        sched = get_scheduler()
        # Task 2 — métricas 1h (UPSERT idempotente by date+account)
        sched.add_job(self._collect_cobaia_metrics, IntervalTrigger(hours=1, jitter=120),
                      id="cobaia_metrics", replace_existing=True)
        # Task 3a — stop gates 30min (DOUBLE-CHECK; inline no P1-P7 loop body é PRIMARY)
        sched.add_job(self._check_stop_gates, IntervalTrigger(minutes=30, jitter=60),
                      id="cobaia_stop_gates", replace_existing=True)
        # Task 4 — Telegram 19h Cuiabá (DST-safe via CronTrigger timezone)
        sched.add_job(self._send_daily_telegram, CronTrigger(hour=19, minute=0, timezone=TZ_CUIABA),
                      id="cobaia_daily_telegram", replace_existing=True)
        sched.start()
        log.info(f"scheduler started, jobs={[j.id for j in sched.get_jobs()]}")
        await self.run_forever()  # P1-P7 cascade INTACTO

    async def shutdown(self):
        get_scheduler().shutdown(wait=False)
        await self._persist_state()
```

### 5.4 Task 2 — `_collect_cobaia_metrics` (1h, UPSERT idempotente)
```python
async def _collect_cobaia_metrics(self):
    from linkedin.db_utils import _connect
    today = datetime.now(TZ_CUIABA).date().isoformat()
    account = self.settings.linkedin_lab_account
    metrics = {
        "connects_sent": await self._count_connects_today(),
        "accepted": await self._count_accepted_today(),
        "replied": await self._count_replies_today(),
        "viewed": await self._count_profile_views_today(),
        "ban_signals": json.dumps(await self._collect_ban_signals()),
        "compliance_score": await self._calc_compliance_score(),
        "daemon_actions_count": self._actions_count_today,
    }
    with _connect(self.settings.linkedin_db_path) as conn:
        conn.execute("""
            INSERT INTO cobaia_daily_metrics(date,account,connects_sent,accepted,replied,
                viewed,ban_signals,compliance_score,daemon_actions_count)
            VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(date,account) DO UPDATE SET
              connects_sent=excluded.connects_sent, accepted=excluded.accepted,
              replied=excluded.replied, viewed=excluded.viewed,
              ban_signals=excluded.ban_signals, compliance_score=excluded.compliance_score,
              daemon_actions_count=excluded.daemon_actions_count
        """, (today, account, *metrics.values()))
        conn.commit()
    await self._ws_broadcast("cobaia.metrics_update", {"date": today, **metrics})
```

### 5.5 Task 3a — `_check_stop_gates` (fail-closed, 4 gates ordem)
> **CRÍTICO**: manter inline check no `_select_next_task()` P1-P7 ANTES de enqueue (constraint IMPLEMENTATION-PLAN L1191-1204). APScheduler 30min é **double-check fallback**, NÃO substitui inline.

```python
async def _check_stop_gates(self):
    from linkedin.limiter import acceptance_cooldown
    from linkedin.account_profile import challenges_in_last_24h
    try:
        gates = []
        if await self._is_account_burned():
            gates.append(("burned", "account flagged burned"))
        comp = await self._read_compliance_score()
        if comp < 70:
            gates.append(("compliance_low", f"score={comp}"))
        # FONTE CANÔNICA PATCH-014 — proibido recalcular
        accept_rate = acceptance_cooldown().rolling_7d_rate()
        if accept_rate < 0.40:
            gates.append(("acceptance_low", f"rate={accept_rate:.2%}"))
        ch = await challenges_in_last_24h(self.settings.linkedin_lab_account)
        if ch > 2:
            gates.append(("challenges_high", f"count={ch}"))
        if gates:
            gate_name, gate_detail = gates[0]
            await self._pause_warmup(reason=f"{gate_name}:{gate_detail}")
            await self._notify_telegram(f"COBAIA GATE TRIGGERED: {gate_name} ({gate_detail}) — warmup paused")
            await self._ws_broadcast("cobaia.gate_triggered", {"gate": gate_name, "detail": gate_detail})
    except Exception as e:
        # FAIL-CLOSED política F.7: erro → pause
        await self._pause_warmup(reason="gate_check_error")
        await self._notify_telegram(f"COBAIA gate check ERROR (fail-closed pause): {e}")
        raise  # listener captura Sentry
```

### 5.6 Task 4 — `_send_daily_telegram` (CronTrigger 19h + idempotência flag)
```python
async def _send_daily_telegram(self):
    from core.state import get_runtime_state, set_runtime_state
    today_key = datetime.now(TZ_CUIABA).date().isoformat()
    flag_key = f"cobaia.telegram_sent.{today_key}"
    if get_runtime_state(flag_key):
        log.info(f"daily telegram already sent for {today_key}, skip")
        return
    metrics = await self._fetch_daily_metrics(today_key)
    report = self._format_telegram_report_md(metrics)  # Day X/14 + 4 metrics + 4 gates + next
    await self._notify_telegram(report)  # REUSA daemon/orchestrator.py:883
    set_runtime_state(flag_key, True)  # seta APENAS após sucesso
    await self._ws_broadcast("cobaia.day_advanced", {"date": today_key, "report_sent": True})
```

### 5.7 FastAPI lifespan integration (`hermes_api_v2.py`)
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await reconcile_orphaned_runs()  # MERGED existing
    if not daemon_running_standalone():
        sched = get_scheduler()
        register_cobaia_jobs(sched, callable_source=app.state.cobaia_handlers)
        sched.start()
    yield
    if not daemon_running_standalone():
        get_scheduler().shutdown(wait=False)
```

### 5.8 Error handling pattern (TODAS callables)
1. Top-level `try/except Exception` → `log.exception` + sentry via listener (NÃO swallow)
2. Stop gate: fail-closed (`_pause_warmup` ANTES de re-raise)
3. `httpx.AsyncClient(timeout=30)` explícito em call externa
4. `asyncio.wait_for(coro, timeout=120)` se job pode hang >2min
5. `EVENT_JOB_MISSED` listener alerta Telegram após 3 misses consecutivos mesmo `job_id`

### 5.9 Observability hooks F.8 prep
- `runtime_state.scheduler.{job_id}.last_run` + `.last_error` JSON queryable via `GET /api/scheduler/jobs`
- `EVENT_JOB_EXECUTED` computa `duration_s` — persist em `runtime_state` OU promover `scheduler_history` table
- Sentry tags: `job_id`, `scheduled_run_time`, `jobstore` (zero código extra por callable)
- OTel span via `@traced_job` decorator opcional (F.6 auto-instrumentation FastAPI herda context)
- Dashboard widget "Scheduler Health" 3 cards consome `/api/scheduler/jobs`

---

## 6. Migration Checklist

1. **Deps**: editar `requirements.txt` → `apscheduler>=3.11.0,<4.0` + `tzdata>=2024.1`; `ssh hermes-gcp 'source ~/hermes/venv/bin/activate && pip install apscheduler tzdata'` + validar `python -c "from apscheduler.schedulers.asyncio import AsyncIOScheduler; from zoneinfo import ZoneInfo; print(ZoneInfo('America/Cuiaba'))"`
2. **Config**: adicionar em `config.py HermesSettings` campos `scheduler_misfire_grace_time=300`, `scheduler_jitter_seconds=120`, `scheduler_timezone='America/Cuiaba'`, `linkedin_lab_account`, `hermes_internal_token` (via pydantic-settings MERGED-013)
3. **Migration SQL**: criar `migrations/0XX_cobaia_warmup_tables.sql` idempotente (`PRAGMA table_info` guarded) — `cobaia_daily_metrics(PRIMARY KEY date,account)` + `cobaia_actions_log` + `cobaia_pause_events` + `ALTER warmup_state ADD COLUMN paused INT DEFAULT 0 + paused_reason TEXT`; aplicar via `scripts/migrate.py` PC + ssh VM
4. **Helpers**: `linkedin/account_profile.challenges_in_last_24h()` rolling window + `linkedin/limiter.acceptance_cooldown()` exposto público (FONTE CANÔNICA PATCH-014)
5. **Singleton scheduler**: criar `core/scheduler.py` (~60 linhas) com `get_scheduler()` + `_on_job_event` listener; unit test `tests/test_scheduler_singleton.py` garante mesma instance
6. **Callables daemon**: implementar `_collect_cobaia_metrics` + `_check_stop_gates` + `_send_daily_telegram`; **MANTER inline `_check_stop_gates` no `_select_next_task()` P1-P7** (constraint L1191-1204) — APScheduler 30min é double-check
7. **Wire-up**: `HermesDaemon.start()` registra 3 jobs via `add_job(..., replace_existing=True)` ANTES de `run_forever()`; `shutdown()` chama `scheduler.shutdown(wait=False)` ANTES de `_persist_state()`
8. **Endpoints**: `vm_api/routes.py` adicionar `GET /api/scheduler/jobs` (job_id + next_run_time + last_run + last_error) + `GET/POST /api/cobaia/*` (7 endpoints) + `POST /api/cobaia/daily-report/preview` (bypassa scheduler); auth Bearer token
9. **Smoke test local PC**: pytest `tests/test_scheduler.py` com freezegun fast-forward 19h Cuiabá → assert `_send_daily_telegram` called 1x + flag set; mock `_eval_4_gates` raise → assert `_pause_warmup` ANTES re-raise (fail-closed); idempotência flag (2x mesma data → 1x Telegram)
10. **Deploy VM**: `/hermes-deploy` seletivo (`daemon/orchestrator.py` + `core/scheduler.py` + `config.py` + `linkedin/*.py` + `migrations/` + `vm_api/routes.py`); SSH dry-run → rsync → `systemctl --user restart hermes-daemon` → health check `curl http://VM:8420/api/scheduler/jobs` deve retornar 3 jobs com `next_run_time` futuro
11. **Prod canary 2h**: `ssh hermes-gcp 'journalctl --user -fu hermes-daemon -n 100 | grep -E "(scheduler|cobaia)"'` aguardar (a) 3 jobs registered no startup, (b) `cobaia_stop_gates` executou 4x em 2h, (c) `cobaia_metrics` executou 2x em 2h, (d) zero ERROR no listener; abort+rollback se falha
12. **Regression gate**: `bash scripts/validate_implementation.py phases A B C D E` mantém **20/22 PASS** + nova phase F.7 check (`GET /api/scheduler/jobs` retorna `len==3` + `last_error is None`); se cair <20 → ROLLBACK + fallback D-híbrido

---

## 7. Fallback Option

### 7.1 D-híbrido — asyncio loop check 60s inline daemon (Tasks 2+3a) + systemd --user timer VM (Task 4 Telegram)
**Trigger fallback**: APScheduler 3.x bug crítico durante F.7 — e.g. `AsyncIOScheduler` conflito event loop com loops MERGED-015 `spawn()`, `tzdata` Windows fallback flake, `EVENT_JOB_MISSED` listener race.

**Rationale**: zero dep nova, zero touch APScheduler-specific code, preserva constraint F.7 stop gate inline check L1191-1204. Custo: +1 sessão F.7 reescrever 3 callables como inline loop checks + perde observability nativa (precisa instrumentação manual `sentry_sdk` em cada callable).

**Implementação fallback**:
- Tasks 2+3a permanecem inline no `daemon/orchestrator.py` loop body via `core.state.spawn()` wrapper (MERGED-015) + `datetime.now(tz).hour/minute` check cada iter — pattern já estabelecido em `loops/linkedin_scheduler.py` 30s poll
- Task 4 Telegram 19h via `systemd --user` timer `hermes-cobaia-telegram.timer OnCalendar='19:00:00' Persistent=true` (alinha DEPLOY-FASE-F.md §2 canonical `hermes-warmup.timer`)

**Migration path B → D-híbrido** (se rollback necessário): ver §11 Rollback Plan.

---

## 8. Long-term Option

**Manter Opção B (APScheduler 3.11.x) → migração futura quando 4.x estabilizar (post-2026)**

**Rationale**: APScheduler 3.11.x sustenta F.7+F.8+F.9 sem rebuild — F.8 Cost&Perf consume `EVENT_JOB_EXECUTED` histogram zero-config, F.9 Pipeline Studio UI builder consome `add_job/remove_job/modify_job` API programática (vs crontab que exigiria parser texto frágil). Migração 4.x é mecânica — classes movidas `apscheduler.AsyncScheduler` top-level, sync interfaces removidas já não usamos (Hermes async-only).

**Trigger pra reavaliar (gatilho objetivo)**:
- Se Hermes escalar multi-tenant (cada owner = 1 cobaia paralela) → avaliar **Temporal.io** (durable execution + workflow versioning + retry policies declarativas + UI built-in)
- Se 10+ schedulers concurrent + distributed coordination necessária → Temporal justifica dep mais pesada
- Se APScheduler 4.x estável (provavelmente 2027) → migração mecânica

**Solo owner F.7→F.9 NÃO precisa** — Opção B cobre estendido futuro.

---

## 9. Risk Mitigation (Top-5 Blockers Cross-Verdicts)

### Blocker 1: Touch `daemon/orchestrator.py` P1-P7 cascade regression risk (score 6/10)
**Mitigação tripla**:
- (a) `add_job()` ANTES de `await run_forever()` preserva loop body INTACTO
- (b) Jobs são métodos privados isolados que NÃO modificam `decide_next_action()` if/elif cascade nem circuit breaker (`consecutive_errors>=5`)
- (c) Pre-deploy obrigatório `bash scripts/validate_implementation.py phases A B C D E` **20/22 PASS gate**, se cair <20 → ROLLBACK imediato + fallback Opção D-híbrido

### Blocker 2: State coupling singleton `acceptance_cooldown` PATCH-014 vs disk drift
**Mitigação**: APScheduler in-process **ELIMINA** esse blocker por design (jobs acessam `self.limiter` direto, zero IPC). Cuidado oposto: garantir que callables NÃO instanciem nova `AccountProfile.load()` ou `Settings()` — reusar instância via `self.account_profile` / `self.settings`. Code review checklist obrigatório nas 3 callables.

### Blocker 3: MemoryJobStore perde jobs em restart + task mid-flight perdida em SIGTERM
**Mitigação tripla**:
- (a) `HermesDaemon.start()` re-registra TODOS jobs com `replace_existing=True` a cada boot (jobs vivem como código, idempotência total)
- (b) `misfire_grace_time=300` + `coalesce=True` garante CronTrigger 19h dispara assim que sobe se restart 18:55-19:05
- (c) `hermes-daemon.service` systemd `Restart=always RestartSec=10 StartLimitBurst=5 OnFailure=hermes-alert@telegram.service` (DEPLOY-FASE-F.md §2)
- Aceitar limitação: Task 4 mid-flight crash entre Telegram POST 200 e `set_runtime_state` flag pode resultar em duplo-envio próximo boot (window <100ms, infrequente)

### Blocker 4: APScheduler 4.x alpha — lock-in 3.11.x
**Mitigação**: pin explícito `apscheduler>=3.11.0,<4.0` em `requirements.txt` + GUARDRAILS entry "🚫 NUNCA upgradar pra 4.0aX em produção". Migração futura mecânica (2027+).

### Blocker 5: Single-process — daemon crash não-recuperado = 3 jobs param silenciosamente
**Mitigação tripla**:
- (a) `hermes-daemon.service` systemd `Restart=always` + `OnFailure` Telegram alert
- (b) `vm_watchdog_loop` PC-side detecta `/api/health` stale >5min + dispara `systemctl --user restart hermes-daemon` remoto via SSH
- (c) Job heartbeat opcional: cada execução escreve `runtime_state.scheduler_heartbeat=now()` — vm_watchdog alerta Telegram se stale >2h

---

## 10. Success Criteria F.7 (8 critérios mensuráveis)

1. **Smoke prod**: `GET /api/scheduler/jobs` retorna exatamente **3 jobs** (`cobaia_metrics`, `cobaia_stop_gates`, `cobaia_daily_telegram`) com `next_run_time > now()` + `last_error is null` APÓS `systemctl restart hermes-daemon`
2. **Task 2 (métricas 1h)**: 24h streak sem skip — `SELECT COUNT(*) FROM cobaia_daily_metrics WHERE date=today AND account=lab_account >= 1` + `runtime_state.scheduler.cobaia_metrics.last_run.ts > now()-3700s` a qualquer momento
3. **Task 3a (stop gates)**: inject `compliance_score=65` em `cobaia_daily_metrics` + aguardar <30min → `warmup_state.paused=1` + `paused_reason='compliance_low:score=65'` + Telegram alert recebido + WS `cobaia.gate_triggered` event capturado dashboard <60s do trigger
4. **Task 4 (Telegram 19h)**: 7d streak entrega 19:00-19:02 Cuiabá (jitter aceitável); `runtime_state.cobaia.telegram_sent.{date}` retorna `True` últimos 7 dias consecutivos; zero duplo-envio mesma data (idempotência flag)
5. **Regression suite preservada**: `bash scripts/validate_implementation.py phases A B C D E` mantém **20/22 PASS** (zero regressão) + nova phase F.7 PASS
6. **Daemon heartbeat**: P1-P7 loop body heartbeat **<60s preservado** (medido via `daemon_decisions.timestamp` delta consecutivas) — APScheduler in-process NÃO bloqueia main loop
7. **Fail-closed verificado**: mock `_eval_4_gates` raise Exception em test prod → `warmup_state.paused=1` + Telegram alert + zero ações P1-P7 enfileiradas mesmo `gate_check_error` (política F.7)
8. **Observability F.5/F.8 prep**: `EVENT_JOB_ERROR` captura via `sentry_sdk` verificada (force erro em test job, query Sentry MCP `list_events tag:job_id` retorna 1 evento) + `duration_s` persistido `runtime_state` queryable via `/api/scheduler/jobs/stats?last=7d`

---

## 11. Rollback Plan

**Trigger rollback**: phases A-E regression cai <20/22 PASS, daemon não sobe (`sched.start()` RuntimeError), Telegram duplo-envio repetido (idempotência flag falha), OU stop gate false-positive pause warmup sem trigger real >2x/dia.

**Procedimento (15-30min, ZERO perda warmup state cobaia)**:

1. **Pause scheduler sem revert código**: `curl -X DELETE http://VM:8420/api/scheduler/jobs/cobaia_metrics` (idem `cobaia_stop_gates`, `cobaia_daily_telegram`) — APScheduler suporta `remove_job()` runtime, daemon continua P1-P7 normal. Buy time pra investigar.

2. **Git revert seletivo**: `git revert <commit_sha_F7_scheduler>` no PC — reverte `daemon/orchestrator.py` start/shutdown changes + `core/scheduler.py` removido + `vm_api/routes.py` `/api/scheduler/*` removido. **PRESERVAR**: `migrations/0XX_cobaia_warmup_tables.sql` + `linkedin/account_profile.challenges_in_last_24h()` + `linkedin/limiter.acceptance_cooldown()` exposed (valor independente do scheduler, reaproveitam fallback D-híbrido).

3. **DB state preservation**: `cobaia_daily_metrics` + `cobaia_actions_log` + `cobaia_pause_events` + `warmup_state.paused/paused_reason` **PERMANECEM** (NÃO rodar migration rollback). Estado warmup cobaia 14d preservado intacto — dia atual, ações executadas, gates triggered history tudo retido.

4. **Deploy rollback VM**: `/hermes-deploy` seletivo `daemon/` + `core/` + `vm_api/` → `systemctl --user restart hermes-daemon` → health check `curl http://VM:8420/api/health` 200 OK + daemon P1-P7 cascade ativo.

5. **Bridge enquanto fallback não implementado**:
   - Task 2: `ssh hermes-gcp 'cd ~/hermes && venv/bin/python -c "from daemon.orchestrator import HermesDaemon; import asyncio; asyncio.run(HermesDaemon().collect_metrics_once())"'` ad-hoc 1x/dia
   - Task 3a: JÁ roda INLINE no loop body (constraint L1191-1204 garante independente APScheduler) — funcional sem ação
   - Task 4: `curl -X POST http://VM:8420/api/cobaia/daily-report/send` manual 19h (cron temporary `0 19 * * * curl ...` aceitável)

6. **Migrar pra fallback D-híbrido**: nova sessão F.7 dedicada implementa Tasks 2+3a via asyncio loop check 60s inline (pattern `loops/linkedin_scheduler.py`) + Task 4 via systemd `--user` timer `hermes-cobaia-telegram.timer`. Estimate +1 sessão F.7.

7. **Audit trail**: criar `.claude/F7-ROLLBACK-LOG.md` documentando trigger, decisão, timeline, learnings — alimenta retrospectiva F.future + `memory_save type='architecture'`.

**Garantia**: `warmup_state.paused`, `cobaia_daily_metrics` rows, `cobaia_actions_log` **NUNCA destruídos** — owner Caio NÃO perde dias warmup acumulados. Pior caso: 1 dia sem Telegram report enquanto fallback implementa (aceitável vs cobaia ban risk de manter scheduler quebrado).

---

## 12. Cross-References

- **F.3.4 discovery commit**: `c3c24d3` (2026-06-10) — grep zero matches `APScheduler|crontab|celery|cron` em `daemon/orchestrator.py`
- **Memory entries**:
  - `mem_mq7fh8qa` — Hermes deps inventory (PC requirements.txt 13 deps, VM extras)
  - `mem_mq7eyrio` — F.7 task slicing 4→6 sessões + schedule infra dependency
- **PLAN.md**: bloco "🚨 DECISÃO ARQUITETURAL PENDENTE" L393-422 (origem trigger)
- **IMPLEMENTATION-PLAN-FASE-F.md**: L1149-1245 (F.7 task contracts) + L1191-1204 (Task 3a inline constraint)
- **GUARDRAILS.md**: L12-16 (LinkedIn/patchright VM-only), L99-112 (VM deps), L196-204 (config.py canonical MERGED-013), L375-389 (core/brain.py F.6 ToolRegistry)
- **DEPLOY-FASE-F.md**: §2 `hermes-warmup.timer` canonical pattern (alinha fallback D-híbrido systemd timer)
- **Workflow run**: `.claude/workflows/f7-schedule-arch-analysis.js` (48 agents parallel, 8 alternativas × 4 lenses verdict)
- **Code refs**:
  - `core/state.py:75` — `spawn()` wrapper MERGED-015
  - `core/state.py:119-156` — `runtime_state` table (reusado pra `scheduler.{job_id}.last_run`)
  - `daemon/orchestrator.py:307-464` — main loop P1-P7 (INTACTO)
  - `daemon/orchestrator.py:883` — `_notify_telegram` (REUSADO pela Task 4)
  - `loops/linkedin_scheduler.py:44-157` — modelo poll pattern (fallback D-híbrido)
  - `core/limiter.py` — singleton pattern Limiter (modelo `core/scheduler.py`)
  - `linkedin/db_utils._connect` — WAL + busy_timeout=30s obrigatório (MERGED-005)

---

## 13. Approval Checklist (owner DEVE marcar antes F.7 session)

- [ ] Owner leu **§2 Sumário Executivo** + **§4 Análise Detalhada Primary Option (B)**
- [ ] Owner confirma **dependencies novas acceptable**: `apscheduler>=3.11.0,<4.0` (~600KB) + `tzdata>=2024.1` (~5MB) — total 13 deps → 14 (+10% venv size)
- [ ] Owner aceita **f7_sessions_impact**: base 6 sessões → **6 (zero overhead Primary)** OU **7 (+1 se fallback D-híbrido necessário)**
- [ ] Owner ciente **fallback option D-híbrido** se APScheduler 3.x mostrar bug crítico (asyncio loop check 60s inline + systemd timer) — preserva constraint L1191-1204
- [ ] Owner ciente **regression risk MÉDIO** (6/10) por touch 6 mature files — gate `bash scripts/validate_implementation.py phases A B C D E` 20/22 PASS **INVIOLÁVEL**
- [ ] Owner ciente **long-term path**: manter 3.11.x até 4.x estável (2027+) OU migrar Temporal.io se multi-tenant futuro
- [ ] Owner ciente **rollback garante zero perda warmup state cobaia** (§11) — DB rows preservadas, only code reverted
- [ ] Owner aprova **constraint INVIOLÁVEL Task 3a**: stop gate check INLINE no `_select_next_task()` P1-P7 daemon loop body (primary) + APScheduler 30min (double-check fallback) — NUNCA crontab/scheduler-only pra gate enforcement

---

**Decisão tomada**: Opção B — APScheduler in-process daemon. Aguarda owner approval §13 antes de iniciar F.7 session dedicada.
