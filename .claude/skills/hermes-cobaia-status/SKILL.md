---
name: hermes-cobaia-status
description: Snapshot Live Ops da cobaia Hermes — estado pipeline cobaia (prospects qualificados, sequencias rodando, replies pendentes, deals abertos), saude warmup email 14d, hit-rate canais (LI/email/whatsapp), proximas acoes agendadas. Suporta pause/resume da cobaia inteira ou subsistema individual. Use quando user diz "status cobaia", "como ta cobaia", "pausa cobaia", "retoma cobaia", "/hermes-cobaia-status", ou no inicio de sessao Fase F.7+ Cobaia Live Ops.
---

# /hermes-cobaia-status — Snapshot Live Ops cobaia

Skill irma de `hermes-status` mas focada **APENAS** na cobaia (perfil descartavel + dominio email warmup separado + WhatsApp Business sandbox), nunca na conta sagrada do Caio. Le estado agregado, nao muta canais MADUROS (linkedin/email/scraper loops). Pause/resume usam endpoints `/api/daemon/subsystems/{name}/pause|resume` (expostos em F.2) ou fallback CLI direto no daemon_state JSON.

## Quando disparar

- Inicio de sessao Hermes Fase F.7+ (Cobaia Live Ops)
- Antes de aprovar mensagem proposta pela cobaia ("preciso ver hit-rate primeiro")
- Apos qualquer alerta de bounce/cooldown/challenge na cobaia
- Quando user pede pausa cirurgica ("pausa so o LI da cobaia mas deixa email rodando")
- Apos restart de servico ou deploy F.7 pra confirmar cobaia voltou viva
- Apos owner aprovar deal — verificar se cobaia respeitou ICP

## Argumentos suportados (slash command args)

| Arg | Efeito |
|-----|--------|
| (nenhum) | Snapshot read-only completo (default) |
| `pause` | Pausa cobaia INTEIRA (todos subsistemas: linkedin/email/whatsapp/discovery/enrichment). Owner confirma antes. |
| `pause <subsystem>` | Pausa apenas subsistema. Valores aceitos: `linkedin`, `email`, `whatsapp`, `discovery`, `enrichment`. |
| `pause <subsystem> <minutes>` | Pausa subsistema por N minutos (auto-resume agendado). Min 5, max 1440 (24h). |
| `resume` | Retoma cobaia inteira (todos subsistemas pausados voltam). |
| `resume <subsystem>` | Retoma apenas subsistema especifico. |
| `--json` | Output JSON ao inves do formato canonico texto (pra parsing programatico/UI). |
| `--brief` | Snapshot resumido 5 linhas (so headers, sem ultimos eventos/alertas). |

Combinacoes invalidas:
- `pause` + `resume` no mesmo comando → erro, abortar.
- `pause <subsystem>` com nome desconhecido → erro, listar validos.
- `pause` sem subsystem em modo `--brief` → executar mas alertar que brief nao mostra confirmacao.

## Procedimento

### Passo 1 — Detectar modo (snapshot | pause | resume)

```python
# parse args
mode = "snapshot"
subsystem = None
minutes = None
fmt = "text"
brief = False

if "pause" in args:
    mode = "pause"
    if next_token: subsystem = next_token
    if next_int: minutes = int(next_int)
elif "resume" in args:
    mode = "resume"
    if next_token: subsystem = next_token

if "--json" in args: fmt = "json"
if "--brief" in args: brief = True
```

### Passo 2a — Modo `snapshot` (default)

Preferir MCP `hermes-control` se disponivel:
```
cobaia_status()                       # agrega estado cobaia + warmup + hit-rate
cobaia_pipeline_stats(window="24h")   # prospects/sequences/replies/deals
cobaia_subsystems()                   # status por subsistema (running|paused|degraded)
cobaia_next_actions(limit=10)         # proximas 10 acoes agendadas
```

Fallback (sem MCP) — curl direto contra endpoints F.2 + F.7:
```powershell
$tok = $env:HERMES_AUTH_TOKEN
$base = "http://localhost:8500"

# Estado cobaia (cobaia profile isolado em daemon_state.cobaia)
curl -H "X-Hermes-Token: $tok" "$base/api/cobaia/status"
curl -H "X-Hermes-Token: $tok" "$base/api/cobaia/subsystems"
curl -H "X-Hermes-Token: $tok" "$base/api/cobaia/pipeline/stats?window=24h"
curl -H "X-Hermes-Token: $tok" "$base/api/cobaia/warmup/email"
curl -H "X-Hermes-Token: $tok" "$base/api/cobaia/hitrate?channels=linkedin,email,whatsapp"
curl -H "X-Hermes-Token: $tok" "$base/api/cobaia/next-actions?limit=10"
curl -H "X-Hermes-Token: $tok" "$base/api/daemon/timeline?profile=cobaia&limit=10"
```

