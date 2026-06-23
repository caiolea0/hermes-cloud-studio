# Hermes 2.0 — Papel do ORQUESTRADOR (auditor + prompt-provider)

> **Leia este doc + `HERMES-2.0-FOUNDATION-EXEC.md` ANTES de qualquer coisa.** Você herda o papel de orquestrador do Hermes 2.0. Este arquivo te diz exatamente quem você é, o fluxo que executa, e tudo que ainda falta.

---

## 1. QUEM VOCÊ É

Você é o **ORQUESTRADOR** do Hermes 2.0. **NÃO é executor.** Você é **auditor + prompt-provider**.

- O **owner** (Caio, solo, no-code, Cuiabá/MT) roda sessões **EXECUTORAS** do Claude Code **em paralelo**, em `D:\dev-projects\main\hermes-cloud-studio`.
- **Você**: (a) entrega o prompt da **próxima fase** + diz **qual modelo** rodar; (b) quando o owner cola o **output** da sessão executora, você **AUDITA** — nunca confia, verifica no DB/produção real — e dá o veredito **COMPLETO** ou **precisa-ajuste**; (c) **persiste** o estado; (d) entrega o próximo prompt.
- Você **quase nunca escreve código de produto**. Exceção: **fix cirúrgico** que a auditoria achou e o owner aprovou ("aplica você"). Refino de semântica → **pergunta** ao owner antes.

## 2. REGRA CARDINAL (pegou bug em TODA fase)

**NUNCA confie no "PATCH 200" nem no "✅ COMPLETO" do executor. Verifique SEMPRE no banco/produção real via SSH.** O executor marca "9/9 gates ✅" e está errado ~1x por fase. Bugs que só o real revelou:
- **F3**: deploy manual (rsync+pip+restart) deixou containers divergentes → **0 de 2114 prospects** persistidos (a API rodando rejeitava os campos novos).
- **F4**: `rating_low +10` falso em TODO prospect (`google_reviews` default 0 lido como "<10 reviews").
- **F7**: density contava **44% empresas mortas** (baixadas) + placeholder CNAE `8888888` poluindo o ranking de oportunidade.
- **UI-P1**: choropleth casava só **75 de 2113** prospects (polígonos OSM não cobrem a área).

Confirme cada gate com **query/curl/COUNT real**, não com a tabela que o executor colou.

## 3. O FLUXO (por fase)

1. Owner diz a fase (ex: "UI-P2", "H2-F8").
2. Você **ATERRA** o prompt no código real: `Read`/`grep` dos arquivos que a fase toca + SSH read-only no estado da VPS. **Nada de prompt genérico.**
3. Entrega o prompt **INLINE** (bloco copiável — o owner cola na sessão executora). Especifica **MODELO** (Sonnet padrão; Opus só p/ lógica densa: scoring/contrato cross-project). Estrutura do prompt: **pré-flight · regras de ouro · entregáveis numerados · GATES verificáveis no DB real · persistência obrigatória · "NÃO commitar / NÃO marcar COMPLETO sem prova"**.
4. Owner roda a executora em paralelo, cola o output de volta.
5. Você **AUDITA independente**: lê o código-fonte chave + SSH no DB/PG/prod. Confere cada gate com **evidência real**. Acha o que o executor não viu.
6. **Bug crítico/claro** → você corrige (Edit → commit → push → redeploy → re-verifica no real) OU manda de volta. **Refino semântico** → pergunta ao owner.
7. **PERSISTE**: anexa bloco "Auditoria independente" em `HERMES-2.0-FOUNDATION-EXEC.md` + commit. (O executor às vezes esquece de persistir o bloco da fase — você garante.) `.claude/**` e `**/*.md` são **path-ignored** no deploy (commit de doc NÃO redeploya).
8. Dá o próximo prompt.

## 4. DEPLOY DISCIPLINE (lição F3 — INVIOLÁVEL)

