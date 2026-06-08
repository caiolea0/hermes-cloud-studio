# Hermes Cloud Studio — Guardrails Invioláveis

> **Leia ANTES de qualquer ação** nesta codebase. Atualize com TODA decisão arquitetural nova.
> Mecanismo anti-confusão. Evita erros como "instalar Patchright no PC" ou perder contexto pós-erro.

---

## 🚫 NUNCA FAZER

| Erro | Consequência | Por quê |
|---|---|---|
| Instalar `patchright`, `playwright`, browser binaries no **PC** | Loop de debug perdido | Esse stack roda APENAS na VM |
| Rodar `python -m linkedin.*` no PC local | Module not found / arch errada | `linkedin/` é deployado na VM via SCP/rsync |
| Executar fluxos LinkedIn sem tunnel SOCKS5 UP | Egress vai pelo IP datacenter GCP → ban imediato | PATCH-003 inegociável |
| SSH direto da VM pra LinkedIn sem proxy | Idem datacenter ban | Sempre via socks5 reverse PC residencial |
| Modificar `linkedin/stealth.py` sem rodar lab pos-mudança | Regressão silenciosa de fingerprint | Lab é gate obrigatório |
| Deletar `~/.hermes/` na VM | Estado de session/li_at perdido | Backup antes |
| Trocar IP/proxy/UA durante sessão LinkedIn ativa | Burn da conta (li_at+IP+fp bound) | PATCH-008 |
| Skip preflight/compliance gates em prod | Bypass de segurança | Gates são inegociáveis |
| Commit `.env`, `*.db`, `linkedin_data/`, `logs/`, `linkedin/lab/artifacts/` | Vazamento de credentials / repo gigante | .gitignore cobre |

---

## ✅ SEMPRE FAZER

### Antes de qualquer execução

```
1. Read .claude/GUARDRAILS.md (este arquivo)
2. Read .claude/PLAN.md (estado da sessão)
3. memory_smart_search "hermes" (contexto cross-sessão)
4. Verificar tunnel supervisor: python scripts/tunnel_supervisor.py --status
   - egress_residential MUST be true
   - Se false → diagnóstico antes de seguir
```

### Antes de comando que toca código

Resposta às 3 perguntas:

1. **Onde isto roda?** PC local OU VM?
2. **Deps existem nessa máquina?** (`pip show <dep>` ANTES de install)
3. **Tunnel necessário?** (LinkedIn = sempre sim)

### Antes de SCP/sync VM

```
git status --short             # ver mudanças
tar -czf ... --exclude=...     # exclude __pycache__, artifacts, profiles
scp ... hermes-gcp@VM:/tmp/
ssh ... "cd ~ && tar -xzf ..."
```

### Antes de rodar lab/prod LinkedIn

```
ssh VM "rm -f ~/.hermes/data/linkedin_health.json"   # clear cooldown cache
ssh VM "python3 linkedin/lab/_clear_launch_cooldown.py"  # clear 30min spacing
xvfb-run -a --server-args='-screen 0 1920x1080x24' python3 -m linkedin.lab.lab_runner --flow ...
```

---

## 🏗️ Arquitetura (referência canônica)