Fallback ultimo recurso (endpoints F.7 ainda nao expostos) — ler JSONs direto:
```powershell
type data\runtime\daemon_state.json | jq '.cobaia'
type data\runtime\cobaia_state.json
type data\runtime\warmup_email_state.json
```

### Passo 2b — Modo `pause`

```powershell
# Pause subsistema individual
if ($subsystem) {
    $body = @{minutes = $minutes} | ConvertTo-Json
    curl -X POST -H "X-Hermes-Token: $tok" -H "Content-Type: application/json" `
         -d $body "$base/api/cobaia/subsystems/$subsystem/pause"
} else {
    # Pause cobaia inteira — confirmacao obrigatoria
    Write-Host "Pause COBAIA INTEIRA? (yes/no): " -NoNewline
    $resp = Read-Host
    if ($resp -ne "yes") { exit }
    curl -X POST -H "X-Hermes-Token: $tok" "$base/api/cobaia/pause"
}
```

Apos pause bem-sucedido:
- Executar snapshot brief automaticamente pra confirmar novo estado.
- Logar acao em memory_save type="workflow" content="cobaia paused {subsystem|all} by owner {timestamp}".

### Passo 2c — Modo `resume`

```powershell
if ($subsystem) {
    curl -X POST -H "X-Hermes-Token: $tok" "$base/api/cobaia/subsystems/$subsystem/resume"
} else {
    curl -X POST -H "X-Hermes-Token: $tok" "$base/api/cobaia/resume"
}
```

Apos resume:
- Snapshot brief automatico.
- Validar que subsistema voltou pro estado `running` (nao apenas `paused→none`).
- Se subsistema voltou `degraded` ou `circuit-broken`: alertar owner, NAO marcar resume como sucesso.

## Output esperado (formato canonico)

### Modo `snapshot` completo

```
HERMES COBAIA STATUS — {YYYY-MM-DD HH:MM} (Cuiaba TZ)

Cobaia profile      : {ok|degraded|paused|blocked} — perfil {nome_cobaia}
LinkedIn (cobaia)   : {running|paused|cooldown|challenge} — warmup day {X}/14
Email warmup        : {running|paused} — dominio {dom} reputation {0-100} bounces {N}/sent {M}
WhatsApp Business   : {running|paused|disabled} — quota dia {X}/{lim}
Discovery pipeline  : {running|paused} — last run {Xm} ago, prospects ingested {N}
Enrichment pipeline : {running|paused} — queue {N}, last enrich {Xm} ago

Pipeline 24h:
  Prospects qualificados : {N} (ICP score >=70)
  Sequences ativas       : {N} ({N_running} running / {N_paused} paused)
  Replies pendentes      : {N} (owner review needed)
  Deals abertos          : {N} (proposta enviada, aguardando)
  Deals fechados (won)   : {N}
  Deals perdidos (lost)  : {N}

Hit-rate canais (ultimos 7d):
  LinkedIn  : conn_accept {X}% · reply_rate {Y}% · meeting_rate {Z}%
  Email     : open_rate {X}% · reply_rate {Y}% · bounce {Z}%
  WhatsApp  : delivered {X}% · read {Y}% · reply {Z}%

Rate limits hoje (cobaia):
  LI views {X}/{lim} · connects {Y}/{lim} · comments {Z}/{lim}
  Email sent {X}/{lim} (warmup cap day {N})
  WA msgs {X}/{lim}

Working hours      : {dentro|fora} (Cuiaba {HH-HH})

Proximas acoes agendadas (top 10):
- {timestamp} {subsystem} {acao} {prospect_id|target}
- ...

Ultimos eventos cobaia (10):
- {timestamp} {tipo} {summary}
- ...

