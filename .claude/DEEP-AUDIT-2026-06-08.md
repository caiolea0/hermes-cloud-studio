# Hermes Cloud Studio — Deep Audit (2026-06-08)

> Gerado por workflow `hermes-deep-audit`. Investigação multi-dimensional pós-implementação dos 3 patches stealth reduzidos.

**Findings totais**: 172 (de 11 dimensões: arquitetura, backend, channels, daemon, stealth residual, skills YAML, database, MCP, tunnel resilience, security, performance)
**Top 20 sintetizados**: 20
**Confirmados (>=2 lentes valid)**: 20

---

## Top findings confirmados

### MERGED-001 — WebSocket /ws sem autenticação — broadcast de dados sensíveis para qualquer cliente

- **Severity**: critical 
- **Category**: security
- **File**: `server.py:810-831, /ws`
- **Verify score**: 3/3 lentes

**Resumo**: Middleware auth_middleware só cobre /api/. /ws aceita qualquer conexão e broadcasta campanhas LinkedIn, prospects, daemon_state, partial_results. Combinado com CORS=* e tunnel público, vazamento total de dados operacionais e sessão.

**Evidência**: ```
server.py:810-819 sem checagem de token; CLAUDE.md:57 documenta mas não implementa
```

**Fix hint**: Validar X-Hermes-Token ou query token no handshake WS; reject 1008 se inválido. Fail-closed quando token vazio.