```
PC LOCAL (Windows, D:\dev-projects\main\hermes-cloud-studio)
├── Hermes.exe (Tauri 2.0)
├── server.py :8500 — dashboard backend (proxy/sync com VM)
├── socks5_proxy.py :55081 — proxy residencial
├── ssh -R 55081:55081 hermes-gcp@VM — tunnel reverse
├── scripts/tunnel_supervisor.py — always-on (Windows Task Scheduler)
├── Dashboard SPA — exibe/controla, NUNCA executa LinkedIn
├── MCP hermes-control (TS) — controla VM via natural language
└── .claude/ — PLAN, AUDIT, STEALTH-PATCHES, skills, agents, commands, workflows

VM GCP 136.115.74.69 (Ubuntu 24.04, hermes-gcp)
├── hermes_api_v2.py :8420 — backend real
├── daemon/orchestrator.py — loop 24/7 P1-P7
├── linkedin/ (deployado via SCP do PC) ← É AQUI QUE LinkedIn EXECUTA
│   ├── stealth.py + human.py + limiter.py (3 patches reduzidos aplicados)
│   ├── preflight.py — assert_tunnel_healthy fail-closed
│   ├── stealth_compliance.py — auto-correct lang + chrome.loadTimes
│   ├── account_profile.py — burn_flag + sticky_session_id
│   ├── viewer.py / engager.py / connector.py — flows prod
│   └── lab/ — modo descartavel pra testar
├── gosom_scraper (Docker) + night_scraper
├── Ollama (PC GPU via SSH tunnel reverso :11434)
└── ~/.hermes/skills/ — YAML

EGRESS LinkedIn:
PC residencial (Caio, ASN brasileiro) ← VM via socks5_proxy ← Patchright Chrome
```

**Regra**: trabalho pesado na VM. PC orquestra/cacheia/UI. Nunca o contrário.

---

## 🔧 Deps por máquina

### PC (Windows, Python 3.13)
- `python-dotenv`, `playwright` (referência) — instalado
- **NÃO** patchright, **NÃO** browser binaries Chromium/Playwright
- Node 18+ + `@modelcontextprotocol/sdk` em `mcps/hermes-control/`

### VM (Linux, Python 3.12)
- `patchright`, `playwright`, `python-dotenv`, `httpx[socks]`, `socksio`, `httpx`, `fastapi`, `uvicorn`
- Browser: chromium-1223 em `~/.cache/ms-playwright/`
- Chrome stable real: `~/chrome-extract/opt/google/chrome/google-chrome` (149.0.7827.53)
- System: `xvfb-run`, `mesa-utils`, `libgl1-mesa-dri`

**Validar via**: `ssh hermes-gcp@136.115.74.69 "pip3 show <pkg>"` antes de qualquer install.

---

## 🔐 Inviolavelmente persistido

Estado que NUNCA pode ser perdido:
- `linkedin_data/profiles/lab_*` — user_data_dir Patchright (cookies bound to fingerprint)
- `linkedin_data/sessions/*.json` — session_file backup (li_at + outros)
- `linkedin_data/account_profiles/*.json` — AccountProfile (sticky_session_id, burn_flag)
- `linkedin_data/rate_limits.db` — warmup_state + pending_invites + acceptance_cooldown
- `~/.hermes/` na VM inteiro
- Tunnel supervisor estado em `logs/tunnel_supervisor_state.json`

Backup antes de mexer.

---

## 🚨 Sinais de problemas

Reagir IMEDIATAMENTE se:

| Sinal | Ação |
|---|---|
| `egress_residential: false` no supervisor | Restart socks5_proxy + ssh tunnel |
| `LinkedIn em cooldown: challenge` | Ler logs, **não** force-refresh — pode piorar |
| `compliance score < 70` | Não tocar LinkedIn. Investigar fingerprint primeiro |
| AccountProfile `burned_flag=true` | NÃO retry. Owner valida na UI antes de unburn |
| Tunnel cai > 5min | Supervisor deve restartar; se não, diagnose pcap |

---

## 📝 Pre-flight checklist (mental — cada session start)

```
[ ] GUARDRAILS.md lido (este arquivo)
[ ] PLAN.md aberto, próximo checkbox identificado
[ ] memory_smart_search rodado
[ ] tunnel supervisor --status retornou OK
[ ] git status checado (mudanças pendentes mapeadas)
[ ] Sei em qual máquina cada comando do plano roda
```

---

## 🧪 Validation Harness (anti-regressão)

Mecanismo automatizado pra confirmar implementação:
```bash
python scripts/validate_implementation.py            # tudo
python scripts/validate_implementation.py --phase A  # uma fase
python scripts/validate_implementation.py --finding MERGED-001
python scripts/validate_implementation.py --json     # output máquina
python scripts/validate_implementation.py --apply-flags  # reabre tasks pra fails
```

