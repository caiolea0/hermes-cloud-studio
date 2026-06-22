# Hermes 2.0 — Acesso (Desktop ↔ VPS) + Deploy Contínuo
**Criado**: 2026-06-21 · **Status**: PROPOSTA (aguarda decisões do owner — §4)

> Responde 2 perguntas do owner:
> A) Como o app desktop no PC local acessa tudo atualizado E dispara ações no cérebro da VPS Contabo.
> B) Como manter a VPS sempre no ÚLTIMO ESTADO do projeto durante o desenvolvimento diário.

---

## 0. Princípio (não muda)
- **A verdade vive na VPS**: cérebro 24/7 (daemon) + banco (Postgres compartilhado no `geronimo-net`). O app desktop é um **cliente fino** — exibe e dispara, nunca executa o trabalho pesado. (Já é a regra do GUARDRAILS: "PC orquestra/UI, trabalho pesado na VM".)
- **Simplificação do 2.0**: com LinkedIn FROZEN, o PC **não é mais proxy de egress** (acabou o socks5/tunnel-reverso/`server.py` intermediário). O app passa a falar **direto** com a VPS. Menos peças, menos falha.

---

## A. Acesso: app desktop (PC) ↔ cérebro (VPS)

### Modelo
```
PC LOCAL                                  VPS CONTABO (geronimo-net)
┌──────────────────────┐                  ┌─────────────────────────────┐
│ App desktop (Tauri)  │   HTTPS REST     │ hermes-api :8800            │
│  carrega dashboard v2 │ ───────────────▶ │  (lê estado, recebe ações)  │
│                       │   WSS (tempo real)│ daemon 24/7 (cérebro)       │
│                       │ ◀─────────────── │  Postgres (estado real)     │
└──────────────────────┘  daemon.* deltas  └─────────────────────────────┘
```

- **App** = Tauri (já existe `Hermes.exe`), carregando o dashboard v2. Continua sendo o app desktop.
- **Ler "tudo atualizado"**: no load puxa um snapshot via REST; depois recebe deltas em tempo real via **WebSocket** (`daemon.{subsystem_status,log_event,decision}` — camada F.2.3 já existe). O estado vive 100% na VPS; o app não guarda verdade própria.
- **Disparar ações**: o app faz `POST` autenticado nos endpoints de ação da VPS (varrer bairro, auditar negócio, aprovar dossiê, mandar pro Vuecra/Geronimo). O cérebro executa na VPS. Ações sensíveis passam pelo **gate HITL/confirm** (`brain/safety.py`) — já existe.

### Como conectar (recomendado: **Tailscale**)
- PC e VPS na **mesma tailnet** (a VPS já usa Tailscale pro tráfego interno Hermes↔Geronimo — §4.3 do PLAN). O app aponta pra um nome privado (MagicDNS), ex: `http://hermes-vps:8800` / `wss://hermes-vps:8800/ws`.
- **Vantagens**: zero superfície pública, criptografado, $0, sem expor dashboard na internet. Defesa em profundidade (rede autentica + token autentica).
- **Alternativa**: `cloudflared` tunnel + **Cloudflare Access** (login Google só do owner) — usar só se precisar acessar de dispositivos fora da mesh. Mais exposto.

### Auth (já é o padrão, manter)
- Todo REST: `Authorization: Bearer <HERMES_AUTH_TOKEN>`.
- WS: `?token=...` (browser não manda header custom). Handler valida (MERGED auth).
- Atualizar `CROSS-PROJECT-ENV.md`: `HERMES_BASE_URL` → endpoint da VPS (Tailscale), NÃO mais `localhost:8500` nem o IP GCP.

### O que construir/adaptar (A)
1. Tailscale no PC (VPS já na mesh).
2. App Tauri: config aponta pra URL da VPS; CORS/WS na VPS aceitam a origem do app.
3. Confirmar tokens setados na VPS (fail-closed já existe).
4. **Aposentar/stub `server.py` local** (sem LinkedIn não há mais proxy de egress) — decisão D2.