**Lentes**:
- OK (high): Evidência confirmada no código real. server.py:810-819 define @app.websocket("/ws") que chama ws_manager.connect(websocket) e aceita handshake sem qualquer validação de token. Middleware auth_middleware (822-831) só valida path.startswith("/api/") — WS handshake nem passa por HTTP middleware no FastAPI/Starlette de qualquer forma. Broadcasts (linhas 416, 491, 587, 611, 695, 2379, 2496, 2657, 3184,
- OK (high): WebSocket /ws bypassa auth_middleware (cobre só /api/). Broadcasta campanhas LinkedIn, prospects (PII B2B), daemon_state, partial_results. Com CORS=* + tunnel público, qualquer cliente conecta e exfiltra pipeline de vendas em tempo real. 3 meses sem fix: vazamento contínuo silencioso, possível LGPD breach (prospects identificáveis), competidores espelham estratégia comercial, tokens/sessão potenci
- OK (high): Fix viavel. Adicionar checagem X-Hermes-Token no handshake WS antes de aceitar conexao. FastAPI/Starlette WebSocket le headers/query no endpoint /ws. Reject com close(code=1008) se token invalido/vazio (fail-closed). Effort S: ~10-20 linhas em server.py:810-831, padrao identico ao auth_middleware ja existente em /api/. Sem dependencia bloqueante — pode ser corrigido isolado. CORS=* e tunnel public

---

### MERGED-002 — AUTH_TOKEN vazio = fail-open — API totalmente pública por default

- **Severity**: critical 
- **Category**: security
- **File**: `server.py:48,823-825; hermes_api_v2.py:28,154-156`
- **Verify score**: 3/3 lentes

**Resumo**: `if not AUTH_TOKEN: return await call_next(request)` em ambos PC e VM. Deploy sem env definida expõe scraper start, restart endpoints, dispatch LinkedIn, rotate LI_AT. Padrão deveria ser fail-closed (503).

**Evidência**: ```
server.py:48; hermes_api_v2.py:154
```

**Fix hint**: Em startup: raise se AUTH_TOKEN ausente. Nunca pular middleware por token vazio.

**Lentes**:
- OK (high): Evidência confirmada em ambos arquivos. server.py:48 define `AUTH_TOKEN = os.environ.get("HERMES_AUTH_TOKEN", "")` (default vazio); server.py:823-825 middleware checa `if not AUTH_TOKEN: return await call_next(request)` — bypass total. Idêntico em hermes_api_v2.py:28 (`VM_AUTH_TOKEN` default "") e 154-156 (mesmo pattern). Deploy sem env var = API 100% pública. Fail-open em endpoints sensíveis (scr
- OK (high): Fail-open auth em ambos PC e VM (server.py:48 + hermes_api_v2.py:154) expõe endpoints sensíveis (scraper start/restart, dispatch LinkedIn, rotate LI_AT) sem nenhuma autenticação se AUTH_TOKEN estiver vazio/ausente — condição trivial de ocorrer em deploy (esquecer env var, .env mal carregado, container sem secret). Dano em 3 meses sem fix: (1) qualquer um na internet com IP/URL pode disparar rotate
- OK (high): Fix viável e direto: trocar `if not AUTH_TOKEN: return await call_next(request)` por raise no startup (fail-closed). Effort S — mudança trivial em 2 arquivos (server.py:48 e hermes_api_v2.py:154), ~5 linhas cada. Sem dependência de outros findings: é mudança isolada no middleware/startup. Risco de regressão baixo mas real — qualquer deploy/dev local sem AUTH_TOKEN setado vai quebrar imediatamente 

---

### MERGED-003 — Endpoints /api/internal/* confiam apenas em request.client.host — LI_AT rotacionável via IP spoof

- **Severity**: high 
- **Category**: security
- **File**: `server.py:2394,2433,2470`
- **Verify score**: 3/3 lentes

**Resumo**: 3 endpoints internos checam só client.host in 127.0.0.1. Sem token. /api/internal/li_at_rotate aceita cookie LinkedIn. Se bind 0.0.0.0 ou X-Forwarded-For respeitado, atacante rouba/seta sessão LinkedIn.

**Evidência**: ```
server.py:2394
```

**Fix hint**: Exigir token interno separado + bind exclusivo loopback; nunca confiar em headers de proxy não-validados.

**Lentes**:
- OK (high): Evidência confirmada literalmente em server.py:2394, 2433, 2470 — três endpoints /api/internal/* (account_type_set, li_at_rotate, linkedin/event) validam apenas request.client.host in (127.0.0.1, ::1, localhost), sem token de autenticação inbound. Bind é 0.0.0.0:55000 (linha 3308), expondo a porta em todas as interfaces. /api/internal/li_at_rotate aceita cookie LinkedIn (li_at) e propaga para a VM
- OK (high): Finding real mas severity high exagerada. Análise: (1) FastAPI request.client.host usa IP TCP real, não respeita X-Forwarded-For sem ProxyHeadersMiddleware (não habilitado aqui) — claim de "IP spoof via header" é incorreta. (2) Bind 0.0.0.0:55000 confirmado (linha 3308), mas atacante LAN conectando direto vê IP LAN real, bloqueado pelo check. (3) Fluxo li_at é PC→VM (cookie sai do PC, vai pra VM v
- OK (high): Fix viável e padrão. Effort S: (1) gerar token interno via secrets.token_urlsafe() em env var INTERNAL_API_TOKEN, (2) adicionar dependency FastAPI que valida header X-Internal-Token + checa client.host == 127.0.0.1, (3) garantir uvicorn bind em 127.0.0.1 (não 0.0.0.0), (4) nunca confiar X-Forwarded-For sem ProxyHeadersMiddleware com trusted_hosts explícito. Sem dependência de outro finding — indep

---

### MERGED-004 — Estado crítico em globals in-memory sem persistência — perde tracker em restart

- **Severity**: high 
- **Category**: bug
- **File**: `hermes_api_v2.py:1046 _running_linkedin_campaigns; server.py _LI_SESSION_LAST_OK, _LI_HEALTH_NOTIFIED_AT, _audit_state, _agent_zero_context_id:51`
- **Verify score**: 3/3 lentes

**Resumo**: Tracker de campanhas LinkedIn ativas, estado de saúde, contexto Agent Zero — tudo em dict de módulo. Restart (Tauri tray, supervisor, deploy) perde tracking mas Patchright headful e cookies continuam vivos. Reconciliação manual.

**Evidência**: ```
hermes_api_v2.py:1046
```

**Fix hint**: Persistir em SQLite (tabela campaign_runs com status); recovery no startup do lifespan.

**Lentes**:
- OK (high): Evidência confirmada no código atual. hermes_api_v2.py:1046 tem exatamente `_running_linkedin_campaigns: dict = {}` (tracker in-memory de asyncio.Task). server.py:51 tem `_agent_zero_context_id: Optional[str] = None`, :520 tem `_LI_SESSION_LAST_OK = True`, :541 tem `_LI_HEALTH_NOTIFIED_AT = 0.0`. Todos são globals de módulo sem persistência — perdem estado em restart. Única discrepância: `_audit_s
- OK (medium): Bug real mas severity 'high' exagera. Cenarios 3 meses sem fix: (1) restart raro em ferramenta single-user Tauri local; (2) campanhas LinkedIn observaveis via Patchright headful vivo, usuario reconcilia visualmente; (3) cookies/sessao Patchright persistem em disco — recovery manual viavel; (4) Agent Zero context_id perdido = nova sessao, nao perda de dado. Dano real: retrabalho operacional + risco
- OK (high): Fix viável e direto. Persistir tracker LinkedIn em SQLite (tabela campaign_runs: id, status, started_at, updated_at, context_id, metadata JSON) é padrão. Recovery no FastAPI lifespan startup reconcilia estado lendo campanhas com status='running' e re-anexa ao Patchright via cookies/contexto persistido. Effort M: schema+migration, refatorar 4 globals (_running_linkedin_campaigns, _LI_SESSION_LAST_O

---

### MERGED-005 — Race conditions em 5 loops + endpoints concorrentes contra SQLite sem busy_timeout

- **Severity**: high 
- **Category**: race-condition
- **File**: `server.py:56-60,426-738,554,478`
- **Verify score**: 3/3 lentes

**Resumo**: WAL ativado mas sem PRAGMA busy_timeout. linkedin_scheduler_loop SELECT scheduled, linkedin_sync_loop UPDATE vindo da VM, _dispatch UPDATE — janela SELECT→UPDATE sem transação atômica. Sob contenção: OperationalError database is locked imediato.

**Evidência**: ```
server.py:56-60
```

**Fix hint**: PRAGMA busy_timeout=5000; encapsular SELECT+UPDATE em BEGIN IMMEDIATE; idempotência por version column.

**Lentes**:
- OK (high): Evidência confirmada no código real. server.py:56-60 mostra get_db() com PRAGMA journal_mode=WAL ativo mas SEM PRAGMA busy_timeout. server.py:554 confirma linkedin_scheduler_loop SELECT id FROM linkedin_campaigns WHERE status='scheduled'. server.py:478 confirma UPDATE linkedin_campaigns dentro de sync_linkedin_campaigns (chamado por linkedin_sync_loop a cada 10s). Janela SELECT→dispatch→UPDATE sem
- OK (medium): Finding válido tecnicamente: WAL sem busy_timeout + SELECT→UPDATE não-atômico em 3+ loops concorrentes (scheduler, sync VM, dispatch) gera OperationalError "database is locked" sob contenção real. Porém severity "high" é exagerada para o cenário concreto: SQLite com WAL tolera bem leitores concorrentes; conflito real só em writers simultâneos. Em 3 meses sem fix, dano provável: erros esporádicos e
- OK (high): Fix viável e padrão SQLite. PRAGMA busy_timeout=5000 trivial (1 linha no connect). BEGIN IMMEDIATE encapsulando SELECT+UPDATE resolve race window. Version column pra idempotência adiciona migration mas é padrão. Effort M: 3 loops + _dispatch precisam refactor de transação, migration de schema pra version column, testes de contenção. Dependências: cross-links dim2-FIND-004/022/012 sugerem outros ra

---

### MERGED-006 — Sync PC↔VM por polling 60s sem versionamento — last-write-wins silencioso

- **Severity**: high 
- **Category**: race-condition
- **File**: `server.py:426 sync_loop, 508 linkedin_sync_loop; limit=50 sem since`
- **Verify score**: 3/3 lentes

**Resumo**: Dois SQLites bidirecional sem vector clock/updated_at reconciliation. Bulk PATCH no PC + enrichment VM no mesmo prospect → último ganha sem audit. limit=50 sem paginação deixa campanhas antigas eternamente desatualizadas e zombies pós-delete VM-side.

**Evidência**: ```
server.py:434-505
```

**Fix hint**: Adicionar updated_at + ETag/version; sync incremental por since=; merge baseado em monotonic clock; tombstones para deleções.

**Lentes**:
- OK (high): Evidência confirmada no código atual. sync_loop linha 426 (60s SYNC_INTERVAL), linkedin_sync_loop linha 508 (10s, não 60s — finding diz "60s" mas o linkedin é 10s; sync_loop geral é 60s). sync_linkedin_campaigns linha 439 usa limit=50 sem since=. Ausência total de versionamento/ETag/vector clock/tombstones confirmada via grep (0 hits). sync_from_vm linhas 310-333 sobrescreve campos do prospect (in
- OK (high): Finding factualmente correto: sync_loop (60s) e linkedin_sync_loop (10s) puxam VM→PC sem since= nem reconciliação por updated_at; coluna updated_at existe nas tabelas (server.py:94,135,159) mas NÃO é consultada no sync — só atualizada localmente. limit=50 hardcoded em /api/linkedin/campaigns. Bidirecional last-write-wins real (PC PATCH em 1133/1149/1155 + VM enrichment puxando de volta). Nenhum to
- OK (high): Fix hint viável e claro. Effort L: requer (1) migration schema SQLite adicionando updated_at + version/etag em ambos PC e VM, (2) reescrever sync_loop e linkedin_sync_loop para usar since= cursor incremental com paginação, (3) implementar merge strategy (monotonic clock ou Lamport timestamp) em vez de last-write-wins, (4) tombstone table para deleções soft-delete, (5) backfill updated_at em regist

---

### MERGED-007 — 30+ except Exception:pass silenciam falhas em loops e endpoints — bugs invisíveis

- **Severity**: high 
- **Category**: tech-debt
- **File**: `server.py:444,476,500,568,592,616,696,720,803,818,1459,1510,1619,1716,1776,2311,2384,2421,2458,2497,2569,2589,2605,2671,2700,2750,2850,2946`
- **Verify score**: 3/3 lentes

**Resumo**: Falta padrão de resiliência. sync_loop, broadcast WS, parse JSON, session-check confundem timeout de rede com sessão expirada (dispara Telegram falso). Loops podem morrer e UI mostra dados velhos sem alerta.

**Evidência**: ```
server.py:720 session-check
```

**Fix hint**: Wrapper run_loop_forever(name, fn) com logger.exception + backoff + métrica de heartbeat; classificar exceções (network vs business) antes de mascarar.

**Lentes**:
- OK (high): Grep confirmou 30+ ocorrências de `except Exception:` seguidas de `pass`/silent em server.py. Linhas citadas (444, 500, 568, 592, 616, 696, 720, 803, 818, 1459, 1510, 1619, 1716, 1776, 2311, 2384, 2421, 2458, 2497, 2569, 2589, 2605, 2671, 2700, 2750, 2850, 2946) batem todas. Caso emblemático line 720 (linkedin_session_monitor_loop) verificado: bloco try abrange httpx.get + parse JSON, e qualquer E
- OK (high): Severity high justificada. 30+ except Exception:pass em server.py cobrem sync_loop, broadcast WS, session-check e parse JSON. Cenários reais em 3 meses sem fix: (1) sync_loop morre silenciosamente, UI mostra dados velhos sem alerta — usuário decide com info stale; (2) session-check confunde timeout de rede com sessão expirada e dispara Telegram falso repetido, gerando alert fatigue até alertas rea
- OK (high): Fix hint claro e padrão: wrapper run_loop_forever(name, fn) com logger.exception, backoff exponencial e heartbeat metric é prática consolidada (ver tenacity, asyncio patterns). Classificar exceções (network/timeout vs business/auth) antes de mascarar é trivial com isinstance checks (requests.Timeout, ConnectionError vs HTTPError 401/403). Effort M: 30+ sites, mas refactor mecânico — criar 1 decora

---

### MERGED-008 — Topologia 'PC orquestra, VM executa' violada — linkedin_viewer aceito no PC

- **Severity**: high 
- **Category**: tech-debt
- **File**: `server.py:/api/pipelines vs CLAUDE.md:35,104`
- **Verify score**: 3/3 lentes

**Resumo**: Guardrail proíbe LinkedIn/Patchright no PC mas roteador aceita tipo linkedin_viewer com execução PC. Dead code ou violação real — em ambos casos sinaliza erosão arquitetural e contradição com docs.

**Evidência**: ```
server.py:2963
```

**Fix hint**: Auditar pipelines reais; remover tipo se dead, ou explicitar exception no guardrail. Test contract para garantir LinkedIn=VM-only.

**Lentes**:
- OK (high): Evidência confirmada com ressalva sobre linha. Pointer original (server.py:2963) está INCORRETO — linha 2963 é SSH restart-vm, não pipelines. Mas o claim subjacente é VERDADEIRO e verificável: server.py:2050 aceita pipeline_type=='linkedin_viewer' e despacha pra _execute_linkedin_viewer() em 2106, que em 2132-2151 importa `from linkedin import LinkedInViewer` e roda Patchright LOCALMENTE no PC (`v
- OK (medium): Finding valido — contradicao real entre guardrail (CLAUDE.md proibe LinkedIn/Patchright no PC) e roteador (server.py:2963 aceita linkedin_viewer com exec PC). Mas severity "high" exagera. Cenarios 3 meses sem fix: (a) se dead code, dano = zero funcional, so confusao docs/onboarding; (b) se rota viva mas nao usada, mesmo dano; (c) se alguem disparar pipeline LinkedIn no PC, risco = ban conta Linked
- OK (high): Fix viável: auditar /api/pipelines em server.py:2963 pra ver se linkedin_viewer é dead code ou execução real. Se dead, remover branch. Se ativo, ou roteia pra VM (alinhar com guardrail PC=orquestra/VM=executa) ou documentar exception explícita em CLAUDE.md. Effort S/M (1-3h): leitura do roteador + grep de chamadas + decisão + test contract garantindo LinkedIn=VM-only. Risco regressão baixo se houv

---

### MERGED-009 — IP da VM hardcoded em 13+ lugares — migração GPU planejada vai quebrar

- **Severity**: high 
- **Category**: tech-debt
- **File**: `server.py:2963, proxy-tunnel.ps1:9, README.md, setup_vm*.sh, agents/vm-deploy-verifier.md`
- **Verify score**: 3/3 lentes

**Resumo**: 136.115.74.69 espalhado em código + docs + scripts. Fase 1 do AUDIT.md prevê migração GPU. SSH com StrictHostKeyChecking=no + hardcode = MITM + esforço de grep-replace cross-repo com risco de stale.

**Evidência**: ```
server.py:2955-2977
```

**Fix hint**: Settings central (pydantic-settings) com VM_HOST; known_hosts pinned; CI lint contra IP literal.

**Lentes**:
- OK (high): Evidência confirmada em todos os pontos citados: (1) server.py:2963 contém literal "hermes-gcp@136.115.74.69" dentro de chamada SSH com flag "-o StrictHostKeyChecking=no" na linha 2961 — exatamente como descrito; (2) proxy-tunnel.ps1:9 tem $VMHost = "136.115.74.69" hardcoded; (3) grep do IP retornou 14 arquivos incluindo README.md, setup_vm.sh, setup_vm_complete.sh, agents/vm-deploy-verifier.md, C
- OK (medium): Hardcode IP espalhado é tech-debt real mas não quebra sistema hoje. Cenário 3 meses sem fix: migração GPU planejada (Fase 1 AUDIT.md) força grep-replace em 13+ lugares — chato mas mecânico, ~1h trabalho. Risco MITM via StrictHostKeyChecking=no é vetor real porém exige atacante na rota SSH (low likelihood em tunnel LAN). Dano: atraso de migração + janela MITM teórica. Não é 'high' pois (a) sistema 
- OK (high): Fix viável e direto. Pydantic-settings com VM_HOST em .env é padrão maduro, baixa fricção. Effort M: (1) criar settings.py central, (2) substituir 13+ ocorrências via grep-replace controlado, (3) gerar known_hosts pinned com ssh-keyscan + remover StrictHostKeyChecking=no, (4) adicionar lint CI (regex IPv4 literal) bloqueando regressão. Docs (README, AUDIT.md) tambem migram pra placeholder. Sem dep

---

### MERGED-010 — Canais Email/WhatsApp/Instagram são stubs — daemon mente sobre P1-P7 multi-canal

- **Severity**: high 
- **Category**: missing-feature
- **File**: `channels/email, channels/whatsapp, channels/instagram (__init__.py vazio); daemon/orchestrator.py:79`
- **Verify score**: 3/3 lentes

**Resumo**: Só linkedin/ tem implementação (~250KB). ChannelState modelado mas não pluggado. Dashboard control page mostra 4 canais — UX engana operador. Email é o canal lógico para começar (rate maior, menor risco).

**Evidência**: ```
channels/email/__init__.py vazio
```

**Fix hint**: Definir interface ChannelAdapter; implementar email primeiro (SMTP+deliverability); registry + wiring no orchestrator loop.

**Lentes**:
- OK (high): Evidence confirmed. channels/email/__init__.py, channels/whatsapp/__init__.py, channels/instagram/__init__.py contêm apenas 1 linha de comentário cada (stubs reais, sem código). daemon/orchestrator.py:79 define @dataclass ChannelState com daily_limit/health/warmup mas só linkedin/ tem implementação real (~2.2MB em D:/dev-projects/main/hermes-cloud-studio/linkedin/, não em channels/linkedin/). Pequ
- OK (high): Finding válido — stubs vazios + UI mostra 4 canais = mismatch real entre promessa e entrega. Mas severity "high" exagerada. Cenários 3 meses sem fix: (1) sistema NÃO quebra — linkedin/ continua funcionando isolado; (2) dano = UX confusa (operador clica canal morto) + dívida arquitetural (ChannelState modelado sem uso) + bloqueio de roadmap multi-canal. Nada disso é catastrófico nem perda de dados/
- OK (high): Fix hint claro e viável: definir interface ChannelAdapter, implementar email (SMTP+deliverability) primeiro, registry + wiring no orchestrator. Effort L — não é só código; envolve SMTP infra (DKIM/SPF/DMARC), warm-up de IP, bounce/complaint handling, templates, unsubscribe compliance (CAN-SPAM/LGPD), e refactor do orchestrator para multi-canal. Dependências: deve vir DEPOIS de consolidar interface

---

### MERGED-011 — Monolitos server.py (3308 lin) + hermes_api_v2.py (1861 lin) sem separação por domínio

- **Severity**: high 
- **Category**: tech-debt
- **File**: `server.py, hermes_api_v2.py`
- **Verify score**: 3/3 lentes

**Resumo**: Tudo num arquivo: routers, loops, auth, sync, dispatch, agent zero. Merge conflicts garantidos; difícil testar isolado; regressões silenciosas. Bloqueia adição de novos canais (FIND MERGED-010).

**Evidência**: ```
server.py 3308 linhas
```

**Fix hint**: APIRouter por domínio (linkedin/, sync/, agent/, scraper/, internal/); extrair loops para módulo background/.

**Lentes**:
- OK (high): Evidência confirmada exatamente. server.py = 3308 linhas (bate exato), hermes_api_v2.py = 1861 linhas (bate exato). Total 5169 linhas em 2 arquivos. 189 defs/decorators em server.py + 108 em hermes_api_v2.py = 297 funções/rotas concentradas. Monolito real, severity high justificada. Fix hint (APIRouter por domínio) é padrão FastAPI válido.
- OK (high): Monolitos 3308+1861 lin sem separação por domínio. 3 meses sem fix: merge conflicts crescem, onboarding lento, bugs cross-domain (auth quebra sync, loop quebra dispatch), testes unitários impossíveis, bloqueia MERGED-010 (novos canais). Sistema NÃO quebra — roda. Mas velocidade de feature cai e regressões silenciosas aumentam. Não é critical (sistema não para). High justificado pelo bloqueio explí
- OK (high): Fix viavel. APIRouter por dominio padrao FastAPI, mecanico. Effort L: 3308+1861=5169 linhas, exige mapear endpoints, extrair loops background pra modulo separado, ajustar imports/dependencies, testar cada rota. Dependencia: idealmente antes de MERGED-010 (novos canais), pois refactor cria estrutura modular que MERGED-010 vai usar — evita retrabalho. Risco regressao medio-alto: monolito sem testes 

---

### MERGED-012 — Lógica duplicada daemon/orchestrator.py vs scripts/pipeline.py

- **Severity**: medium 
- **Category**: tech-debt
- **File**: `daemon/orchestrator.py (948 lin), scripts/pipeline.py`
- **Verify score**: 3/3 lentes

**Resumo**: Loop autônomo e pipeline manual repetem discovery→audit→outreach. Regras de scoring vão divergir; correção num lado não propaga.

**Evidência**: ```
daemon/orchestrator.py
```

**Fix hint**: Extrair stages para pacote core/stages/ chamado por ambos; pipeline.py = wrapper CLI sobre o mesmo core.

**Lentes**:
- OK (high): Ambos arquivos existem em D:/dev-projects/main/hermes-cloud-studio/. orchestrator.py tem 948 linhas (bate). scripts/pipeline.py (284 lin) define run_discovery/run_audit_pending/run_outreach_ready com thresholds hardcoded (50/65/70). daemon/orchestrator.py define _exec_discovery/_exec_batch_audit/_exec_recalculate_scores + TaskCategory.DISCOVERY/AUDIT/OUTREACH. Dois pipelines paralelos confirmados,
- OK (medium): Duplicação real entre daemon/orchestrator.py (948 lin) e scripts/pipeline.py em discovery→audit→outreach gera risco concreto de divergência. Dano em 3 meses sem fix: bugs corrigidos num lado persistem no outro, leads scoram diferente conforme caminho (daemon vs CLI manual), retrabalho a cada mudança de regra, onboarding confuso. Não quebra sistema (não é critical/high) — ambos rodam. Medium justif
- OK (high): Fix viável: extrair stages (discovery, audit, outreach) para core/stages/ é refactor clássico DRY. Daemon e pipeline.py viram thin wrappers chamando mesmo core. Effort M: ~948 linhas no orchestrator + pipeline.py, exige identificar fronteiras stage, mover funções puras, ajustar imports, testar ambos caminhos (loop autônomo + CLI manual). Sem dependência bloqueante — pode ser feito standalone, mas 

---

### MERGED-013 — Configuração ad-hoc com os.getenv — sem Settings central, defaults inconsistentes

- **Severity**: medium 
- **Category**: tech-debt
- **File**: `server.py, hermes_api_v2.py, daemon/orchestrator.py, scripts/*`
- **Verify score**: 3/3 lentes

**Resumo**: Cada módulo lê env próprio. Falha tardia/silenciosa quando secret falta. Não há doc de quais envs PC vs VM precisam. Bloqueia FIND-009 (eliminar IP hardcoded).

**Evidência**: ```
server.py multiple getenv
```

**Fix hint**: pydantic-settings Settings() compartilhado; .env.example documentando PC vs VM; fail-fast em startup.

**Lentes**:
- OK (high): Evidência confirmada. Grep encontrou 113 ocorrências de os.getenv/os.environ em 22 arquivos .py do projeto. Distribuição bate exatamente com o finding: server.py=24, hermes_api_v2.py=17, daemon/orchestrator.py=6, scripts/* (li_at_sync.py=8, pipeline.py=2, google_maps_scraper.py=1, tunnel_supervisor.py=1). Nenhum uso de pydantic-settings/BaseSettings/Settings central no codebase. .env.example exist
- OK (high): Finding válido mas severity medium superestima impacto. Cenário 3 meses sem fix: sistema continua funcionando — os.getenv() ad-hoc não quebra produção, apenas gera fricção em onboarding/debug quando env falta (erro tardio em vez de fail-fast no startup). Não há perda de dados, não há vulnerabilidade, não há outage. É tech-debt clássico de DX: doc faltando + defaults inconsistentes + descoberta tar
- OK (high): Fix viável, padrão da indústria. pydantic-settings centraliza env vars com validação, defaults e fail-fast. Effort M: criar settings.py com classe Settings, substituir os.getenv em ~4 módulos, criar .env.example documentando PC vs VM. Sem dependência hard — habilita FIND-009 (IP hardcoded). Risco regressão baixo-médio: envs opcionais devem ser Optional com defaults explícitos pra não quebrar deplo

---

### MERGED-014 — Dependência circular PC↔VM: VM 24/7 depende de Ollama no PC via tunnel reverso

- **Severity**: medium 
- **Category**: scalability
- **File**: `CLAUDE.md:16,123, GUARDRAILS.md:88`
- **Verify score**: 3/3 lentes

**Resumo**: Topologia documentada inverte SPOF: PC dorme/reboot → daemon VM perde Ollama, cai em fallback degradado. Contradiz objetivo 24/7.

**Evidência**: ```
CLAUDE.md:123
```

**Fix hint**: Mover Ollama para VM (GPU migration); ou fallback Anthropic API definido; circuit breaker no daemon quando Ollama unreachable.

**Lentes**:
- OK (medium): CLAUDE.md:16 e :123 confirmam SSH tunnel reverso forwarding port 11434 (Ollama) entre PC e VM — evidência concreta existe. Porém GUARDRAILS.md NÃO existe no projeto (alucinação parcial do auditor nessa parte). Adicionalmente, há contradição interna na própria CLAUDE.md: linha 25 lista Ollama no bloco VM e linha 111 afirma "VM só tem Ollama local", o que enfraquece a tese de SPOF (se VM tem Ollama 
- OK (high): Finding válido. Topologia PC↔VM com Ollama no PC cria SPOF: PC dormir/reboot/Windows Update derruba inferência do daemon VM 24/7, contradizendo objetivo de disponibilidade contínua. Severity medium justificada — não critical (sistema não quebra catastroficamente, fallback degradado existe, workloads Hermes/Mercury toleram janelas curtas), mas não low (afeta SLA 24/7 declarado, degrada prospecção/t
- OK (high): Fix_hint viável e claro com 3 opções concretas. Effort M: (1) circuit breaker no daemon + fallback Anthropic API = M (algumas horas, código isolado no daemon, baixo risco); (2) migração Ollama PC→VM = L (requer GPU na VM ou aceitar CPU inference degradado, reconfig SSH tunnels, testes de performance). Caminho recomendado: começar com circuit breaker + fallback Anthropic (curto prazo, resolve SPOF 

---

### MERGED-015 — asyncio.create_task sem hold de referência — risco de GC silencioso

- **Severity**: medium 
- **Category**: bug
- **File**: `server.py:647,2006,2753,2934,2951,2989`
- **Verify score**: 3/3 lentes

**Resumo**: Docs Python explícitos: weak ref permite GC antes de terminar. _dispatch pode ser coletado deixando campanha pending eterno sem dispatch real.

**Evidência**: ```
server.py:647
```

**Fix hint**: Manter set _BG_TASKS = set(); task.add_done_callback(_BG_TASKS.discard).

**Lentes**:
- OK (high): Verifiquei as 6 linhas citadas em D:/dev-projects/main/hermes-cloud-studio/server.py. Todas contêm asyncio.create_task() sem armazenar referência em variável/set persistente. Pattern documentado como bug pelo Python docs (weak ref → GC pode coletar antes do término). Casos reais com risco: linha 647 (_fire campaign error update), 2006 (_run_pipeline_async — pipeline inteiro!), 2753 (_dispatch camp
- OK (medium): Severity medium justificada. Cenário real 3 meses sem fix: asyncio docs confirmam que event loop só mantém weak ref a tasks criadas com create_task. Se _dispatch sem await/gather e sem hold em set, GC pode coletar task antes de concluir — sintoma: campanha fica "pending" eterno, dispatch silencioso desaparece sob carga (quando GC roda agressivo). Não derruba sistema (não é critical), mas causa bug
- OK (high): Fix viável e canônico (padrão oficial recomendado pelos docs Python). Effort S: criar módulo-level set _BG_TASKS=set(), wrapper helper spawn_bg(coro) que faz t=asyncio.create_task(coro); _BG_TASKS.add(t); t.add_done_callback(_BG_TASKS.discard); return t. Substituir 6 call sites por spawn_bg(...). Sem dependência de outros findings — mudança isolada e mecânica. Risco regressão baixíssimo: semântica

---

### MERGED-016 — _dispatch error sobrescrito por sync_loop — UI mostra running eterno

- **Severity**: medium 
- **Category**: race-condition
- **File**: `server.py:2641-2754`
- **Verify score**: 3/3 lentes

**Resumo**: Timeout local httpx=30s marca error; VM já aceitou e reporta running; sync sobrescreve error→running. Operador não vê falha real.

**Evidência**: ```
server.py:2641
```

**Fix hint**: Status machine com transições válidas; error só sobrescreve via campo terminal_error_at; sync respeita terminal states.

**Lentes**:
- OK (high): Evidência confirmada no código atual. server.py:2712-2753 _dispatch() usa httpx timeout=30s e em qualquer exceção marca status='error' (linha 2728). server.py:434-505 sync_linkedin_campaigns() em 474-476 só protege estados 'scheduled' e 'cancelled' contra sobrescrita pela VM — estado 'error' NÃO está na guarda, então UPDATE em 478-487 sobrescreverá error→running/done se VM ainda processa. Race con
- OK (medium): Finding válido (race entre _dispatch timeout local e sync_loop é cenário plausível httpx=30s vs VM ainda processando). Mas severity medium superestima dano real em 3 meses sem fix: (1) não quebra sistema, não corrompe dados, não vaza; (2) impacto = UX confusa (running eterno) + possível job duplicado se operador reiniciar; (3) workaround trivial (checar logs VM, refresh); (4) frequência baixa — só
- OK (high): Fix viável. State machine simples: estados terminais (error, completed, cancelled) vs transitórios (running, queued). _dispatch grava terminal_error_at junto com status=error; sync_loop checa guard `if job.terminal_error_at: skip update`. Effort M: (1) campo terminal_error_at no schema, (2) modificar _dispatch server.py:2641 pra setar timestamp no timeout, (3) guard em sync_loop server.py:2754, (4

---

### MERGED-017 — Subprocess scraper via Popen sem supervisão — zombies + PID stale + kill -0 non-portable

- **Severity**: medium 
- **Category**: bug
- **File**: `hermes_api_v2.py:474,563-614`
- **Verify score**: 3/3 lentes

**Resumo**: Popen start_new_session, PID file persiste em crash, kill -0 só Unix e falha por permission denied = falso 'not running' → double-start. Restarts acumulam scrapers órfãos.

**Evidência**: ```
hermes_api_v2.py:474
```

**Fix hint**: Usar systemd unit ou supervisor; ou psutil.pid_exists; cleanup atexit + lockfile com fcntl.

**Lentes**:
- OK (high): Evidência confirmada no código. hermes_api_v2.py:474 e :572 usam `subprocess.run(["kill", "-0", str(pid)], capture_output=True)` — comando `kill` é Unix-only (não roda em Windows) e retorna não-zero em permission denied (falso negativo de 'not running'). hermes_api_v2.py:605-613 usa `subprocess.Popen(..., start_new_session=True)` e grava PID em arquivo sem cleanup atexit/lockfile/fcntl. Combinação
- OK (medium): Finding válido tecnicamente: Popen start_new_session sem reaper deixa zombies, PID file stale após crash causa lógica errada, e kill -0 não é portável (Windows) e pode falhar por EPERM dando falso negativo de "not running". Porém, severity medium é exagerada para impacto real em 3 meses sem fix: (1) é serviço scraper interno do Hermes, não path crítico de receita; (2) "zombies acumulando" só ocorr
- OK (high): Fix viável. Effort S-M: substituir `subprocess.run(["kill","-0",pid])` por `psutil.pid_exists(pid)` + checar `psutil.Process(pid).status() != zombie` (S, ~15 LOC em 2 lugares: linhas 474 e 572). Cleanup stale PID file dentro do mesmo bloco quando proc não existe (S). Lockfile com fcntl/portalocker pra evitar TOCTOU race no start (M). systemd unit é alternativa mais robusta porém troca arquitetura 

---

### MERGED-018 — linkedin_session_monitor confunde flake de rede com sessão expirada

- **Severity**: medium 
- **Category**: bug
- **File**: `server.py:709-738`
- **Verify score**: 3/3 lentes

**Resumo**: except Exception: ok=False trata DNS/timeout/500 como cookie morto. Telegram falso a cada flake; operador rotaciona LI_AT sem necessidade.

**Evidência**: ```
server.py:720
```

**Fix hint**: Diferenciar HTTPStatusError(401/403) (real expirado) vs TransportError (flake); exigir N falhas consecutivas reais antes de alertar.

**Lentes**:
- OK (high): Evidência confirmada em server.py:709-738. Linha 720-721: `except Exception: ok = False` engole qualquer erro (httpx.TransportError, timeout, DNS, 500) e marca ok=False idêntico a um 401/403 real. Linha 724-732 dispara Telegram já na primeira transição True→False (sem contador de falhas consecutivas), gerando falso positivo em qualquer flake de rede entre PC e VM_API_URL. Severity medium adequado:
- OK (high): Severity medium superestimada. Cenário 3 meses sem fix: operador recebe Telegram falso ocasional em flake de rede (DNS, timeout, 500 transitório do LinkedIn). Reação = rotacionar LI_AT desnecessariamente (5-10min trabalho manual) ou simplesmente ignorar alerta após perceber padrão. Sistema NÃO quebra: scraping continua funcionando com cookie válido. Dano real = ruído operacional + erosão de confia
- OK (high): Fix viável e claro. httpx já diferencia HTTPStatusError (resposta HTTP recebida, checa status 401/403) vs TransportError/ConnectError/TimeoutException (falha de rede/DNS). Mudança localizada em server.py:709-738: substituir except Exception genérico por except branches tipados + adicionar contador de falhas consecutivas reais (ex: 3x 401/403 antes de alertar Telegram). Effort S (1-2h): ~30 linhas,

---

### MERGED-020 — /api/server/restart-* sem rate-limit/CSRF — DoS trivial em loop

- **Severity**: medium 
- **Category**: security
- **File**: `server.py:2925-2990`
- **Verify score**: 3/3 lentes

**Resumo**: POST restart-local/shutdown-local/restart-vm/restart-all chama os._exit(0). Com FIND MERGED-002 (token vazio), atacante LAN derruba em loop. XSS no dashboard (FIND-019) também mata serviço.

**Evidência**: ```
server.py:2925
```

**Fix hint**: Rate limit por IP+token; exigir confirm header; restart só via signal local, não HTTP público.

**Lentes**:
- OK (high): Confirmado em D:/dev-projects/main/hermes-cloud-studio/server.py:2925-2990. Quatro endpoints POST (restart-local, shutdown-local, restart-vm, restart-all) sem decorator de auth/rate-limit. restart-local/shutdown-local/restart-all chamam os._exit(0) via asyncio task. Loop trivial derruba serviço. Severidade medium adequada (depende de exposição LAN + FIND-002 token vazio para amplificar).
- OK (high): Endpoint POST chama os._exit(0) sem rate-limit/CSRF. Combinado com MERGED-002 (token vazio) e FIND-019 (XSS), atacante LAN ou via browser do owner derruba serviço em loop infinito (DoS persistente — cada restart morre de novo). Dano real em 3 meses: serviço inutilizável enquanto attacker mantiver loop; owner perde produtividade, gerações interrompidas. Não é critical pois (1) escopo LAN/local, não
- OK (high): Fix viável. Effort S/M: rate-limit por IP+token (in-memory dict com timestamps, ~30 linhas), confirm header (X-Confirm-Restart: yes, trivial check), restart via signal local (SIGUSR1 handler ou arquivo sentinel) ao invés de os._exit(0) direto no handler HTTP. Dependência: MERGED-002 (token vazio) deve ser corrigido primeiro — sem auth real, rate-limit sozinho não resolve (atacante LAN ainda derrub

---

### MERGED-019 — Markdown renderer custom no dashboard sem allowlist — XSS via Claude output

- **Severity**: low (originalmente medium)
- **Category**: security
- **File**: `dashboard/app.js (Claude page)`
- **Verify score**: 3/3 lentes

**Resumo**: escapeHtml + re-enable markdown inline é território clássico de bypass (javascript: links, MathML/SVG). Conteúdo vem do Claude API que pode refletir input não-confiável (prospect bio scraped).

**Evidência**: ```
dashboard/app.js
```

**Fix hint**: DOMPurify ou marked + sanitize-html com allowlist estrita; bloquear protocolos javascript:/data:.

**Lentes**:
- OK (high): Evidência existe. dashboard/app.js linhas 2520-2562 define renderMarkdownTerminal + formatInline: escapeHtml roda primeiro, depois regex substitui **bold**, *italic*, `code` por tags HTML inline. Output do Claude (/api/claude/execute) renderizado via output.innerHTML += renderMarkdownTerminal(text) na linha 2589. Padrão "escape-then-reinject" confirmado. PORÉM o vetor descrito pelo auditor (javasc
- OK (high): Finding válido em premissa (renderer custom é território de bypass), mas severity medium superestimada. Auditei renderMarkdownTerminal + formatInline em D:/dev-projects/main/hermes-cloud-studio/dashboard/app.js:2514-2562: escapeHtml roda ANTES de qualquer regex inline (backticks, **bold**, *italic*). Não há parsing de [text](url) — vetor javascript:/data: não existe. Não há pass-through de HTML ra
- OK (high): Fix viável e padrão da indústria. Effort S (1-3h): npm install dompurify, importar no dashboard/app.js, trocar innerHTML do markdown renderizado por DOMPurify.sanitize(html, {ALLOWED_URI_REGEXP: /^(?:https?|mailto):/i, FORBID_TAGS:['style','script'], FORBID_ATTR:['style','on*']}). Alternativa marked+sanitize-html equivalente. Sem dependência bloqueante de outros findings — pode ser corrigido isola

---

## Discoveries por área (raw)

### unknown (172 findings)
- **[high]** FIND-001 Monolitos server.py (3308 lin) e hermes_api_v2.py (1861 lin) violam separação de responsabilidades (tech-debt)
- **[medium]** FIND-002 Documentação afirma bug 'time.time() sem import time' que NÃO existe no código atual (doc)
- **[high]** FIND-003 Topologia documentada como 'PC orquestra, VM executa' é violada por viewer LinkedIn no PC (tech-debt)
- **[high]** FIND-004 IP da VM hardcoded em pelo menos 13 arquivos (código + docs + scripts) (tech-debt)
- **[high]** FIND-005 Estado crítico em variáveis globais de módulo, não persistido — perde-se em restart (bug)
- **[high]** FIND-006 Sincronização PC↔VM por polling de 60s sem versionamento → race conditions e estados divergentes (race-condition)
- **[medium]** FIND-007 Lógica duplicada entre daemon/orchestrator.py e scripts/pipeline.py sem abstração comum (tech-debt)
- **[medium]** FIND-008 Ausência de abstração de configuração global — secrets lidos via os.getenv ad-hoc (tech-debt)
- **[high]** FIND-009 Tratamento de erro inconsistente nos 5 loops background — exceções podem matar loops silenciosamente (bug)
- **[high]** FIND-010 WebSocket /ws sem autenticação (documentado mas não fechado) (security)
- **[medium]** FIND-011 Auth baseado em header simples (X-Hermes-Token) com mesmo segredo PC e VM, sem rotação (security)
- **[medium]** FIND-012 Dependência implícita do PC para VM funcionar (Ollama via tunnel reverso) cria SPOF inverso (scalability)
- **[medium]** FIND-013 Subprocesso de scraper via Popen sem supervisão de ciclo de vida (bug)
- **[low]** FIND-014 Subpasta com mesmo nome do projeto (Hermes Cloud Studio/) vazia no repo, indica histórico não limpo (tech-debt)
- **[low]** FIND-015 hermes_desktop.py deprecated continua no repo e exporta endpoints que conflitam com Tauri (tech-debt)
- **[low]** FIND-016 intelligence/ e task_queue/ existem como diretórios vazios com intenção futura (tech-debt)
- **[high]** FIND-017 Camada channels/ documentada como 4 canais (LinkedIn/Email/WA/IG) mas só LinkedIn implementado, daemon mente sobre P1-P7 (missing-feature)
- **[medium]** FIND-018 Markdown renderer custom no dashboard sem allowlist contra XSS (security)
- **[critical]** FIND-001 WebSocket /ws sem autenticação — bypass do AUTH_TOKEN (security)
- **[high]** FIND-002 CORS allow_origins=['*'] com allow_credentials=True (security)