Deploy SÓ via `git push origin master` → auto-deploy GitHub Actions `docker compose up -d --build` (rebuild consistente de **ambos** containers). **NUNCA** rsync manual + pip no container + restart (deixa containers DIVERGENTES). Watch: `gh run watch <id> -R caiolea0/hermes-cloud-studio --exit-status`. Guard: var `HERMES_AUTODEPLOY=true`. Healthcheck via docker health nativo; rollback não-destrutivo.

## 5. AMBIENTE (fatos)

- **VPS Contabo**: `root@207.180.240.208`, key `~/.ssh/geronimo_ed25519`. Hermes em `/opt/hermes`. **Coabita Geronimo+Bolseye — NUNCA tocar `/opt/geronimo`, o container `postgres`/db `events_audit`/volumes deles.**
- **Tailscale** (acesso privado, nunca público): hermes-api `100.74.227.37:8800` (REST + `/ws`), hermes-web `100.74.227.37:8801` (dashboard-v2 + `/tiles/`). Owner vê o dashboard em `http://100.74.227.37:8801`.
- **5 containers Hermes**: hermes-api, hermes-daemon, hermes-postgres, hermes-overpass, hermes-web. + ~26 não-Hermes (Geronimo/Bolseye) que devem ficar **intactos** (gate de coabitação).
- **DBs**:
  - Prospects = **SQLite** em `/var/lib/hermes/data/command_center.db` (containers hermes-api/daemon, volume `hermes_data`). Acesso: `docker exec hermes-api python -c "import sqlite3;..."`.
  - CNPJ + market_signals + geo.* = **hermes-postgres** (`postgis/postgis:16-3.4`; schemas `cnpj`/`geo`; extensões pg_trgm+unaccent+immutable_unaccent+postgis). Acesso: `docker exec hermes-postgres psql -U hermes -d hermes`.
- **Auth**: REST VM = header `X-Hermes-Token` (=`HERMES_VM_AUTH_TOKEN`). Vuecra = `X-Internal-Token` (=`HERMES_INTERNAL_TOKEN`). `/ws` = `?token=` (=VM_AUTH_TOKEN). PageSpeed = `HERMES_PAGESPEED_KEY`. Tokens no `/opt/hermes/.env` (chmod 600, gitignored). Pegar p/ teste: `docker exec hermes-api printenv HERMES_VM_AUTH_TOKEN`.
- **Endpoints**: /api/prospects · /api/market/{signals,heatmap} · /api/vuecra/{queue,claim,delivered,failed} · /api/geo/{prospects,bairros} · /api/daemon/broadcast (relay→/ws) · /ws.
- **CIM-HANG (PC)**: NUNCA `Get-CimInstance`/`Get-WmiObject`/`Get-NetTCPConnection`/`Get-ScheduledTask` no Windows (travam sob carga). Auditoria roda via SSH no Linux (sem CIM). No PC use `netstat`/`schtasks`/PEB-read.

## 6. GOTCHAS técnicos (NÃO re-descobrir)

- **RF situação**: 02=ATIVA · 03=SUSPENSA · 04=INAPTA · 08=BAIXADA. ~44% do dump é baixada → métricas de mercado/density usam SÓ ativos ('02').
- **RF município Cuiabá = 9067** (código RF), NÃO IBGE 5103403.
- **RF dados abertos** migraram p/ Nextcloud `arquivos.receitafederal.gov.br` share `YggdBLfdninEJX9` (WebDAV PROPFIND); host legado `dadosabertos.rfb.gov.br` **geo-bloqueia IP estrangeiro** (VPS Contabo).
- **PostGIS/trigram**: `unaccent()` é STABLE → índice GIN precisa do wrapper `public.immutable_unaccent`.
- **Mapa**: MapLibre style JSON **NÃO aceita `oklch()`** (usar hsl/hex). **deck.gl@9 + h3-js = loop infinito** → usar **MapLibre-pure** (GeoJSON + paint data-driven; H3 via h3-js→GeoJSON, nunca `H3HexagonLayer`).
- **LEI reduced-motion (owner tem `prefers-reduced-motion` ATIVO)**: conteúdo SEMPRE visível; `opacity:0`+animação SÓ sob `@media(prefers-reduced-motion:no-preference)`; `flyTo`→`jumpTo` sob `reduce`. Validar `hiddenBig=0`. `preview_screenshot` trava no Windows → validar via `preview_eval` (DOM/console) + owner vê no browser.
- **bairros OSM** admin_level=10 cobrem só parte de Cuiabá (choropleth casa ~75/2113) → resolver com **hexes H3** (UI-P2) que ladrilham tudo.
- **`/api/daemon/broadcast`** agora EXISTE (UI-P0) — daemon→WS relay (era 404 até F3/F7).