---

## B. Deploy contínuo: PC (dev diário) → VPS (sempre no último estado)

### Princípios
- **Git é a fonte da verdade.** Dev no PC → `commit` → `push` → VPS faz `pull` → restart. Versionado, rollback trivial.
- **Código ≠ dados.** Deploy troca CÓDIGO. **Dados/estado vivem em volume Docker (Postgres) e NUNCA são sobrescritos**; mudança de schema = **migration idempotente** no deploy.
- **Docker** (a Contabo já roda docker/`geronimo-net`): Hermes vira serviço(s) compose nas portas 8800–8810 (PLAN §5.2). Deploy = `git pull` + `docker compose up -d --build` + migrations + **health check** (+ rollback se falhar).
- **Boot reconciliation**: `restart: always` (ou systemd) → se a VPS reiniciar, os serviços sobem no último código deployado e o daemon retoma do estado persistido.

### Fluxo escolhido (D3): **auto-deploy a cada push** — com salvaguardas
```
PC: git push (branch de produção = main)
 └─ CI (GitHub Actions + Tailscale → ssh VPS, ZERO superfície pública):
      git pull → docker compose up -d --build
              → run migrations (idempotente)
              → health check (/health, daemon vivo, WS ok)
              → PASSOU? deploy efetivado
              → FALHOU? git checkout <commit anterior> + restart (rollback automático) + alerta Telegram
```
- **Você controla o que publica pela branch**: desenvolve em feature branches; `push`/merge na `main` = publica. "Automático" sem subir todo WIP.
- **Salvaguarda anti-quebra**: o deploy só "vale" se o health check passar; senão **rollback automático** pro último commit bom. Nunca deixa a VPS quebrada.
- **Mecanismo**: GitHub Actions com `tailscale/github-action` entra na tailnet e faz ssh na VPS (sem abrir porta pública — alinha com D1). Alternativa: deploy-agent na VPS recebendo webhook via cloudflared outbound.
- `/hermes-deploy` v2 permanece como **deploy/rollback manual de emergência** sob comando.

> A skill `hermes-deploy` já existe (SSH + rsync + restart + healthcheck + rollback pra GCP). **Adaptar pra Contabo**: git em vez de rsync, `docker compose` em vez de systemd GCP, migrations no fluxo.

### O que construir/adaptar (B)
1. Clone git do Hermes na VPS (branch de produção) — ou pipeline CI.
2. `Dockerfile` + serviço no `docker-compose` do `geronimo-net` (portas 8800–8810).
3. **Migrations runner** no deploy (schema evolui sem perder dados).
4. **Skill `hermes-deploy` v2** (Contabo/git/docker/migrations/healthcheck/rollback).
5. Endpoint `/health` + rollback (git checkout previous + restart).
6. `restart: always` / systemd pro boot reconciliation.

---

## 4. Decisões do owner — RESOLVIDAS (2026-06-21)
| # | Decisão | ESCOLHA |
|---|---|---|
| D1 | Acesso PC→VPS | **Tailscale** (já instalado no PC; VPS já na tailnet) |
| D2 | `server.py` local | **Aposentar** (app Tauri fala direto com a VPS) |
| D3 | Gatilho de deploy | **Automático a cada push** (CI) — com salvaguardas (§B: branch main + healthcheck + rollback) |
| D4 | Empacotamento VPS | **Docker compose** no `geronimo-net` |

## 5. Sequência sugerida (depois das decisões)
1. Migração Contabo (PLAN §5.6 a–f) sobe o cérebro na VPS em docker.
2. Tailscale PC↔VPS + app Tauri apontado pra VPS + tokens → **acesso (A) funcionando**.
3. Skill `hermes-deploy` v2 (git+docker+migrations+healthcheck+rollback) → **deploy (B) funcionando**.
4. Aposentar `server.py` local (se D2=aposentar).
5. Smoke: do PC, abrir app → ver estado da VPS ao vivo → disparar 1 ação → confirmar no daemon.