- Lê `.claude/VALIDATION-CHECKLIST.md` (asserts por finding)
- Output: `.claude/validation-report.json`
- Flags: `.claude/validation-flags.json` (lista finding_ids em FAIL)
- **Inviolável**: rodar antes de fechar cada fase. FAIL = reabrir + reimplementar. Loop até 100% PASS.

## 🔄 Quando atualizar este arquivo

- Toda decisão arquitetural nova → adiciona linha em "Arquitetura"
- Todo erro inesperado novo → adiciona em "🚫 NUNCA FAZER"
- Toda dep nova → adiciona em "Deps por máquina"
- Todo gate novo → adiciona em "🔐"

## 🔐 Auth tokens obrigatórios (MERGED-002/001/003)

- `HERMES_AUTH_TOKEN` — PC server.py. Ausente = RuntimeError no startup.
- `HERMES_VM_AUTH_TOKEN` — VM hermes_api_v2.py. Idem.
- `HERMES_INTERNAL_TOKEN` — endpoints /api/internal/*. Ausente = RuntimeError. Extension + li_at_sync.py enviam via `X-Internal-Token`.
- WebSocket /ws exige token via `?token=` query param (browser não envia custom headers). FastAPI middleware NÃO cobre WS — auth no handler.
- server.py bind `127.0.0.1:55000` (não 0.0.0.0). /api/internal/* aceita loopback + INTERNAL_TOKEN.

## 🔄 Robustness (Fase B — MERGED-005/015/004/016/007)

- **SQLite**: usar `linkedin/db_utils._connect()` para novas conexões. `busy_timeout=30s` + WAL obrigatório.
- **asyncio tasks**: usar `spawn()` (server.py / hermes_api_v2.py). NUNCA `asyncio.create_task()` bare.
- **except Exception: pass**: sempre comentar `# noqa: silenciado intencional — <razão>`. Loops principais usar `logger.exception()`.
- **campaign_runs**: persistência VM. Qualquer campanha 'running' com heartbeat > 5min = orphaned no próximo startup.
- **sync overwrite**: `_local_error_until_ack` protege erros de dispatch. Não remover sem `/dismiss-error`.

## 🧩 Config central (Fase C.1 — MERGED-013/009)

- **`config.py` raiz é fonte canônica** de TODAS env vars do projeto. NUNCA `os.environ.get` novo em server.py / hermes_api_v2.py — adicionar field em `HermesSettings` e usar `settings.X`.
  - Exceções permitidas: vars do SO (USERPROFILE, PATH) e tokens runtime-set (LI_AT é setado por endpoint, não vem do .env no boot).
- **IP da VM**: `settings.vm_host`. NUNCA literal `136.115.74.69` em código. Excepcao unica: `linkedin/preflight.py` que mantém literal como constante de segurança datacenter blocklist (NÃO é config, é guard anti-detecção).
- **`settings.vm_api_url_resolved`**: usar quando precisar do URL VM API completo (fallback computa de vm_host:vm_api_port).
- **Fail-closed tokens**: settings.auth_token / internal_token / vm_auth_token são strings vazias por default. Cada consumidor (server.py, hermes_api_v2.py) DEVE manter `if not TOKEN: raise RuntimeError(...)` após binding pra preservar MERGED-002/003.
- **Pydantic-settings carrega .env automaticamente** — `load_dotenv()` em server.py / hermes_api_v2.py virou redundante mas inofensivo (mantido por compat).

## 🤖 Ollama router (Fase C.4 — MERGED-014)

- **TODA chamada Ollama vai por `linkedin/ollama_router.py`** — NUNCA `httpx.post` direto pra `:11434`. Use `await ollama_router.route("classify"|"creative_ptbr", prompt, options={...})`.
- **Model map por task**: `classify` -> `qwen2.5:3b` (rapido), `creative_ptbr` -> `qwen2.5:7b-instruct` (multilingual PT-BR). Override via `HERMES_OLLAMA_MODEL_*` env.
- **Primary = PC tunnel reverso** (RTX 2060 6GB). Fallback opcional via `HERMES_OLLAMA_FALLBACK_URL` (vazio default, sem fallback = `OllamaUnavailable` quando PC offline).
- **Migracao VM-GPU**: trocar `OLLAMA_URL` pra `http://localhost:11434` da VM e zerar fallback. Acoplamento PC->VM some.
- **Modelo NAO instalado** = silent fail historico (connector.py default era `qwen2.5:7b` nunca instalado). Sempre `ollama list` antes de mudar default.

## 🧩 Split monolitos (Fase C.5 — MERGED-011)

- **server.py é shell fino** (~250 linhas): imports, lifespan, app FastAPI, middleware, WS /ws endpoint, include_router(*) de api/, spawn() dos 6 loops em loops/.
- **PC routers em `api/<dominio>.py`** — cada arquivo expoe `router = APIRouter()` e e incluido em server.py via `app.include_router()`. NAO criar `@app.<verb>(...)` novo direto em server.py: adicionar ao router do dominio relevante (ou criar novo `api/<novo>.py` + include).
- **PC loops em `loops/<loop>.py`** — `sync_loop`, `linkedin_sync_loop`, `linkedin_scheduler_loop`, `linkedin_health_monitor_loop`, `vm_health_watchdog_loop`, `linkedin_session_monitor_loop`. Lifespan em server.py spawns todos.
- **Shared infra em `core/state.py`** — get_db, init_db, spawn (MERGED-015), AUTH_TOKEN/INTERNAL_TOKEN fail-closed, WSManager+ws_manager, _check_internal (MERGED-003), _telegram_notify, _local_error_until_ack (MERGED-016), _LI_* globals (acessados via `state.NOME` em loops, NUNCA via `global NOME`).
- **Pydantic models em `core/models.py`** (PC) e `vm_core/models.py` (VM). NUNCA inline em routers.
- **AI helpers em `core/ai.py`**: call_agent_zero, call_claude_cli, call_ai, execute_claude_command. Importados por api/prospects, api/tasks, api/claude, api/agent_zero, api/scraper.
- **VM idem**: `hermes_api_v2.py` shell fino (~98 linhas), `vm_core/state.py` shared infra, `vm_api/routes.py` consolidado (todos endpoints + helpers LinkedIn ainda fortemente acoplados).
- **Late imports para circular** — `loops/linkedin_scheduler.py` importa `_compute_schedule_state` de `api.linkedin` dentro do loop body (NAO no topo). `api/hermes.py:trigger_sync` importa `sync_from_vm` de `loops.sync` dentro do handler.
- **NUNCA atualizar globals com `global` keyword pra _LI_*** — eles vivem em `core/state.py`. Use `import core.state as state; state._LI_SESSION_LAST_OK = X`.

## 🛡️ Infra & Supervision (Fase D — MERGED-017/018/020/006)

- **Subprocess Popen na VM**: SEMPRE `start_new_session=True` (isola signals do parent) + `_write_pid_meta(pid_file, proc.pid)` (JSON {pid, create_time}) + `register_subproc(proc.pid)`. Liveness check via `_proc_alive(pid, expected_ct)` — NUNCA `kill -0` (Linux-only, sem create_time guard). `terminate_tracked_subprocs()` no lifespan shutdown.
- **Session monitor** (`loops/linkedin_session.py`): `REQUIRED_FAILS=3`. UMA probe falha NUNCA dispara alert. Só notifica Telegram quando `_LI_SESSION_FAIL_STREAK >= REQUIRED_FAILS`. Probe ok zera streak. Mata spam por flake de rede / VM lag.
- **Restart endpoints**: TODOS os `@router.post("/api/server/restart-*"|"/shutdown-local")` em `api/server_ctrl.py` carregam `@limiter.limit("2/hour")` + `request: Request` na assinatura (slowapi requirement). NUNCA adicionar restart sem rate-limit. Limiter singleton em `core/limiter.py`.
- **UPDATE prospects**: SEMPRE incluir `version = version + 1` (e `updated_at = CURRENT_TIMESTAMP`) na clausula SET. Vale pra PC (`api/prospects.py`) e VM (`vm_api/routes.py`). Sync detecta conflict comparando `vm.version` vs `local.last_synced_version` + `local.version`. Bug invisível se version não bumpar.
- **sync_from_vm conflict policy**: ambos editados (vm.version > last_synced E local.version > last_synced) → `conflict_at = now`, local **preservado**, NUNCA sobrescrever sem owner dismiss via `/api/prospects/{id}/resolve-conflict`.
- **Migration nova em prospects**: aplicar BOTH PC (`core/state.py` init_db) E VM (`vm_core/state.py` init_db) — schemas precisam ficar coerentes pra sync funcionar. VM aplica via SSH + ALTER TABLE idempotente.

## 📬 Channels (Fase E.1 — MERGED-010 Email)

- **Email channel mora em `channels/email/`** paralelo a `linkedin/`. Pattern: `config.py` (dataclass + `from_settings()`), `limiter.py` (warmup + caps + working hours, `_get_db()` reusa `linkedin/db_utils._connect`), `sender.py` (orquestra: assert_ready -> can_send -> _smtp_send -> record_sent/failed).
- **Gmail App Password** em `EMAIL_APP_PASSWORD` (.env, NUNCA `.env.example`). Setar `EMAIL_FROM`. Smtp default smtp.gmail.com:587 STARTTLS.
- **DB sidecar em `channels_data/email/email_rate.db`** — NUNCA reutilizar `linkedin_data/rate_limits.db`. Tabelas `email_actions` (per envio) + `email_warmup_state` (per account).
- **Warmup obrigatório**: dia 0 = 10% de `daily_cap` (50/dia se cap=500). Ramp linear até dia 14 = 80%. Após 14d = 100% cap. Não desligar `working_hours_enabled` em prod (sinal anti-spam pra provedor).
- **Retry só em transient SMTP codes** {421, 450, 451, 452, 454} e OSError de rede. Outros codes (5xx auth/perm) sobem como `EmailSendError` direto.
- **Headers Hermes**: `Message-ID` (make_msgid hermes.local domain), `X-Hermes-Campaign-Id`, `X-Hermes-Run-Id` (uuid 12 hex). Pra tracking sem cookie pixel.
- **Outros channels (WhatsApp/Instagram)**: replicar mesmo pattern em `channels/whatsapp/` e `channels/instagram/`. NÃO emparelhar — testar Email 30d antes do próximo.

## 🔒 XSS dashboard (Fase E — MERGED-019)

- **`dashboard/vendor/purify.min.js`** (DOMPurify 3.2.4) é vendor LOCAL. NÃO trocar por CDN runtime (dashboard pode estar offline). Atualizar versão = `curl jsdelivr` + commit binary.
- **TODA injeção de HTML em `innerHTML +=` derivada de input do Claude/Hermes DEVE passar por `sanitizeClaudeHtml()`**. Allowlist atual em `app.js`: `CLAUDE_ALLOWED_TAGS` (17 tags) + `CLAUDE_ALLOWED_ATTR` (4 attrs). Expandir só se markdown render precisar.
- **Fail-open dev only**: se DOMPurify ausente (vendor não carregou), `sanitizeClaudeHtml` retorna sem sanitizar com `console.warn`. Em prod isso = bug do `<script src=...>` no index.html — investigar, não ignorar.

Última edição: 2026-06-08 (Chapter 20 — Fase E.1 MERGED-010 Email + E.2 MERGED-019 XSS).