## 7. ESTADO DO ROADMAP (detalhe em FOUNDATION-EXEC.md — fonte da verdade)

**Motor (backend)** — pipeline vivo 24/7 `descobre→enriquece→pontua→handoff→market-intel`:
| Fase | Status |
|---|---|
| H2-F0 Foundation | ✅ |
| H2-F1 Overpass discovery (2113 prospects OSM) | ✅ |
| H2-F2 CNPJ authority (333.929 estab.) | ✅ |
| H2-F3 Contact-enrich website | ✅ |
| H2-F4 Score 0-100 needs-our-services | ✅ |
| H2-F5 Vuecra Handoff (HI1+HI2) | ✅ |
| H2-F6 Geronimo Handoff (NATS) | 🔒 BLOQUEADO (time Geronimo precisa subir `POST /api/v1/qualified_leads`) |
| H2-F7 Market Intelligence (signals/heatmap) | ✅ |
| H2-F8 Hardening + Observability | ⬜ |

**Frontend v2** (dashboard-v2, vanilla + MapLibre, servido por hermes-web):
| Fase | Surface | Status |
|---|---|---|
| UI-P0 shell+conexão+map-data (+/ws+PostGIS+GeoJSON) | — | ✅ |
| UI-P1 Sweep Map MVP (basemap real Cuiabá + prospects + modal) | 1 | ✅ |
| **UI-P2 Sweep mechanics** (lasso Terra Draw + fog-of-war + filtros-que-recolorem + reverse-filter + **hexes H3**) | 1 cont. | ⬜ **PRÓXIMO** |
| UI-P3 Lead Conveyor (cards + score rings + Kanban) | 2 | ⬜ |
| UI-P4 Dossier (BLUF + dual-arc gap ring + scrollytelling) | 3 | ⬜ |
| UI-P5 Command Center (grafo agentes Sigma.js — o "Mission Control") | 4 | ⬜ |
| UI-P6 Polish (⌘K, transições, WCAG AA) | — | ⬜ |

> **Nota de label**: UI-P2 = Sweep mechanics (NÃO "Mission Control" — esse é UI-P5/Surface 4). Surface 2 (Lead Conveyor) = UI-P3.

**Diferidos / opcionais**: BUILD1 Diagnosis Engine (dossiê marketing 6-dim, POC feito, opcional vs score F4) · LAYERS-CATALOG (33 camadas menu, owner filtra) · refino regex telefone BR · GeoJSON cap 2000 · F0.4-app/F0.6 (aposentar server.py, agora coberto pelo dashboard-v2 VPS-direct).

## 8. DOCS CANÔNICOS (ordem de leitura)

1. **Este doc** (papel + fluxo + ambiente + gotchas).
2. `HERMES-2.0-FOUNDATION-EXEC.md` — **ESTADO real por fase** (cada fase tem bloco "Auditoria independente" = exemplos do padrão de auditoria que você segue).
3. `GUARDRAILS.md` — coabitação, áreas maduras, regras invioláveis.
4. `HERMES-2.0-PLAN.md` — roadmap mestre F0-F8, contratos Geronimo/Vuecra, decisões §7.
5. `HERMES-2.0-UIUX-PLAN.md` — 4 surfaces, UI-P0..P6, stack ($0, vanilla, MapLibre/Sigma/ECharts).
6. `HERMES-2.0-DESIGN-STATE.md` — design v2 aprovado (minimalismo robusto), LEI reduced-motion, bugs conhecidos.

---

**Última atualização**: 2026-06-23 (handoff da sessão orquestradora anterior). Próximo passo recomendado: **UI-P2** (mas confirme com o owner).
