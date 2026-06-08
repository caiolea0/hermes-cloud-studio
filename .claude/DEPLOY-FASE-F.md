# Hermes Fase F — Procedure Consolidado de Deploy PC→VM

> **Escopo:** procedure determinístico de deploy PC→VM para os 9 chapters da Fase F (F.1→F.9).
> Cobre: systemd units novas, migrations ordem, rollback, backup `~/.hermes/data/`, health checks pós-deploy.
> **Fonte canônica:** este arquivo + `.claude/skills/hermes-deploy/SKILL.md` (procedure genérico).
> Este doc ESTENDE a skill com matriz por chapter + units novas + migrations.
> **Audiência:** owner solo + futuras sessões Claude executando `/hermes-deploy` durante F.x.
> **Guardrail #0 (INVIOLÁVEL):** zero `patchright`/`playwright`/binários browser no PC. Stack stealth vive APENAS na VM.

---

## 0. Topologia + Constantes de Deploy

| Item | Valor | Notas |
|---|---|---|
| VM host | `hermes-gcp@136.115.74.69` | GCP e2-medium, Ubuntu 22.04 |
| VM home | `/home/hermes-gcp` (aka `~`) | |
| VM data dir | `~/.hermes/data/` | SQLite DBs + state JSON + backups |
| VM skills dir | `~/.hermes/skills/` | YAMLs sincronizados via scp |
| VM logs dir | `~/.hermes/logs/` | api.log, daemon.log, channels/*.log |
| VM backups dir | `~/.hermes/backups/{timestamp}/` | snapshot pré-deploy |
| VM API port | `8500` (via tunnel cloudflared) | |
| PC API port | `8000` (FastAPI uvicorn) | |
| PC backend root | `D:/dev-projects/main/hermes-cloud-studio/` | |
| Deploy log | `.claude/.last-deploy.json` | rastreia mtime por arquivo |
| Health endpoint VM | `GET http://localhost:8500/api/hermes/status` | requer `X-Hermes-Token` |
| Health endpoint PC | `GET http://localhost:8000/api/health` | sem auth |
| Validate gate | `python scripts/validate_implementation.py --phase A B C D E` | baseline 20/22 PASS |
| SSH key | `~/.ssh/hermes-gcp` (PC) | autenticação keyfile, sem senha |

---

## 1. Matriz Chapter → Targets de Deploy

Para cada chapter F.x, esta tabela define **o que** sincronizar, **onde** roda (PC/VM/ambos), e **quais units** restartar. Use-a como input do passo 1 de `/hermes-deploy`.

| Chapter | Side | Arquivos PC→VM | Units VM restart | Units PC restart | Migrations | Deploy obrigatório? |
|---|---|---|---|---|---|---|
| **F.1** Gap Audit | PC-only | `.claude/skills/hermes-frontend-gap/`, `.claude/FRONTEND-GAP.md`, `.claude/commands/hermes-frontend-gap.md` | — | — | — | NÃO (zero código produção) |
| **F.2** Mission Control RT | PC+VM | `dashboard/`, `dashboard/components/`, `loops/sync.py` (broadcast WS), `api/daemon.py` (endpoints subsystems+pause+resume) | `hermes-api` | uvicorn reload | — | SIM (loops + api/daemon.py mudam) |
| **F.3** Lab Cockpit | PC+VM (lab pré-prod) | `linkedin/lab/`, `api/lab.py` (novo), `dashboard/lab/`, `scripts/lab_runner.py` | `hermes-api` | uvicorn reload | `lab_runs` table (PC + VM) | SIM |
| **F.4** Auto-Skill Loop W3 | PC+VM | `app/workflows/hermes-skill-forge.js`, `intelligence/skill_proposer.py`, `api/skills.py` (proposals endpoints), `dashboard/skills/`, sync `~/.hermes/skills/` automático | `hermes-api`, `hermes-daemon` | uvicorn reload | `skill_proposals` table (PC) + `skill_audit_log` (VM) | SIM |
| **F.5** MCP Discovery+Integration | PC+VM | `mcps/contextforge/` (gateway VM), `mcps/hermes-linkedin/`, `mcps/hermes-prospects/`, `mcps/hermes-skills/`, `.mcp.json` | `hermes-mcp-gateway` (NEW unit), `hermes-api` | restart MCP clients | — | SIM (NOVA unit systemd) |
| **F.6** Cérebro/Brain | PC+VM | `intelligence/brain.py`, `api/brain.py`, `dashboard/brain/`, `loops/brain_loop.py` | `hermes-brain` (NEW unit), `hermes-api` | uvicorn reload | `brain_decisions`, `brain_intents` (PC) | SIM (NOVA unit systemd) |
| **F.7** Cobaia Live Ops | VM-heavy | `linkedin/warmup/`, `channels/email_warmup.py`, `intelligence/cobaia_qualifier.py`, `scripts/warmup_daily.py` | `hermes-api`, `hermes-daemon`, `hermes-warmup` (NEW unit) | — | `cobaia_runs`, `warmup_events` (VM) | SIM (NOVA unit + cron-like timer) |
| **F.8** Observability | PC+VM | `observability/`, `api/observability.py`, `dashboard/observability/`, `mcps/sentry-bridge/` (opcional), `loops/metrics_emitter.py` | `hermes-api`, `hermes-daemon`, `hermes-otel-collector` (NEW unit, opcional) | uvicorn reload | `metric_snapshots` (PC + VM, ring buffer 7d) | SIM |
| **F.9** Pipeline Studio | PC-heavy | `dashboard/pipeline/`, `app/pipeline_designer/`, `api/pipeline.py`, `intelligence/pipeline_executor.py`, sync de pipelines compilados pra VM | `hermes-api` | uvicorn reload | `pipelines`, `pipeline_runs`, `pipeline_steps` (PC) | SIM |

**Legenda Side:**
- **PC-only**: nenhum `scp`/`rsync` pra VM, nenhum systemctl restart na VM.
- **PC+VM**: roda em ambos, requer sync + restart.
- **VM-heavy**: lógica principal na VM, PC apenas hospeda UI/dashboard.

---

## 2. Systemd Units Novas (Fase F)

Todas usam `--user` scope (não-root) em `~/.config/systemd/user/`. Habilitar via `systemctl --user enable <unit> && systemctl --user start <unit>`. Persistência cross-reboot via `loginctl enable-linger hermes-gcp` (já configurado, não tocar).

### 2.1 `hermes-mcp-gateway.service` (criado em F.5)

```ini
# ~/.config/systemd/user/hermes-mcp-gateway.service
[Unit]
Description=Hermes MCP Gateway (ContextForge)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/hermes-gcp/mcps/contextforge
ExecStart=/usr/bin/python3 -m mcp_contextforge.server --config /home/hermes-gcp/.hermes/mcp-gateway.yaml
Restart=on-failure
RestartSec=5
StandardOutput=append:/home/hermes-gcp/.hermes/logs/mcp-gateway.log
StandardError=append:/home/hermes-gcp/.hermes/logs/mcp-gateway.err
Environment="HERMES_AUTH_TOKEN_FILE=/home/hermes-gcp/.hermes/auth_token"

[Install]
WantedBy=default.target
```

**Health check pós-deploy:**
```bash
ssh hermes-gcp@136.115.74.69 "systemctl --user is-active hermes-mcp-gateway && curl -sf http://localhost:8600/healthz"
```

### 2.2 `hermes-brain.service` (criado em F.6)

```ini
# ~/.config/systemd/user/hermes-brain.service
[Unit]
Description=Hermes Brain (intent classifier + decision loop)
After=network-online.target hermes-api.service
Requires=hermes-api.service

[Service]
Type=simple
WorkingDirectory=/home/hermes-gcp
ExecStart=/usr/bin/python3 -m intelligence.brain_loop
Restart=on-failure
RestartSec=5
StandardOutput=append:/home/hermes-gcp/.hermes/logs/brain.log
StandardError=append:/home/hermes-gcp/.hermes/logs/brain.err
Environment="HERMES_BRAIN_OLLAMA_HOST=http://136.115.74.69:11434"

[Install]
WantedBy=default.target
```

**Health check:** `curl -sf http://localhost:8500/api/brain/health` (endpoint criado em F.6).

### 2.3 `hermes-warmup.service` + `hermes-warmup.timer` (criados em F.7)

```ini
# ~/.config/systemd/user/hermes-warmup.service
[Unit]
Description=Hermes Cobaia Warmup (daily run)
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/home/hermes-gcp
ExecStart=/usr/bin/python3 scripts/warmup_daily.py
StandardOutput=append:/home/hermes-gcp/.hermes/logs/warmup.log
StandardError=append:/home/hermes-gcp/.hermes/logs/warmup.err
```

```ini
# ~/.config/systemd/user/hermes-warmup.timer
[Unit]
Description=Trigger hermes-warmup daily at 09:30 BRT (12:30 UTC)

[Timer]
OnCalendar=*-*-* 12:30:00
Persistent=true

[Install]
WantedBy=timers.target
```

**Habilitar timer:**
```bash
ssh hermes-gcp@136.115.74.69 "systemctl --user daemon-reload && systemctl --user enable --now hermes-warmup.timer"
```

**Verificar próximo disparo:** `ssh hermes-gcp ... "systemctl --user list-timers hermes-warmup.timer"`.

### 2.4 `hermes-otel-collector.service` (OPCIONAL, criado em F.8 se decisão for self-host OTel)

```ini
# ~/.config/systemd/user/hermes-otel-collector.service
[Unit]
Description=Hermes OpenTelemetry Collector
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/otelcol --config=/home/hermes-gcp/.hermes/otel-config.yaml
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

**Skip se F.8 decidir usar Sentry MCP direto** (sem collector local).

### 2.5 Units Existentes (NÃO tocar config, apenas restart)

| Unit | Função | Restart trigger |
|---|---|---|
| `hermes-api` | FastAPI VM (`hermes_api_v2.py`) | qualquer mudança em `api/`, `vm_api/`, `core/`, `channels/` |
| `hermes-daemon` | daemon orquestrador (loops/) | mudança em `daemon/`, `loops/` |
| `hermes-tunnel` | cloudflared tunnel | NÃO restartar em deploy de código (afeta dashboard upstream) |
| `hermes-mcp-control` | MCP TS `hermes-control` | mudança em `mcps/hermes-control/` |

---

## 3. Migrations VM — Ordem Canônica

**Regra de ouro:** migrations rodam **DEPOIS** do backup `~/.hermes/data/` e **ANTES** do restart de services. Ordem importa: dependências FK primeiro.

### 3.1 Convenção de nomenclatura

```
migrations/
  2026_06_linkedin_full.sql          # existente (baseline)
  2026_07_f3_lab_runs.sql            # F.3 — lab_runs (PC + VM)
  2026_07_f4_skill_proposals.sql     # F.4 — PC only
  2026_07_f4_skill_audit_log.sql     # F.4 — VM only
  2026_07_f6_brain_decisions.sql     # F.6 — PC
  2026_07_f6_brain_intents.sql       # F.6 — PC
  2026_07_f7_cobaia_runs.sql         # F.7 — VM
  2026_07_f7_warmup_events.sql       # F.7 — VM
  2026_08_f8_metric_snapshots.sql    # F.8 — PC + VM
  2026_08_f9_pipelines.sql           # F.9 — PC
  2026_08_f9_pipeline_runs.sql       # F.9 — PC
  2026_08_f9_pipeline_steps.sql      # F.9 — PC
```

### 3.2 Ordem de execução por chapter

| Chapter | DB target | Ordem SQL files | Pre-check |
|---|---|---|---|
| F.3 | PC: `hermes_local.db`<br>VM: `~/.hermes/data/command_center.db` | `2026_07_f3_lab_runs.sql` (ambos) | `SELECT name FROM sqlite_master WHERE name='lab_runs'` → vazio |
| F.4 | PC: `hermes_local.db`<br>VM: `~/.hermes/data/command_center.db` | PC: `2026_07_f4_skill_proposals.sql`<br>VM: `2026_07_f4_skill_audit_log.sql` | tabela `skills` existe (FK) |
| F.6 | PC: `hermes_local.db` | `2026_07_f6_brain_intents.sql` → `2026_07_f6_brain_decisions.sql` (FK intent_id) | tabela `prospects` existe (FK em decisions) |
| F.7 | VM: `~/.hermes/data/command_center.db` | `2026_07_f7_cobaia_runs.sql` → `2026_07_f7_warmup_events.sql` (FK run_id) | `linkedin_full` tabelas existem (FK) |
| F.8 | PC + VM | `2026_08_f8_metric_snapshots.sql` (ambos) | — |
| F.9 | PC: `hermes_local.db` | `2026_08_f9_pipelines.sql` → `2026_08_f9_pipeline_runs.sql` (FK pipeline_id) → `2026_08_f9_pipeline_steps.sql` (FK run_id) | — |

### 3.3 Helper: aplicar migration VM

```bash
# Dry-run (lê apenas — verifica sintaxe + schema atual)
ssh hermes-gcp@136.115.74.69 "sqlite3 ~/.hermes/data/command_center.db '.schema' | grep -i <table_name>"

# Backup ANTES (obrigatório)
ssh hermes-gcp@136.115.74.69 "cp ~/.hermes/data/command_center.db ~/.hermes/backups/$(date +%Y%m%d_%H%M%S)/command_center.db.bak"

# Aplicar
scp migrations/2026_07_f3_lab_runs.sql hermes-gcp@136.115.74.69:/tmp/
ssh hermes-gcp@136.115.74.69 "sqlite3 ~/.hermes/data/command_center.db < /tmp/2026_07_f3_lab_runs.sql && rm /tmp/2026_07_f3_lab_runs.sql"

# Verify
ssh hermes-gcp@136.115.74.69 "sqlite3 ~/.hermes/data/command_center.db '.schema lab_runs'"
```

### 3.4 Helper: aplicar migration PC

```powershell
# Backup
Copy-Item "$env:USERPROFILE\.hermes\hermes_local.db" "$env:USERPROFILE\.hermes\backups\$(Get-Date -Format yyyyMMdd_HHmmss)\hermes_local.db.bak"

# Aplicar
Get-Content migrations\2026_07_f4_skill_proposals.sql | sqlite3 "$env:USERPROFILE\.hermes\hermes_local.db"

# Verify
sqlite3 "$env:USERPROFILE\.hermes\hermes_local.db" ".schema skill_proposals"
```

### 3.5 Regras invioláveis

- **NUNCA** rodar migration sem backup precedente (mesmo que pareça idempotente).
- **NUNCA** modificar SQL de migration já aplicada — gerar `_fixup.sql` adicional.
- **SEMPRE** rodar migration PC antes da VM (se ambos têm) — owner aprova schema localmente primeiro.
- **NUNCA** rodar migration durante deploy de código no mesmo passo — separar em 2 fases (migration → smoke → código).

---

## 4. Backup `~/.hermes/data/` — Procedure Canônico

### 4.1 Quando fazer backup

| Trigger | Tipo | Retenção |
|---|---|---|
| Antes de qualquer migration | full snapshot | 30 dias |
| Antes de restart `hermes-api` em produção (campaign running) | full snapshot | 7 dias |
| Diariamente 03:00 BRT (cron-like via timer) | full snapshot | 14 dias |
| Antes de `/hermes-deploy` se arquivo afetado é DB-touching | full snapshot | 7 dias |

### 4.2 Script `~/scripts/hermes_backup.sh` (VM)

```bash
#!/bin/bash
# /home/hermes-gcp/scripts/hermes_backup.sh
set -euo pipefail
TS=$(date +%Y%m%d_%H%M%S)
DEST="/home/hermes-gcp/.hermes/backups/$TS"
mkdir -p "$DEST"

# SQLite — usa .backup pra snapshot consistente (não copy direto)
sqlite3 /home/hermes-gcp/.hermes/data/command_center.db ".backup '$DEST/command_center.db'"

# State JSONs
cp /home/hermes-gcp/.hermes/data/runtime_state.json "$DEST/" 2>/dev/null || true
cp /home/hermes-gcp/.hermes/data/campaign_runs.json "$DEST/" 2>/dev/null || true
cp /home/hermes-gcp/.hermes/data/daemon_state.json "$DEST/" 2>/dev/null || true

# Skills snapshot (YAMLs vivos)
tar czf "$DEST/skills.tar.gz" -C /home/hermes-gcp/.hermes skills/

# Auth token (criptografado em rest seria ideal — TODO F.8)
cp /home/hermes-gcp/.hermes/auth_token "$DEST/" 2>/dev/null || true

# Cleanup antigos (>30d)
find /home/hermes-gcp/.hermes/backups -maxdepth 1 -type d -mtime +30 -exec rm -rf {} \;

echo "Backup ok: $DEST"
```

### 4.3 Timer systemd diário

```ini
# ~/.config/systemd/user/hermes-backup.timer
[Unit]
Description=Hermes data backup daily 03:00 BRT

[Timer]
OnCalendar=*-*-* 06:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```ini
# ~/.config/systemd/user/hermes-backup.service
[Unit]
Description=Hermes data backup

[Service]
Type=oneshot
ExecStart=/home/hermes-gcp/scripts/hermes_backup.sh
```

**Habilitar uma vez:**
```bash
ssh hermes-gcp@136.115.74.69 "chmod +x ~/scripts/hermes_backup.sh && systemctl --user daemon-reload && systemctl --user enable --now hermes-backup.timer"
```

### 4.4 Backup PC (PowerShell)

```powershell
# scripts\pc_backup.ps1 (rodar antes de cada deploy)
$ts = Get-Date -Format yyyyMMdd_HHmmss
$dest = "$env:USERPROFILE\.hermes\backups\$ts"
New-Item -ItemType Directory -Force $dest | Out-Null

# SQLite snapshot
& sqlite3 "$env:USERPROFILE\.hermes\hermes_local.db" ".backup '$dest\hermes_local.db'"

# State files
Copy-Item "$env:USERPROFILE\.hermes\runtime_state.json" $dest -ErrorAction SilentlyContinue
Copy-Item "$env:USERPROFILE\.hermes\campaign_runs.json" $dest -ErrorAction SilentlyContinue

# Cleanup >14d
Get-ChildItem "$env:USERPROFILE\.hermes\backups" -Directory | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } | Remove-Item -Recurse -Force

Write-Output "Backup PC ok: $dest"
```

---

## 5. Procedure Determinístico — `/hermes-deploy` Fase F

Sequência canônica que `/hermes-deploy` skill executa. **Cada passo tem gate concreto — se falhar, abortar imediatamente.**

### Passo 0 — Pre-flight (sempre)

```powershell
# 0.1 Validar baseline A-E
python scripts/validate_implementation.py --phase A B C D E --json |
  python -c "import sys,json; r=json.load(sys.stdin); assert r['summary']['pass']==20 and r['summary']['fail']==2, f'BASELINE QUEBRADO: {r[\"summary\"]}'; print('baseline 20/22 PASS')"

# 0.2 Confirmar conectividade VM
ssh -o ConnectTimeout=5 hermes-gcp@136.115.74.69 "echo VM up && systemctl --user is-active hermes-api"

# 0.3 Confirmar VM não está em campaign_running
ssh hermes-gcp@136.115.74.69 "curl -sf -H 'X-Hermes-Token: $(cat ~/.hermes/auth_token)' http://localhost:8500/api/daemon/state | jq -r .campaign_status"
# Se == "running": PARAR. Pedir confirmação owner. NUNCA deploy durante campanha sem pause explícito.
```

**Gate:** 3 checks PASS. Falha em qualquer → abort + report.

### Passo 1 — Resolver chapter target

Identificar qual chapter F.x está sendo deployado. Consultar **§1 Matriz Chapter→Targets** acima. Output:
- Lista de arquivos a sincronizar
- Lista de units a restartar (PC + VM)
- Migrations a aplicar (ordem)
- Decisão: deploy é obrigatório? (alguns chapters PC-only, skip)

### Passo 2 — Backup (sempre, ambos lados)

```powershell
# PC
.\scripts\pc_backup.ps1

# VM
ssh hermes-gcp@136.115.74.69 "~/scripts/hermes_backup.sh"
```

**Gate:** ambos backups retornaram `ok: <path>`. Persistir paths em `.claude/.last-deploy.json` campo `backup_pc` + `backup_vm`.

### Passo 3 — Migrations (se aplicável)

Para cada migration listada no chapter:
1. Pre-check schema (verificar tabela NÃO existe ou check FK dependency existe)
2. Aplicar PC primeiro (se tem)
3. Verify schema PC
4. Aplicar VM (se tem)
5. Verify schema VM

**Gate:** schema verify retorna tabela com colunas esperadas. Falha → restaurar backup `.bak`, abort.

### Passo 4 — Dry-run SSH (sempre)

```powershell
ssh hermes-gcp@136.115.74.69 "ls ~/hermes_api_v2.py && systemctl --user status hermes-api hermes-daemon"
```

Saída esperada: arquivo existe + units `active (running)`. Falha → abort.

### Passo 5 — Sync arquivos PC→VM

Usar `scp` para arquivos isolados, `rsync -avz --delete` para diretórios. **NUNCA usar `--delete` em diretórios que VM modifica em runtime** (ex: `~/.hermes/data/`, `~/.hermes/logs/`).

```powershell
# Exemplo F.2 (Mission Control)
rsync -avz dashboard/ hermes-gcp@136.115.74.69:~/dashboard/
scp loops/sync.py hermes-gcp@136.115.74.69:~/loops/sync.py
scp api/daemon.py hermes-gcp@136.115.74.69:~/api/daemon.py

# Exemplo F.4 (Auto-skill loop)
scp api/skills.py hermes-gcp@136.115.74.69:~/api/skills.py
scp intelligence/skill_proposer.py hermes-gcp@136.115.74.69:~/intelligence/skill_proposer.py
rsync -avz skills/ hermes-gcp@136.115.74.69:~/.hermes/skills/  # SEM --delete (owner pode ter approvados)

# Exemplo F.5 (MCP Gateway — primeira instalação)
rsync -avz mcps/contextforge/ hermes-gcp@136.115.74.69:~/mcps/contextforge/
scp .claude/mcp-gateway.yaml hermes-gcp@136.115.74.69:~/.hermes/mcp-gateway.yaml
scp .claude/systemd-units/hermes-mcp-gateway.service hermes-gcp@136.115.74.69:~/.config/systemd/user/
ssh hermes-gcp@136.115.74.69 "systemctl --user daemon-reload && systemctl --user enable --now hermes-mcp-gateway"
```

**Gate:** `rsync` exit 0. Persistir lista de arquivos em `.claude/.last-deploy.json` campo `files`.

### Passo 6 — Restart units (ordem importa)

Ordem canônica de restart (dependências):

```
hermes-mcp-gateway   →   (F.5 only, primeiro pq Brain depende)
hermes-brain         →   (F.6 only, antes da api porque consome)
hermes-api           →   (sempre se mudou api/, vm_api/, core/, channels/)
hermes-daemon        →   (depois da api — daemon consome /api/internal/*)
hermes-warmup.timer  →   (F.7 only — reload timer se schedule mudou)
```

```bash
# Template
ssh hermes-gcp@136.115.74.69 "systemctl --user restart hermes-api && sleep 3 && systemctl --user restart hermes-daemon"
```

**Gate:** cada restart seguido de `is-active` retornando `active`. Se falhou → log `journalctl --user -u <unit> -n 50` e ir pra Passo 8 (rollback).

### Passo 7 — Health check pós-deploy

```powershell
# 7.1 API VM
ssh hermes-gcp@136.115.74.69 "curl -sf -H 'X-Hermes-Token: $(cat ~/.hermes/auth_token)' http://localhost:8500/api/hermes/status" | ConvertFrom-Json

# 7.2 Endpoints específicos do chapter (ver §6 abaixo)

# 7.3 Daemon state
ssh hermes-gcp@136.115.74.69 "curl -sf -H 'X-Hermes-Token: $(cat ~/.hermes/auth_token)' http://localhost:8500/api/daemon/state"

# 7.4 WS reconnect smoke (F.2+)
# Owner conecta dashboard PC → confirma activity-orbit recebe eventos em <10s

# 7.5 Validate baseline pós-deploy
python scripts/validate_implementation.py --phase A B C D E --json |
  python -c "import sys,json; r=json.load(sys.stdin); assert r['summary']['pass']==20, f'REGREDIU: {r[\"summary\"]}'; print('OK 20/22 preservado pós-deploy')"
```

**Gate:** todos checks PASS dentro de 30s. Falha → Passo 8.

### Passo 8 — Rollback (se health falhou)

```bash
# Identificar último backup
BACKUP=$(ssh hermes-gcp@136.115.74.69 "ls -1t ~/.hermes/backups | head -1")

# Restaurar DB
ssh hermes-gcp@136.115.74.69 "cp ~/.hermes/backups/$BACKUP/command_center.db ~/.hermes/data/command_center.db"

# Restaurar state JSONs
ssh hermes-gcp@136.115.74.69 "cp ~/.hermes/backups/$BACKUP/*.json ~/.hermes/data/ 2>/dev/null || true"

# Restaurar skills
ssh hermes-gcp@136.115.74.69 "tar xzf ~/.hermes/backups/$BACKUP/skills.tar.gz -C ~/.hermes/"

# Reverter código via git (se commit já foi feito)
ssh hermes-gcp@136.115.74.69 "cd ~ && git checkout HEAD~1 -- <arquivos>"
# OU re-sync da versão estável anterior do PC (.claude/.last-deploy.json campo prev_commit)

# Restart
ssh hermes-gcp@136.115.74.69 "systemctl --user restart hermes-api hermes-daemon"

# Re-health-check
ssh hermes-gcp@136.115.74.69 "curl -sf -H 'X-Hermes-Token: ...' http://localhost:8500/api/hermes/status"
```

**Persistir falha** em `.claude/.last-deploy.json` campo `result: "rollback"` + `error: <msg>` + `rolled_back_to: <backup_ts>`.

### Passo 9 — Persistir deploy log

```json
{
  "timestamp": "2026-06-10T14:32:11-03:00",
  "chapter": "F.2",
  "files": ["dashboard/app.js", "loops/sync.py", "api/daemon.py"],
  "migrations_applied": [],
  "units_restarted_vm": ["hermes-api", "hermes-daemon"],
  "units_restarted_pc": ["uvicorn"],
  "backup_pc": "C:\\Users\\cleao\\.hermes\\backups\\20260610_143111",
  "backup_vm": "/home/hermes-gcp/.hermes/backups/20260610_143115",
  "result": "ok",
  "validate_pre": "20/22 PASS",
  "validate_post": "20/22 PASS",
  "duration_seconds": 47
}
```

Atualizar `.claude/.last-deploy.json` (truncado em últimas 50 entradas).

---

## 6. Health Checks Pós-Deploy por Chapter

Além do `/api/hermes/status` genérico, cada chapter tem endpoints específicos que **DEVEM** retornar 200 + payload válido pós-deploy:

| Chapter | Endpoints health | Smoke extra |
|---|---|---|
| F.1 | — (PC-only, sem deploy) | rodar skill `/hermes-frontend-gap` end-to-end <90s |
| F.2 | `GET /api/daemon/state`, `GET /api/daemon/timeline`, `GET /api/daemon/subsystems`, `GET /api/daemon/channels` | WS `/ws/daemon` recebe evento em <10s; tile "LinkedIn" muda status ao pause/resume |
| F.3 | `GET /api/lab/runs`, `POST /api/lab/start` (dry-run) | `lab_runner.py --dry-run` retorna OK; screenshot smoke 1 capturada |
| F.4 | `GET /api/skills/proposals`, `POST /api/skills/proposals/{id}/accept` (dry-run) | workflow `hermes-skill-forge.js` lê activity 7d sem erro; tabela `skill_proposals` aceita insert |
| F.5 | `curl http://VM:8600/healthz` (gateway), `GET /api/mcp/registry` | Brain (PC) consegue listar tools via gateway; auth JWT valida |
| F.6 | `GET /api/brain/health`, `POST /api/brain/decide` (com dummy intent) | Brain classifica intent test em <3s usando ollama; decisão persistida em `brain_decisions` |
| F.7 | `GET /api/cobaia/state`, timer `hermes-warmup.timer` listado em `list-timers` | `scripts/warmup_daily.py --dry-run` retorna lista ações sem executar |
| F.8 | `GET /api/observability/metrics/latest`, `GET /api/observability/health` | metric_emitter loop emite snapshot em <60s; sentry MCP responde (se instalado) |
| F.9 | `GET /api/pipeline/list`, `POST /api/pipeline/dry-run` | designer carrega no dashboard; pipeline teste compila + valida sem executar |

**Falha em qualquer endpoint health do chapter alvo → rollback obrigatório.**

---

## 7. Cenários de Rollback — Decision Tree

```
Deploy executou → health check FALHOU
  │
  ├── Migration aplicada? 
  │     ├── SIM → Restaurar DB do backup ANTES de qualquer outra ação (passo 8.1-8.3)
  │     └── NÃO → pular pra rollback de código
  │
  ├── Arquivos sincronizados via rsync?
  │     ├── SIM → restaurar via git checkout commit anterior na VM 
  │     │         OU re-sync da versão estável (PC commit anterior)
  │     └── NÃO → apenas restart unit (provavelmente env var / config falha)
  │
  ├── Unit nova systemd habilitada?
  │     ├── SIM → systemctl --user disable + stop a unit nova
  │     └── NÃO → skip
  │
  └── Restart final + re-health-check
        ├── OK → marcar deploy como "rollback success", reportar owner
        └── FAIL → ESCALAR: stop hermes-api, deixar VM em estado conhecido-bom anterior, alertar owner via 
                   `journalctl --user -u hermes-api -n 100` + abrir issue
```

### 7.1 Rollback parcial (failed migration apenas)

Se migration falhou MAS código não foi sincronizado ainda:
1. Restaurar DB do backup
2. NÃO restartar unit (código antigo continua compatível com schema antigo)
3. Investigar SQL antes de re-tentar
4. **NUNCA** continuar deploy de código apontando pra schema novo se migration foi revertida — geraria erro de coluna ausente

### 7.2 Rollback total (falha em produção com campaign-running)

Cenário pior: deploy foi feito DURANTE campanha (passo 0.3 não bloqueou por bug do gate).
1. **Pausar daemon imediatamente:** `ssh hermes-gcp ... "curl -X POST -H 'X-Hermes-Token: ...' http://localhost:8500/api/daemon/pause"`
2. Executar rollback completo (8.1-8.5)
3. Validar via `/api/linkedin/visited` que não houve corrupção mid-campaign
4. Só retomar campanha após confirmação manual owner

---

## 8. Anti-Padrões — NUNCA Fazer

Compilação consolidada dos guardrails F.x (estende `.claude/GUARDRAILS.md`):

1. **NUNCA** rodar migration sem backup imediatamente anterior — mesmo idempotente.
2. **NUNCA** deploy de `linkedin/stealth.py | human.py | limiter.py` sem rodar skill `/hermes-li-lab` antes em cobaia.
3. **NUNCA** restart `hermes-tunnel` em deploy de código — afeta dashboard upstream pro owner.
4. **NUNCA** `rsync --delete` em `~/.hermes/data/` ou `~/.hermes/logs/` — runtime state vivo.
5. **NUNCA** sync diretório `~/.hermes/skills/` com `--delete` — owner pode ter aprovados skills propostos via F.4 que ainda não estão no repo PC.
6. **NUNCA** deploy durante `campaign_status == "running"` sem pause explícito documentado.
7. **NUNCA** habilitar unit systemd nova sem `daemon-reload` antes.
8. **NUNCA** instalar `patchright`/`playwright`/browser binaries no PC (guardrail global #0 Hermes).
9. **NUNCA** modificar SQL de migration já aplicada — gerar `_fixup.sql`.
10. **NUNCA** skipar passo 0.1 (validate baseline) — regressão A-E mascara falhas Fase F.
11. **NUNCA** persistir token em `.last-deploy.json` ou backup descriptografado em diretório versionado.
12. **NUNCA** restart `hermes-api` em paralelo com `hermes-daemon` (ordem: api primeiro, daemon segundo).

---

## 9. Confirmações Obrigatórias do Owner

Antes de proceder, `/hermes-deploy` skill DEVE solicitar confirmação explícita owner quando:

| Situação | Confirmação requerida |
|---|---|
| Chapter F.5+F.6+F.7 (units novas systemd) | "Confirma habilitar nova unit systemd `<nome>` permanente?" |
| Migration FK em tabela com >1000 linhas | "Migration vai mudar schema com N linhas — confirma backup OK?" |
| Deploy `linkedin/*.py` (qualquer arquivo) | "Lab passou nas últimas 24h? Confirma deploy stealth-touching?" |
| Restart `hermes-api` em horário comercial (09-18 BRT) | "VM ativa em horário owner — confirma restart?" |
| Rollback acionado | "Health falhou. Confirma rollback automático? (alternativa: investigar manual)" |
| Deploy 1ª vez de chapter F.x | "Primeira vez deployando F.x — confirma leitura do PLAN.md §F.x?" |

---

## 10. Checklist Operacional — Antes/Durante/Depois

### Antes do deploy
- [ ] Branch git limpo + commit do código a deployar feito
- [ ] `validate_implementation.py --phase A B C D E` = 20/22 PASS
- [ ] PLAN.md chapter F.x lido + critérios done conhecidos
- [ ] Backup PC + VM completados (passo 2)
- [ ] Migration files revisados (se aplicável)
- [ ] Owner confirmou (§9 se aplicável)

### Durante o deploy
- [ ] Cada passo (0-9) executado em ordem
- [ ] Gate de cada passo PASS antes de prosseguir
- [ ] Logs persistidos (stdout + journalctl)
- [ ] `.last-deploy.json` atualizado incrementalmente

### Depois do deploy
- [ ] Health checks específicos chapter PASS (§6)
- [ ] `validate_implementation.py` re-rodado = 20/22 PASS preservado
- [ ] Smoke test owner-visible (ex: F.2 → owner clica dashboard tile, vê WS update)
- [ ] memory_save tipo workflow: `hermes F.x deploy ok — <chapter title>`
- [ ] mark_chapter: `F.x deployed VM`
- [ ] Git commit log atualizado com `deploy(F.x): <descrição>`

---

## 11. Referências Cruzadas

- `.claude/skills/hermes-deploy/SKILL.md` — skill genérica (este doc ESTENDE com Fase F)
- `.claude/PLAN.md` — chapters F.1→F.9 critérios done
- `.claude/GUARDRAILS.md` — guardrails globais (este doc ADICIONA §8 anti-padrões F.x)
- `.claude/HOW-TO-START-PHASE.md` — bootstrap de fase
- `.claude/PHASE-F-STUDY-SYNTHESIS.md` — fundamentação técnica
- `scripts/validate_implementation.py` — gate baseline A-E
- `migrations/` — SQL files versionados
- `.claude/.last-deploy.json` — histórico de deploys (persistente)

---

## 12. Changelog deste documento

| Data | Mudança | Autor |
|---|---|---|
| 2026-06-08 | Criação inicial — Fase F deploy procedure consolidado | Claude Opus 4.7 (Completeness Critic) |
