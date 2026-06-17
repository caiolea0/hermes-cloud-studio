# F.7 Cobaia Live Ops — Owner Pre-launch Actions

> **Status 2026-06-17**: F.7 CHAPTER CLOSED via 6 sub-sessions + P5 hardening.
> Código + infra prontos. Falta apenas ações manuais owner abaixo antes ativar warmup live.
> Cross-ref: `.claude/F7-PREP.md` (decisões D1-D10) + `.claude/PLAN.md` F.7 block.

---

## 1. LinkedIn Cobaia Account Setup (D1 manual)

### 1.1 Conta nova (já em andamento — Task #13 PLAN.md owner)
- [ ] Conta LinkedIn criada com nome "Caio Leão" (real owner — não disposable)
- [ ] Email real validado (não temp-mail)
- [ ] Telefone real validado (LinkedIn obriga 2FA SMS)
- [ ] Foto perfil profissional (não default avatar)
- [ ] Headline + about + experience preenchidos (badge **All-Star**)

### 1.2 Seed orgânico (~10 dias manual ANTES Hermes ativar)
- [ ] 50+ conexões seed manual (owner conecta 5/dia × 10 dias)
- [ ] 2-4 posts orgânicos publicados (não vendendo — value-first content)
- [ ] Interagir com feed 5-10 min/dia (likes + comments curtos)
- [ ] Profile views >20 antes ativar (sinal natural)

### 1.3 Cobaia profile final check
- [ ] Badge "All-Star" visível
- [ ] >50 conexões reais
- [ ] Profile completeness 100%
- [ ] Zero warnings LinkedIn

---

## 2. Credenciais setup (commands)

### 2.1 Hunter.io API key (P5 — antes warmup)
```powershell
# Pre-req: conta hunter.io free tier (25 verifies/mo)
# Get key: https://hunter.io/api-keys
powershell -ExecutionPolicy Bypass -File scripts\setup_hunter_key.ps1
```
- [ ] Script runs sem erro
- [ ] Smoke `/v2/account` 200 OK
- [ ] plan_name = "free" (ou superior)
- [ ] calls_available > 0

### 2.2 COBAIA_LI_AT (após D1.3 cobaia profile pronto)
Manual extract:
1. Chrome login conta cobaia → linkedin.com
2. DevTools (F12) → Application → Cookies → linkedin.com
3. `li_at` row → copy **Value** field (string longa)
4. Update `.env` PC + VM:
   ```
   COBAIA_LI_AT=AQEDA... (paste value)
   COBAIA_ACCOUNT_EMAIL=email-cobaia@dominio.com
   COBAIA_ACCOUNT_TYPE=free
   ```
5. SSH VM atualizar `~/.hermes/.env` mesmo formato

### 2.3 Telegram bot (já configurado F.7 C4)
- [x] HERMES_TELEGRAM_BOT_TOKEN setado (commit 3e86c7c)
- [x] HERMES_TELEGRAM_CHAT_ID setado
- [x] Smoke Telegram send: OK

---

## 3. VM Deployment Validate (pre-flight)

### 3.1 Pre-flight endpoint
```bash
curl -H "X-Hermes-Token: $HERMES_AUTH_TOKEN" \
  http://localhost:55000/api/cobaia/preflight | jq
```
Esperado output:
- `linkedin_session.valid: true`
- `health.status: "ok"`
- `rate_limits.window_open: true`
- `cobaia_warmup.ready: true`
- `all_pass: true`

### 3.2 Systemd timer cobaia (F.4.4 quarantine)
```bash
ssh hermes-gcp@136.115.74.69
systemctl --user status hermes-skill-quarantine.timer
# expected: Active: active (waiting) + Next: <date> 04:00 UTC
```

### 3.3 Sentry SDK cobaia-live env
```bash
curl -H "X-Hermes-Token: $HERMES_AUTH_TOKEN" \
  http://localhost:55000/api/cobaia/sentry-env
# expected: {"environment": "cobaia-live", "dsn_configured": true}
```

### 3.4 Hunter quota check
```bash
curl -H "X-Hermes-Token: $HERMES_AUTH_TOKEN" \
  http://localhost:55000/api/cobaia/hunter-usage
# expected: {"status": "ok", "plan_name": "free", "calls_available": >0}
```

---