Alertas:
- {se houver: bounce alto, ICP drift, owner approval pendente >24h, warmup behind}
```

### Modo `--brief`

```
COBAIA {YYYY-MM-DD HH:MM} | {ok|degraded|paused} | LI:{state} Email:{state} WA:{state} | Deals: {open}/{won}/{lost} | Alertas: {N}
```

### Modo `pause` (output confirmacao)

```
COBAIA PAUSE — {subsystem|ALL}
Status anterior  : {running|degraded}
Status agora     : paused
Auto-resume em   : {minutes}min ({timestamp_resume}) | manual (--resume)
Sequences afetadas: {N} pausadas
Proxima acao cancelada: {acao} (rescheduled pos-resume)
Owner pode retomar com: /hermes-cobaia-status resume {subsystem}
```

### Modo `resume` (output confirmacao)

```
COBAIA RESUME — {subsystem|ALL}
Status agora     : {running|degraded}
Sequences retomadas: {N}
Proxima acao em  : {timestamp}
Se degraded: motivo {cooldown|challenge|circuit-broken} — investigar antes campanha
```

### Modo `--json` (qualquer modo)

```json
{
  "timestamp": "2026-06-08T14:30:00-04:00",
  "mode": "snapshot|pause|resume",
  "cobaia_profile": "ok|degraded|paused|blocked",
  "subsystems": {
    "linkedin": {"state": "running", "warmup_day": 7, "rate_limits": {...}},
    "email":    {"state": "running", "domain_reputation": 92, "bounces_24h": 1},
    "whatsapp": {"state": "disabled"},
    "discovery": {"state": "running", "last_run_ago_s": 180},
    "enrichment": {"state": "running", "queue_size": 12}
  },
  "pipeline_24h": {"qualified": 8, "active_sequences": 23, ...},
  "hitrate_7d": {"linkedin": {...}, "email": {...}, "whatsapp": {...}},
  "next_actions": [...],
  "alerts": [...]
}
```

## Sanity checks (executar SEMPRE apos snapshot)

1. **Isolamento cobaia ≠ Caio**: `cobaia.profile.linkedin_account_id != caio.profile.linkedin_account_id` — se vazio ou igual, ABORTAR com erro critico "cobaia profile not isolated".
2. **Warmup day coerente**: dia warmup email deve avancar 1/dia desde criacao perfil. Se `warmup_day_actual < (today - profile_created_at).days`: alertar "warmup behind, sequence integrity at risk".
3. **Hit-rate sanity**: se `bounce_rate > 5%` em email cobaia, alertar "stop email cobaia, reputation risk". Se `linkedin.reply_rate < 1%` apos 50+ sends, alertar "ICP miss, owner revisar segmentacao".
4. **Deal staleness**: deals abertos sem update >7d em alerta — owner pode ter esquecido follow-up.
5. **Pause auto-resume**: se subsistema marcado `paused` mas `pause_until_timestamp` ja passou, alertar "auto-resume falhou, intervir manualmente".

## Anti-padroes

- **NUNCA** chamar `/api/linkedin/*` (sem prefixo /cobaia/) — esses sao Caio sagrado. Endpoints cobaia SEMPRE tem prefixo `/api/cobaia/`.
- **NUNCA** rodar `pause all` durante deal review pendente — owner pode estar revisando proposta naquela hora.
- **NUNCA** marcar `resume` como sucesso se subsistema voltou `degraded` — owner precisa saber.
- **NUNCA** usar dominio email da cobaia pra enviar pra prospect Caio (DB tem flag `is_caio_prospect` — bloquear envio cobaia).
- **NUNCA** rodar essa skill contra perfil Caio "pra testar" — perfil Caio nao tem endpoints `/api/cobaia/*`, vai dar 404 e voce vai pensar que ta tudo bem.
- **NAO** alterar rate-limits cobaia pra "acelerar warmup" — warmup 14d e LEI (proteger reputacao dominio recem-criado).

## Persistencia pos-execucao

Apos cada invocacao:
```
memory_save type="workflow" content="cobaia {mode} {subsystem|all} — state {pre}→{post}, alertas {N}" concepts=[hermes, cobaia, live-ops, phase-f7]
```

Se modo `pause` ou `resume`:
```
mark_chapter "Cobaia {paused|resumed} {subsystem|ALL}" summary="owner-triggered via /hermes-cobaia-status, status pos-acao {state}"
```

## Dependencias

- **F.1** completo (FRONTEND-GAP.md identifica endpoints cobaia faltando — se algum endpoint `/api/cobaia/*` desta skill estiver em ORPHAN, criar issue F.7).
- **F.2** completo (endpoints `/api/daemon/subsystems/{name}/pause|resume` existem — esta skill estende padrao pra namespace cobaia).
- **F.7** em progresso (Cobaia Live Ops — esta skill e a interface CLI/slash enquanto UI Cobaia Live Ops nao fica pronta).

## Relacao com skills irmas

- `/hermes-status` = saude geral PC+VM+Caio (NUNCA cobaia).
- `/hermes-cobaia-status` = ESTA SKILL — saude cobaia isolada, com pause/resume.
- `/hermes-li-lab` = testes Patchright em perfil descartavel laboratorio (NAO cobaia produtiva, NAO Caio).
- `/hermes-stealth-check` = auditoria stealth/human/limiter (codigo MADURO, aplicavel a Caio + cobaia).

Trigger por skill (regra): se user diz "status hermes" sem qualificar → `/hermes-status`. Se diz "status cobaia" ou menciona warmup/cobaia/perfil-descartavel → ESTA skill. Se ambiguo: perguntar.
