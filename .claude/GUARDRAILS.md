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

Última edição: 2026-06-07 (Chapter 10).