## 4. Day-1 Launch Sequence

### 4.1 Start warmup (após 3.x all pass)
```bash
curl -X POST -H "X-Hermes-Token: $HERMES_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"account_handle": "cobaia"}' \
  http://localhost:55000/api/linkedin/cobaia/start-warmup
```
Esperado output:
- `status: "lurking"` (D2.1 default phase day 0)
- `current_day: 0`
- `phase: "lurking"`

### 4.2 Monitor dashboard 30min
- [ ] Abrir dashboard → cobaia page
- [ ] Header card mostra: status=lurking + day=0/14
- [ ] Timeline 24h aparece (vazio inicialmente)
- [ ] KPI section: 0 connects + 0 replies (esperado)
- [ ] Activity feed log inicia

### 4.3 Verify daily metrics tracking (24h after)
```bash
curl -H "X-Hermes-Token: $HERMES_AUTH_TOKEN" \
  http://localhost:55000/api/linkedin/cobaia/metrics?days=1 | jq
# expected: daily[0] row presente com views_count + connects_sent etc
```

### 4.4 Emergency stop tested (PRE-ATIVAR — não esperar emergency real)
```bash
# Stop test
curl -X POST -H "X-Hermes-Token: $HERMES_AUTH_TOKEN" \
  http://localhost:55000/api/linkedin/cobaia/pause
# Resume test
curl -X POST -H "X-Hermes-Token: $HERMES_AUTH_TOKEN" \
  http://localhost:55000/api/linkedin/cobaia/resume
```
- [ ] Botão UI cobaia page → Pausar Tudo funciona
- [ ] Botão UI → Retomar funciona
- [ ] Telegram alerta recebido (verify chat)

---

## 5. Week-1 Monitoring (D6 PIVOT — autonomous)

Owner NÃO precisa abrir dashboard cada dia. Bug Export + Telegram digest cobrem:

### 5.1 Daily digest (automático 09h BRT)
- [ ] Email digest chega chat cleao.mkt@gmail.com com:
  - Daily metrics yesterday
  - Open alerts count
  - Sentry issues new
  - Autotune triggers history

### 5.2 Bug export sob demanda
```bash
curl -H "X-Hermes-Token: $HERMES_AUTH_TOKEN" \
  "http://localhost:55000/api/cobaia/bug-export?hours=24&format=markdown" \
  -o bug-export-$(date +%Y%m%d).md
```

### 5.3 Auto-tune watch (D10 reactive)
- [ ] Após day 7 (ramp phase): autotune-history endpoint começa popular
- [ ] Owner review PRs skill_proposals criadas
- [ ] Quarantine cron 04h UTC daily detecta regressões

---

## 6. Red flags (PARAR imediato)

### 6.1 LinkedIn challenge / 429
- Health endpoint reporta `status: "challenge"` ou `"cooldown"`
- **Action**: NÃO forçar — aguardar 30min+ (cooldown automático). Se persistir 2h → revisar conta LinkedIn manual.

### 6.2 Auto-pause N=3 erros
- Telegram alert "cobaia auto-paused: 3 consecutive errors"
- **Action**: Owner abre dashboard → activity feed → identifica causa. Resume APENAS após investigar.

### 6.3 Sentry alert burst
- 5+ issues novos em 1h → algo quebrou
- **Action**: Bug export 1h → analisar → pause se necessário.

### 6.4 Hunter quota esgotada
- `/api/cobaia/hunter-usage` retorna `calls_available: 0`
- **Action**: Cache 30d cobre. Upgrade plano OU rodar verify só novos emails.

---

## 7. Cleanup pós-warmup completo (day 14)

- [ ] Bug export final 14d → archive
- [ ] Daily metrics aggregate → exportar CSV via `/api/observability/csv-export`
- [ ] Owner review KPIs vs D3 thresholds:
  - Reply rate >8%? → success channel
  - Connect accept >20%? → healthy
  - Profile view→connect >3%? → conversion OK
- [ ] Decisão next phase: scale up daily caps OR add second skill

---

**Última atualização**: 2026-06-17 (P5 hardening closeout)
**Owner**: Caio Leão (cleao.mkt@gmail.com)
**Cross-ref**: `.claude/F7-PREP.md` + `.claude/PLAN.md` F.7 CHAPTER CLOSED block
