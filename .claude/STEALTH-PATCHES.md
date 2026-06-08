# Hermes — Anti-Detection Patches (2026-06-07)

Gerado por workflow `linkedin-anti-detection-sweep`.
8 patches confirmados de 15 propostos. 48 findings de pesquisa em 3 angulos.

## Resumo executivo

Pesquisa convergente em 2024-2026 e a analise do stealth.py atual revelam que o Hermes esta em risco critico de queima imediata em 4 vetores: (1) incoerencia cross-attribute do fingerprint (UA/platform/userAgentData/sec-ch-ua/WebGL), (2) JA3/JA4 TLS detectaveis sem Chrome stable + PQ key exchange, (3) proxy/session model incompativel com binding li_at+IP+fingerprint que LinkedIn enforce em 2026, e (4) comportamento mecanico (mouse teleport, fill instantaneo, sem dwell/scroll, rate limits desatualizados). Os 15 patches priorizam essas 4 frentes com 5 criticos (PATCH-001 a 005) que devem entrar antes de qualquer outreach, seguidos de behavioral hardening (006-010) e refinamentos de fingerprint surface (011-013) e governance (014-015). Testar tudo em lab accounts descartaveis via creepjs/tls.peet.ws/browserleaks antes de tocar conta de producao.

## Patches confirmados (>=2 lentes valid)

### PATCH-003 — Mobile/ISP sticky proxy 1:1 por account

- **Severity**: critical · **Effort**: M · **Category**: network
- **Target**: `D:/dev-projects/main/hermes-cloud-studio/linkedin/stealth.py`
- **Verify score**: 3/3 lentes

**Descricao**: Datacenter IP queima li_at em 1 sessao. Residencial rotativo quebra session continuity. Solucao 2026: 1 ISP static OU mobile carrier IP dedicado por account, sticky 24h-7d, geo alinhada com timezone/locale do profile. Ganho: 50% -> 85% account survival.

**Sketch**:
```
1) Tabela accounts {account_id, proxy_endpoint, proxy_user, proxy_pass, sticky_session_id, geo, timezone}. 2) launch_persistent_context com proxy={server, username:f'user-session-{sticky}', password}. 3) sticky_session_id rotaciona a cada 24h-7d, NUNCA mid-session. 4) Pre-flight: ipinfo.io/json, abortar se ASN datacenter (Google/AWS/OVH/Hetzner). 5) Match timezone_id e locale com geo do IP.
```

**Test plan (lab)**: Lab account descartavel: fazer login, validar nao cai authwall. Rodar 50 profile views distribuidos em 4h. Trocar sticky session entre runs, nunca durante. Conferir li_at persistencia 24h+ no mesmo IP.

**Sources**: use-apify.com best-proxies-linkedin · torchproxies.com why-most-proxies-fail · research.aimultiple.com linkedin-proxies · dataimpulse.com

**Lentes**:
- OK (medium): Tecnica correta no principio: ISP/mobile sticky 1:1 por account e consenso 2025-2026 pra LinkedIn (datacenter queima na hora, residencial rotativo quebra session). stealth.py ja aceita proxy via launch_persistent_context e ja seta timezone_id — patch e extensao natural. Falhas logicas no sketch: (1) sticky_session_id "rotaciona 24h-7d" e ambiguo — LinkedIn pin IP via li_at, qualquer troca de IP no mesmo cookie dispara challenge, entao rotacao deveria ser NUNCA enquanto li_at vivo, nao 24h-7d arbitrario; (2) pre-flight ipinfo.io revela ASN mas muitos provedores ISP residencial usam ASN proprio que pode ser flagged tb — checar so Google/AWS/OVH/Hetzner e insuficiente, falta blocklist M247/DataCamp/Cogent/etc e checagem via IPQualityScore/Spur fraud_score; (3) "match timezone com geo" precisa cobrir tb locale (Accept-Language), WebRTC leak (Playwright nao bloqueia STUN por padrao — IP real vaza), e geolocation API; (4) launch_persistent_context proxy nao suporta rotacao de user/pass mid-context, ok pra sticky mas precisa garantir mesmo IP em reconexao (sticky session token no username); (5) faltou DNS leak (proxy precisa fazer DNS remoto, nao local); (6) faltou fallback quando proxy cai mid-session — deve abortar, NUNCA continuar via IP direto. Implementavel mas sketch incompleto em areas que decidem deteccao.
- OK (medium): Feasibility OK. stealth.py ja plumbed proxy_server/username/password em launch_persistent_context (linhas 276-283). Patchright/Playwright suporta proxy auth + sticky session via username encoding (user-session-{id}) — padrao Bright Data/Smartproxy/IPRoyal, sem hack. Effort M realista: (1) tabela accounts (SQLite ja existe no projeto provavel, senao trivial); (2) wire sticky_session_id no proxy_username — 5 linhas; (3) pre-flight ipinfo.io/json + ASN blocklist — fetch HTTP simples, ~30 linhas; (4) geo/timezone match — config.locale e timezone_id ja sao parametros de launch_persistent_context. Riscos: (a) custo proxy mobile/ISP dedicado ($15-50/mes por IP) — operacional, nao tecnico; (b) provider escolha (DataImpulse/IPRoyal/Soax) define API de sticky — pode exigir ajuste de username format; (c) ipinfo.io rate-limit free tier (50k/mes) — ok pra escala atual; (d) sticky rotation 24h-7d precisa scheduler/cron, nao mid-session — gerenciavel via campo last_rotated_at. Nenhuma dependencia instavel: requests/httpx pra ipinfo, sqlite pra tabela. Sem monkeypatch Playwright.
- OK (medium): Patch ataca vetor critico real: datacenter IP queima li_at em 1 sessao (vetor #1 deteccao LinkedIn 2026). Codigo atual em stealth.py:276-281 ja aceita proxy via config mas SEM validacao ASN, SEM sticky session mgmt, SEM alinhamento geo/timezone. Patch e aditivo a camada de rede, nao mexe nos JS stealth patches (linhas 61-189) nem no Patchright flow, entao NAO causa overshoot de fingerprint. timezone_id e geolocation ja sao passados ao context (linhas 261-262), patch apenas exige sincronizar com geo do IP proxy — correto. Risco vs beneficio: beneficio (50%->85% account survival) supera riscos de implementacao.

---

### PATCH-004 — WebGL renderer coerente com UA class + 65 params

- **Severity**: critical · **Effort**: M · **Category**: fingerprint
- **Target**: `D:/dev-projects/main/hermes-cloud-studio/linkedin/stealth.py`
- **Verify score**: 3/3 lentes

**Descricao**: LinkedIn coleta 65+ WebGL parameters e cruza UNMASKED_RENDERER com classe do UA. Se UA=Windows Chrome desktop, renderer precisa ser GPU desktop plausivel (NVIDIA/Intel/AMD), nunca SwiftShader (headless) nem Mesa (Linux VM). Patch atual nao spoofa WebGL.

**Sketch**:
```
1) Pool de RendererProfile {vendor, renderer, params_dict de 65 chaves} extraido de Chrome real em hardware diverso. 2) 1 RendererProfile por account_id (sticky). 3) Override WebGLRenderingContext.prototype.getParameter e WebGL2 igual: switch sobre param id, retornar valor do profile. 4) Tambem patchar getSupportedExtensions e getShaderPrecisionFormat. 5) Garantir que renderer bate com platform escolhido em PATCH-001 (Mac=Apple GPU, Win=NVIDIA/Intel).
```

**Test plan (lab)**: browserleaks.com/webgl: comparar com Chrome real do mesmo OS. creepjs gpu lies = 0. webglreport.com mostrar 65 params consistentes. Verificar headless mode nao expor SwiftShader.

**Sources**: castle.io detecting-forged · geetest.com botbrowser-2025 · proxies.sx fingerprinting · code_gaps Patch nao implementado

**Lentes**:
- OK (medium): Tecnica fundamentalmente correta e enderecca o gap real. Patch atual em stealth.py linhas 128-142 so spoofa 2 params (37445 vendor, 37446 renderer) hardcoded NVIDIA GTX 1660 SUPER — exatamente o problema descrito. LinkedIn/Castle/Geetest de fato cruzam UA class x renderer e coletam 60+ WebGL params (MAX_TEXTURE_SIZE, MAX_VIEWPORT_DIMS, MAX_VERTEX_ATTRIBS, ALIASED_LINE_WIDTH_RANGE, depth/stencil bits, shader precision, extensions list etc). Pool de profiles sticky por account_id + coerencia com platform do PATCH-001 sao corretos. Falhas/lacunas no sketch que reduzem confidence pra medium: (1) Nao menciona OffscreenCanvas WebGL context — LinkedIn pode chamar via worker e bypassar override do main thread; precisa patchar em worker init tambem. (2) Override de getParameter via JS prototype eh detectavel por toString/Function.prototype.toString — sketch nao menciona Proxy + toString spoofing (Function.prototype.toString.call(getParameter) deve retornar "function getParameter() { [native code] }"). (3) getShaderPrecisionFormat retorna objeto {rangeMin,rangeMax,precision} — sketch diz "patchar" mas nao detalha que valores tem que bater com GPU class (mobile vs desktop diferem). (4) Nao trata WEBGL_debug_renderer_info extension visibility — alguns browsers exigem extension ativa pra retornar UNMASKED_*; spoof precisa preservar esse gate. (5) Pixel-level: readPixels/drawingBufferWidth/getContextAttributes nao mencionados — fingerprint real inclui antialias actual behavior, nao so params. (6) Sketch nao aborda que 65 params coerentes exigem dataset real extraido (afirmado em (1) mas sem fonte/scraper); risco de profile sintetico ter combinacao impossivel (ex: MAX_TEXTURE_SIZE=16384 com vendor mobile). (7) Headless Chromium ainda renderiza via SwiftShader no backend — spoof JS engana getParameter mas se LinkedIn fizer GPU timing attack (rendering benchmark) detecta. Mitigacao requer GPU real (--use-gl=angle + hardware) nao mencionada. Patch eh necessario e direcionalmente correto; sketch precisa expandir nesses 7 pontos antes de implementar.
- OK (high): Feasibility OK. Patch atual em stealth.py:128-142 ja spoofa params 37445/37446 via addInitScript — extender pra 65 params eh extensao direta do mesmo padrao, sem hack pesado. Playwright/Patchright suportam page.add_init_script nativo (ja usado no arquivo). RendererProfile pool = dict Python estatico carregado de JSON, sticky por account_id via hash (trivial). Override getSupportedExtensions/getShaderPrecisionFormat = mesma tecnica de prototype patching ja aplicada. Effort M (1-2 dias) realista: (a) coletar 5-10 perfis reais via browserleaks/webglreport ~3-4h, (b) refactor dos blocos 8 em stealth.py pra receber profile injetado ~2h, (c) coerencia com PATCH-001 platform via lookup table {win:[nvidia,intel], mac:[apple]} ~1h, (d) testes em browserleaks/creepjs ~2-3h. Sem deps externas novas. Risco baixo: param IDs WebGL sao constantes WebGL spec estaveis; getShaderPrecisionFormat retorna struct fixo (rangeMin/rangeMax/precision) facilmente mockavel. Dependencia critica: PATCH-001 (UA platform) precisa landed antes pra coerencia.
- OK (medium): Patch atual (linhas 128-142) spoofa apenas 2 params (37445/37446) hardcoded NVIDIA GTX 1660 — quebra coerencia se PATCH-001 escolher Mac/Intel/AMD, e LinkedIn cruza com 63+ outros params reais do hardware host (cloud VM tipicamente Mesa/SwiftShader). RISCO ATUAL > RISCO DO PATCH: fingerprint hibrido (renderer=NVIDIA + MAX_TEXTURE_SIZE/precision=Mesa) ja eh red flag classica detectada por castle.io/creepjs. Patch endereca gap real.

RISCOS DE QUEBRAR FLUXOS: baixo. WebGL spoofing nao afeta DOM/navegacao LinkedIn (login, scroll, search). LinkedIn nao usa WebGL para features funcionais — apenas fingerprinting passivo. getSupportedExtensions/getShaderPrecisionFormat override pode quebrar se algum widget 3D usar (improvavel no LinkedIn).

RISCOS DE OVERSHOOT: medio-alto se mal executado:
1. Pool pequeno (<20 profiles) = cluster detectavel entre accounts
2. Profile sticky por account_id OK, mas se trocar IP/UA sem trocar profile = inconsistencia temporal
3. Params dict de 65 chaves precisa vir de captura REAL (nao sintetico) — valores inventados batem mal entre si (ex: MAX_VIEWPORT_DIMS incompativel com MAX_TEXTURE_SIZE para aquela GPU)
4. getShaderPrecisionFormat retornar valores fake quebra shaders WebGL legitimos (canvas2d/CSS filter podem falhar) — overshoot real
5. Headless Chrome ainda vaza via timing de readPixels/canvas hash mesmo com params spoofados — patch isolado nao resolve

TEST_PLAN GAPS:
- Nao testa coerencia cross-patch (PATCH-001 UA Mac + renderer NVIDIA = fail)
- Nao testa entropy/uniqueness do pool (so testa 1 profile)
- Nao testa LinkedIn real (so browserleaks/creepjs) — LinkedIn tem fingerprinting proprietario nao coberto
- Falta teste de regressao: login flow + feed scroll + search apos patch
- Falta verificar se getShaderPrecisionFormat override nao quebra LinkedIn UI (canvas avatars, charts)

VEREDICTO: valid=true (gap real, severity critical justificada, beneficio > risco SE implementado com pool capturado de hardware real + coerencia com PATCH-001 + test de regressao funcional). Caveats abaixo sao bloqueantes.

---

### PATCH-005 — navigator.webdriver patch via prototype, nao instancia

- **Severity**: critical · **Effort**: S · **Category**: fingerprint
- **Target**: `D:/dev-projects/main/hermes-cloud-studio/linkedin/stealth.py`
- **Verify score**: 2/3 lentes

**Descricao**: Patch atual na linha 63 define webdriver na instancia navigator. CreepJS/fp-collect detectam via Object.getOwnPropertyDescriptor(Navigator.prototype,'webdriver') (deve existir no prototype, nao na instancia) e validam estrutura do descriptor.

**Sketch**:
```
1) delete Navigator.prototype.webdriver. 2) Object.defineProperty(Navigator.prototype,'webdriver',{get:()=>false, configurable:true, enumerable:true}). 3) Patchar getter.toString() = 'function get webdriver() { [native code] }'. 4) Verificar Reflect.getOwnPropertyDescriptor(navigator,'webdriver') === undefined (so existe no prototype).
```

**Test plan (lab)**: creepjs lies section -> webdriver = 0 lies. bot.sannysoft.com -> webdriver row green. fingerprint.com bot detection score baixo. Console: Object.getOwnPropertyDescriptor(Navigator.prototype,'webdriver') retorna descriptor; Object.getOwnPropertyDescriptor(navigator,'webdriver') retorna undefined.

**Sources**: code_gaps Patch 1 · github.com/Kaliiiiiiiiii-Vinyzu/patchright-python/issues/46

**Lentes**:
- OK (medium): Tecnica correta no core: webdriver real do Chrome vive em Navigator.prototype (nao na instancia), entao detectores comparam Object.getOwnPropertyDescriptor(Navigator.prototype,'webdriver') vs (navigator,'webdriver'). Patch atual linha 63 define na instancia -> deteccao trivial. Sketch resolve: delete prototype + defineProperty no prototype + toString nativo do getter + verificacao instancia undefined. Ressalvas: (1) delete Navigator.prototype.webdriver pode falhar se descriptor original for non-configurable em algumas versoes do Chrome — precisa try/catch ou redefinir direto. (2) toString() spoofing precisa tambem cobrir Function.prototype.toString.call(getter) e toString.toString (Proxy no Function.prototype.toString eh padrao em puppeteer-extra-stealth, sketch nao menciona). (3) enumerable:true esta correto (nativo eh enumerable). (4) Script roda via add_init_script antes do document — ok. (5) Falta validar que getter.name === 'get webdriver'. Sketch resolve a deteccao principal mas toString leak via Function.prototype.toString.call eh gap residual que CreepJS checa.
- OK (high): Patch trivial em add_init_script. JS puro, sem dep extra. Playwright/Patchright suportam add_init_script nativamente (linha 300 ja usa). Effort S realista: ~10 linhas JS substituindo linha 63. Sem hack pesado — defineProperty no Navigator.prototype + toString spoof eh padrao puppeteer-extra-stealth ha anos, bem documentado. Caveat: patch so executa em vanilla Playwright (linha 303 `if not use_patchright`); Patchright ja faz isso nativamente, entao patch redundante quando Patchright ativo — precisa garantir que substituicao do _STEALTH_SCRIPTS[0] nao quebre fallback. Outro caveat: ordem do toString spoof (item 11) precisa rodar APOS o defineProperty pro getter ser capturado no _patchedFns; sketch atual nao integra com infra existente de _patchedFns.
- FAIL (high): Patch correto em conceito (prototype > instance é melhor pra CreepJS/fp-collect), mas sketch incompleto e test_plan inadequado. Três problemas críticos: (1) Path padrão do stealth.py usa Patchright (linha 303 — `if not use_patchright`), que já patcha webdriver via CDP. _STEALTH_SCRIPTS só roda no fallback vanilla Playwright — benefício real do patch é marginal no fluxo de produção. (2) Sketch propõe patchar getter.toString() = native code string, MAS script 11 já instala Function.prototype.toString patch via _patchedFns Set. Se novo getter não for registrado em _patchedFns (sketch não menciona), Function.prototype.toString.call(descriptor.get) vaza implementação custom → DETECÇÃO PIOR que o patch atual (overshoot stealth real). (3) test_plan só valida descriptor location + CreepJS lies, NÃO cobre: regressão de fluxo LinkedIn (login → feed → search → message), toString chain do getter novo, interação com script 11, comportamento quando Patchright já patchou webdriver (double-patch pode quebrar). Risco > benefício: fluxo LinkedIn já passa hoje no path Patchright; mexer no fallback sem teste de regressão LinkedIn end-to-end e sem integrar com toString patch existente cria risco de quebra de fluxo funcionando + risco de overshoot.

---

### PATCH-007 — Rate limiter conservador 2026 (20-30 conn/dia, 100/sem)

- **Severity**: critical · **Effort**: M · **Category**: rate
- **Target**: `D:/dev-projects/main/hermes-cloud-studio/linkedin/stealth.py`
- **Verify score**: 2/3 lentes

**Descricao**: Limites antigos (100/dia) garantem ban. Atualizar para 20-30 conn requests/dia, 50-80 msgs/dia, 10-15 profile views/IP/hora, 5 notas personalizadas/sem (free), 300 searches/mes (CUL). Rolling 7-day window para conn cap 100/sem.

**Sketch**:
```
1) RateBudget per account_id em SQLite/Redis: counters daily, weekly_rolling_7d, monthly_cul, hourly_views. 2) Antes de qualquer acao: check budget, se exceder -> postpone. 3) Distribuir acoes em janelas de horario comercial do timezone do IP (9h-19h local), 0 acoes 22h-7h. 4) Inserir jitter exponencial entre acoes (mean 4-8min, nao constante). 5) Hard stop em 70% do cap.
```

**Test plan (lab)**: Simular 30 dias em lab account, assert nunca excede limites. Inspecionar distribuicao temporal: nao deve ter pattern 24/7 nem intervalos constantes. KS test contra distribuicao humana de referencia.

**Sources**: botdog.co linkedin-faq-2025 · phantombuster.com connection-request-limit · phantombuster.com commercial-use-limit · getsales.io safety-2026 · dux-soup.com safety-2026 · bearconnect.io

**Lentes**:
- FAIL (high): Patch target file (stealth.py) is wrong scope — that module handles browser fingerprint/anti-detection, not rate budgeting. Rate limiter belongs in separate module (e.g., rate_budget.py or scheduler). Mixing concerns violates separation. Implementation sketch issues: (1) "Hard stop em 70% do cap" with cap=20-30/day means effective 14-21/day — fine but ambiguous: is 20-30 the hard cap or soft target? Conflict with "nunca excede limites". (2) Rolling 7d weekly cap 100/sem vs 20-30/day: 7*30=210 — daily cap can exceed weekly; interaction unspecified (which dominates?). (3) "Janelas horario comercial do timezone do IP" — risky: if proxy IP timezone differs from account profile/registered location, mismatch itself is a detection signal. Should be account's declared timezone, not IP. (4) KS test "contra distribuicao humana de referencia" — no reference dataset specified; LinkedIn's actual human baseline is private. Unverifiable test. (5) Jitter "exponencial mean 4-8min" — exponential distribution with that mean produces frequent very-short intervals which look bot-like in bursts; log-normal or gamma better for human-like inter-arrival. (6) "5 notas personalizadas/sem (free)" — outdated: LinkedIn free reduced free invitations significantly; numbers from sources may already be stale. (7) No mention of weekend/holiday throttling, no warmup ramp for new accounts. (8) SQLite/Redis "per account_id" fine but no mention of crash recovery or distributed locking if multiple workers. Technique direction (budgets + jitter + business hours) is correct in principle but sketch has enough gaps and a wrong file target.
- OK (high): Infra ja existe: limiter.py tem SQLite, daily/weekly counters, warmup multiplier, working hours, cooldown. Patch reduz a ajustar config (caps numericos) + add monthly_cul counter + rolling 7d (ja implementado via _count_actions 168h) + jitter exponencial entre acoes. Sem dependencias instaveis — sqlite + datetime + random.expovariate stdlib. Patchright/Playwright nao envolvido (limiter e pure Python). Effort M realista: ~150-250 LOC, mexer config.py defaults + adicionar monthly counter + ajustar jitter em human.py/connector.py. Risco baixo. Target_file errado no patch (stealth.py) — logica vive em limiter.py + config.py.
- OK (medium): PATCH-007 alvo errado (stealth.py = browser launcher, sem rate). Limites pertencem a config.py + limiter.py. MAS premissa do patch ("100/dia garante ban") é FALSA — config.py ja tem free=30 conn/dia, weekly=40, lurking 7d, working hours, warmup 14d. Patch overshoot: defaults atuais ja sao mais conservadores que sketch (30 vs "20-30 OK"). Risco real: aplicar literal quebraria account_type=premium/sales_navigator (perderia 80/150 conn legitimos), conflitaria com warmup_action_multiplier e LURKING_PCT existentes, e duplicaria logica weekly rolling (limiter.py ja faz 168h window). Beneficios adicionais validos: (a) per-IP hourly views cap (10-15/hora) NAO existe — gap real, (b) jitter exponencial mean 4-8min vs atual 3-15s constant — atual sketch real demais (atual delay 3-15s entre acoes pode parecer bot), (c) hard stop 70% cap nao existe (atual permite 100% ate bater limite). test_plan razoavel mas falta: regressao em accounts premium/sales_nav, teste de coexistencia com warmup curve, validacao de que 70% hard stop nao quebra campanhas existentes mid-flight. Recomendo aplicar PARCIAL: adicionar (1) hourly_profile_views cap, (2) ampliar min_action_delay para distribuicao log-normal mean 240-480s, (3) 70% soft warning + 85% hard stop. NAO mexer em daily/weekly caps existentes — ja safe. valid=true porque patch identifica gaps reais (hourly cap, jitter quality, hard stop), mesmo com target_file errado e premissa numerica falsa.

---

### PATCH-008 — Session continuity: li_at + IP + fingerprint binding

- **Severity**: critical · **Effort**: M · **Category**: session
- **Target**: `D:/dev-projects/main/hermes-cloud-studio/linkedin/stealth.py`
- **Verify score**: 3/3 lentes

**Descricao**: li_at e amarrado a IP de login + fingerprint + geo. Trocar IP/UA/canvas durante sessao mata cookie e dispara security alert. Persistir bundle (fingerprint_seed, proxy_session_id, cookies Netscape) por account e reutilizar identico em todo run.

**Sketch**:
```
1) AccountProfile JSON persistente per account_id: {os_profile, renderer_profile, fingerprint_seed, proxy_endpoint+sticky_id, locale, timezone, cookies_path}. 2) Load no inicio, save no fim. 3) NUNCA regenerar fingerprint se cookies validos existem. 4) Export/import cookies Netscape format. 5) Detector de cookie drift: se LinkedIn forca login -> marcar profile como queimado, NAO retry no mesmo IP.
```

**Test plan (lab)**: Login lab account, salvar profile. Reabrir 24h depois -> deve usar mesmo IP+fingerprint+cookies, NAO pedir re-login. Forcar mudanca de IP -> esperar redirecionamento para checkpoint, validar deteccao.

**Sources**: use-apify.com proxies-2026 · scrapfly.io linkedin · sales-mind.ai session-cookie · camoufox.com stealth · linkdapi.com without-ban · code_gaps

**Lentes**:
- OK (medium): Tecnica correta no principio: li_at + IP + fingerprint + UA precisam ser estaveis juntos. LinkedIn de fato cruza esses sinais e drift dispara checkpoint. Codigo atual ja persiste user_data_dir per-account (bom) e ja seed li_at, mas NAO amarra proxy_endpoint sticky a account, NAO persiste fingerprint_seed (atualmente WebGL/canvas hardcoded global iguais para todas contas — risco de "mesma maquina, N contas" detection), e NAO tem detector de cookie drift. Patch resolve gaps reais. Falhas logicas no sketch: (1) "NUNCA regenerar fingerprint se cookies validos" — fingerprint deve ser permanente per-account INDEPENDENTE de validade de cookie; regen so quando profile queimado/recriado. (2) "cookies Netscape format" — Playwright usa storage_state JSON; converter para Netscape adiciona complexidade sem ganho, manter JSON nativo. (3) Sketch nao especifica como detectar "cookie drift" alem de "LinkedIn forca login" — precisa observar redirects para /checkpoint/challenge, /uas/login, ou 401 em /voyager API, nao apenas URL final. (4) Marcar profile queimado e NAO retry mesmo IP esta certo, mas falta TTL/quarentena e politica de rotacao. (5) Risco: hoje codigo prefere env LI_AT sobre session_file — se patch persistir cookies por account mas extensao continua sobrescrevendo via env, ha conflito de fonte de verdade — precisa decidir uma so fonte.
- OK (high): FEASIBILITY: patch realista. Effort M (medio) coerente.

Base existente ja cobre 60% do patch:
- launch_persistent_context com user_data_dir per-account (preserva cookies/cache/localStorage automaticamente — Chrome profile dir e o "bundle persistente" nativo)
- proxy_server/username/password ja parametrizados em config
- timezone_id + geolocation amarrados a config
- Seed durable cookies (li_at) de session_file
- is_fresh_profile flag detecta primeira execucao

O que o patch adiciona (factivel sem hack pesado):
1. AccountProfile JSON sidecar (~/.hermes/profiles/<account_id>.json) com {fingerprint_seed, proxy_sticky_id, locale, timezone, user_data_dir, cookies_path, status} — trivial em Python, ~50 LOC
2. Sticky proxy session id — suportado nativamente por providers (Bright Data, Oxylabs, IPRoyal, Smartproxy) via username pattern tipo user-session-abc123; basta gerar UUID por account e passar no proxy_username. Zero hack.
3. Fingerprint seed reuse — fingerprint_seed e usado pra deterministicamente derivar WebGL renderer, hardware_concurrency, etc. Patchright tem fingerprint nativo coerente; pra Playwright fallback basta seed-driven _STEALTH_SCRIPTS (random com seed fixo). Sem dependencia instavel.
4. Cookies Netscape format — biblioteca http.cookiejar.MozillaCookieJar (stdlib). Zero deps extras.
5. Cookie drift detector — checar URL pos-navigate por /uas/login, /checkpoint/challenge, /authwall e marcar profile burned em JSON. Logica ja parcial via is_fresh_profile + error handling existente.

Riscos baixos:
- Patchright nao expoe API pra fixar fingerprint_seed determinístico (usa randomizacao interna). Mitigacao: confiar em persistent context — mesmo user_data_dir = mesmo profile state, Patchright reusa fingerprint do profile. Nao precisa controle granular.
- Sticky proxy depende do provider; se proxy atual nao suporta, requer upgrade de plano (custo $, nao tecnico).
- Netscape export/import e helper, nao bloqueia funcionalidade core.

Dependencias estaveis: Patchright (mantido), Playwright (Microsoft), stdlib json/http.cookiejar. Nenhuma instavel.

Effort M (~6-12h) realista: 2h AccountProfile dataclass+IO, 2h sticky proxy session gen, 2h drift detector + burned status, 2h Netscape import/export, 2h testes 24h reopen.
- OK (medium): RISK LENS — PATCH-008 (session continuity bundle)

VEREDICTO: valid=true, mas com CAVEATS pesados. Beneficio > risco SE implementado como camada aditiva sobre o stealth.py atual (que ja faz 70% do que o patch pede), NAO como rewrite.

ANALISE DO QUE JA EXISTE (stealth.py):
- user_data_dir persistente por conta = ja existe (linha 248). Cobre cookies/cache/localStorage/IndexedDB inteiro do Chrome, INCLUSIVE fingerprint estavel via mesma instalacao.
- proxy_server por config = ja existe (linha 276-281).
- timezone/geolocation por config = ja existe (linha 261-263).
- li_at env override + DURABLE_COOKIES seed = ja existe e e SUPERIOR ao "Netscape import" do patch (evita stale cookies que causam redirect loop — comentario linhas 312-318 documenta isso).
- Patchright + no_viewport + sem UA custom = ja segue best-practice (fingerprint = real Chrome).

GAPS REAIS QUE O PATCH ENDERECA (validos):
1. AccountProfile JSON consolidado (proxy_endpoint+sticky_id+timezone+geo+session_file path bound ao account_id) — HOJE config e global, nao per-account explicito. Util pra multi-conta.
2. Cookie drift detector / "profile queimado" flag — NAO existe. Hoje retry pode hammerar mesmo IP queimado.
3. Sticky proxy session id explicito — config.proxy_server e string crua; sem garantia de mesmo IP entre runs.

RISCOS DE QUEBRAR FLUXO EXISTENTE:
- "NUNCA regenerar fingerprint se cookies validos" — stealth.py ja NUNCA gera fingerprint (delega ao Chrome real). Patch pode induzir dev a adicionar fingerprint_seed manual (canvas/WebGL spoofing custom), o que e overshoot — Patchright ja resolve melhor. Risco de PIORAR deteccao se reintroduzir _STEALTH_SCRIPTS sobre Patchright (linha 303 explicitamente os desliga em Patchright).
- "Export/import cookies Netscape" — conflita com a logica atual de "minimal seed" (linhas 319-375) que foi escrita pra evitar redirect loop de stale cookies (lidc/JSESSIONID/bscookie). Reimportar bundle completo Netscape RESSUSCITA o bug que ja foi corrigido. ALTO RISCO de regressao.
- fingerprint_seed persistido = redundante com user_data_dir (Chrome ja persiste tudo).

TEST PLAN COBRE?
- "Login lab + 24h depois mesmo IP+fp+cookies" — OK, cobre happy path.
- "Forcar mudanca IP -> checkpoint" — cobre detector basico.
- NAO COBRE: regressao do redirect loop (stale lidc/JSESSIONID); rotacao de UA dentro da mesma sessao; conflito entre env LI_AT e bundle importado; comportamento quando sticky proxy expira mid-session.

RECOMENDACAO: aprovar SOMENTE escopo reduzido:
(a) AccountProfile dataclass com {account_id, proxy_sticky_id, timezone, geo, user_data_dir path, session_file path, burned_flag, last_login_ts} — additivo a LinkedInConfig.
(b) burned_flag setter quando detectar redirect pra /checkpoint ou /uas/login forcado — bloqueia retry no mesmo proxy_sticky_id.
(c) Sticky proxy session id no proxy URL (formato session-{account_id}-{sticky_token}).
REJEITAR: Netscape import (conflita com minimal-seed atual); fingerprint_seed custom (overshoot vs Patchright); regenerar fingerprint logic (inexistente, criaria bug).

Severity=critical do patch e EXAGERADO — stealth.py atual ja entrega ~70% disso. Reclassificar effort para S e severity para high.

---

### PATCH-009 — Behavioral signals: dwell, scroll, hover, feed warm-up

- **Severity**: high · **Effort**: M · **Category**: behavior
- **Target**: `D:/dev-projects/main/hermes-cloud-studio/linkedin/stealth.py`
- **Verify score**: 2/3 lentes

**Descricao**: Authwall dispara em 3-5 profiles sem scroll/hover/dwell. Skip-navigation direto a URL = flag. Adicionar trail organico: abrir feed, scroll lento, like 1-2 posts, search query, clicar resultado.

**Sketch**:
```
1) Antes de profile view: navegar /feed/, scroll com wheel events em rampa (3-12s, 30-60% page). 2) Para chegar em profile: ou via search bar + tecla a tecla (PATCH-010) ou via 'mutual connections' click. 3) Dentro do profile: dwell 8-25s, scroll progressivo, hover em sections. 4) Probabilidade 15% de like/follow para emular engagement-first. 5) Between actions: 4-12min gap com jitter lognormal.
```

**Test plan (lab)**: Lab account: 50 profile views via novo flow, esperar 0 authwall em 4h window. Logar tempo dwell por pagina (>8s p10). Comparar pageviews/session com baseline humano.

**Sources**: scrapfly.io authwall 3-5 · connectsafely.ai skip-navigation · heysid.com outreach safely · linkboost.co engagement-first · salesso.com

**Lentes**:
- OK (medium): Tecnica enderecca causa raiz descrita (skip-navigation direto sem trail organico dispara authwall em 3-5 profile views). Warm-up via /feed/ + scroll + engagement antes de profile view e padrao reconhecido em fingerprinting comportamental — LinkedIn rastreia session entropy: mouse trajectories, dwell, scroll velocity, referrer chain. Sketch logicamente coerente: (1) feed warm-up estabelece sessao aquecida, (2) navegacao via search/mutual reduz flag de URL direta, (3) dwell 8-25s + scroll progressivo emula leitura, (4) gap 4-12min lognormal evita burst. Falhas: (a) 15% like/follow em profile-alvo cria edge rastreavel no grafo social — deveria ser <5% e restrito ao feed; (b) tecla-a-tecla depende de PATCH-010 (timing humano 60-180ms); (c) dwell 8-25s curto, p50 humano real 15-45s; (d) test_plan inconsistente: 50 views/4h = 1/4.8min viola gap 4-12min do sketch; (e) wheel events precisam easing nao-linear, nao rampa; (f) falta tratar document.referrer chain e profiles 3rd+ degree onde authwall e mais agressivo independente de warm-up; (g) nao especifica recovery em authwall parcial. Abordagem direcionalmente correta, valid=true com caveats materiais.
- OK (high): Effort M realista. Patchright/Playwright suportam tudo nativamente — page.mouse.wheel, hover, query_selector, keyboard.type (PATCH-010). Infra ja existe em human.py: scroll_human, simulate_page_reading, move_mouse_human, click_human, simulate_pre_outreach. Patch reduz a: (1) extrair simulate_pre_outreach em micro warm-up por-profile (~30-60s feed scroll) em viewer.py; (2) adicionar hover_sections() iterando sel ['section.experience','section.education','section.about'] com move_mouse_human + dwell 2-5s; (3) flag probabilistico like/follow 15% via button[aria-label*='Like']/button[aria-label*='Follow'] click_human; (4) gap lognormal entre profiles: random.lognormvariate(mu=6.0, sigma=0.4) clamp 240-720s — 1 linha. Zero deps novas (math, random ja usados). Sem hack: tudo API publica Playwright. Risco baixo: warm-up feed ja provado em producao (simulate_pre_outreach existe e funciona). Test plan razoavel — 50 views/4h e auditavel via logs ja presentes em viewer.py. Caveats abaixo. Default valid=true porque implementacao reusa codigo testado, nao introduz dep instavel.
- FAIL (high): Patch falha em 4 frentes: (1) Target file errado — stealth.py eh launcher de browser (anti-detection JS patches, cookie seeding, proxy), nao behavioral signals. Behavioral helpers ja vivem em human.py: simulate_pre_outreach (feed warm-up com notifications/mynetwork/feed split), simulate_page_reading (dwell+scroll), scroll_human, type_human, move_mouse_human. viewer.py:268 ja chama simulate_pre_outreach antes de outreach e simulate_page_reading dentro de profile views (linhas 384, 529, 710). Patch reimplementa o que ja existe. (2) Overshoot risk: probabilidade 15% de like/follow nao-solicitado contamina grafo do lab account e converte perfil de viewer-only em engager, mudando baseline esperado pelo LinkedIn e podendo aumentar scrutiny ao inves de reduzir. Tambem cria efeito colateral real (like em post de terceiro). (3) Gaps 4-12min lognormal sao agressivos demais — limiter.py ja governa throughput, sobrepor gera caps duplicados; 50 profile views viram 3-10h, quebra capacity planning. (4) Test plan insuficiente: 50 views sem control group (baseline autenticado atual), sem N estatistico, sem medir efeitos colaterais (likes em posts errados, follows nao desejados, dwell timeout em paginas lentas), criterio "0 authwall em 4h" eh binario nao quantitativo. Sources sao blog posts SEO (scrapfly, heysid, linkboost) sem dados primarios. Risco concreto de quebrar flow estavel atual em stealth.py (comentarios fortes "do NOT pass user_agent/viewport/locale" — patch mexer nesse arquivo arrisca regressao em ERR_TOO_MANY_REDIRECTS ja resolvido). Recomendacao: rejeitar como esta. Se warm-up real precisa de reforco, target = human.py (estender simulate_pre_outreach com mais variancia) + viewer.py (garantir warm-up roda antes de TODO profile, nao so primeiro outreach), nao stealth.py. Remover like/follow probabilistico ou mover pra engager.py com flag explicita.

---

### PATCH-013 — window.chrome stub completo (runtime, app, csi, loadTimes)

- **Severity**: high · **Effort**: M · **Category**: fingerprint
- **Target**: `D:/dev-projects/main/hermes-cloud-studio/linkedin/stealth.py`
- **Verify score**: 2/3 lentes

**Descricao**: Stub atual viola invariante loadTimes/csi (Date.now() em cada call) e nao implementa runtime.connect/sendMessage com TypeError correto. Snapshot timestamps em navigationStart e replicar API surface real.

**Sketch**:
```
1) Snapshot t0=performance.timing.navigationStart no init. 2) loadTimes() retorna struct com requestTime/startLoadTime/commitLoadTime derivados de t0, congelados. 3) csi() retorna {startE, onloadT, pageT, tran} congelados. 4) runtime.connect(id) -> throw TypeError('Invalid extension id'). 5) Adicionar PlatformOs, PlatformArch, RequestUpdateCheckStatus enums. 6) chrome.app.isInstalled false, getDetails/getIsInstalled funcoes. 7) toString hardening.
```

**Test plan (lab)**: Chamar chrome.loadTimes() duas vezes -> mesmo objeto. chrome.runtime.connect('x') -> TypeError. Comparar Object.keys(chrome.runtime) com Chrome real.

**Sources**: code_gaps Patch 2

**Lentes**:
- FAIL (medium): Direcao correta mas sketch tem falhas tecnicas:

1. **runtime.connect TypeError errado**: Em Chrome real sem extensao instalada, `chrome.runtime.connect('id-invalido')` NAO lanca TypeError sincrono. Retorna um Port que dispara onDisconnect async com lastError "Could not establish connection. Receiving end does not exist." TypeError soh ocorre quando argumento eh tipo invalido (ex: connect({})). Detector como CreepJS/fp-collect testa exatamente isso — stub lancando TypeError vira RED FLAG, pior que stub atual. Sketch inverte a semantica.

2. **navigationStart no init_script**: `performance.timing.navigationStart` em add_init_script roda ANTES de qualquer navegacao real (document_start). Valor pode ser 0 ou timestamp do about:blank, nao da pagina destino. Resultado: requestTime/startLoadTime ficam congelados em valor errado relativo a pagina carregada. Correto: usar `performance.timeOrigin` OU snapshot dentro de listener DOMContentLoaded. Sketch nao trata isso.

3. **Scripts soh injetados no fallback Playwright** (linha 303 `if not use_patchright`). Patchright cuida do chrome.* nativamente. Patch eh dead code no caminho principal — severity high questionavel.

4. **chrome.csi() real retorna milissegundos inteiros e `tran` eh numero (codigo de transicao)**, nao string. Sketch lista `tran` sem especificar tipo — implementacao ingenua quebra teste de tipo.

5. **chrome.app.getDetails/getIsInstalled**: em Chrome moderno (>110) `chrome.app` foi removido para non-PWA pages. Adicionar pode ser FP positivo (deteccao "tem chrome.app onde nao devia"). Precisa checar version-gating.

6. **toString hardening** ja existe (script 11). Sketch nao explica como integra sem conflito.

Tecnica geral (snapshot congelado) eh valida, mas execucao proposta tem 2 bugs semanticos serios (TypeError + navigationStart) que pioram fingerprint em vez de melhorar.
- OK (high): Patch viavel. Implementacao puramente JS via context.add_init_script — Patchright/Playwright suportam nativamente, sem hack. Effort M realista: ~80-120 linhas JS dentro de _STEALTH_SCRIPTS, snapshot t0 no init, retornar objetos congelados (Object.freeze), throw TypeError em runtime.connect. Sem dependencias externas, sem CDP, sem patch binario. Risco baixo. Nota: stub atual so injeta quando NOT use_patchright (linha 303) — patch precisa rodar sempre, ou Patchright ja cobre window.chrome (verificar). Se Patchright ja stub-a chrome, patch pode conflitar — recomendado checar antes de sobrescrever (if window.chrome && window.chrome.loadTimes && nativo, skip). toString hardening ja existe (script 11) mas precisa registrar novas fns.
- OK (medium): RISK lens — PATCH-013 window.chrome stub completo.

STUB ATUAL (linhas 65-82) tem falhas reais detectaveis:
- loadTimes() retorna Date.now()/1000 a cada call → 2 chamadas = timestamps diferentes (Chrome real: congelados em navigationStart). Detector trivial: `const a=chrome.loadTimes(); const b=chrome.loadTimes(); a.requestTime===b.requestTime` → false = bot.
- csi() mesma falha (Date.now() volatil).
- runtime.connect/sendMessage = no-op silencioso. Chrome real sem extension valida: connect('invalid') → throw TypeError. Detector CreepJS/FpScanner usa isso.
- Faltam enums (PlatformOs, PlatformArch) e chrome.app.getDetails/getIsInstalled.

RISCO DE QUEBRAR FLUXOS LINKEDIN:
- Baixo. window.chrome.* nao e usado por codigo LinkedIn de produto — so por anti-bot detectors. Stub atual ja existe; patch substitui, nao remove.
- Risco real: throw TypeError em runtime.connect pode quebrar scripts terceiros (analytics, widgets) que chamam chrome.runtime.connect defensivamente. LinkedIn nao usa extension messaging em paginas publicas, mas extensoes do usuario podem (LinkedIn Sales Navigator extension etc.) — no contexto headless/cloud isso nao se aplica.

RISCO DE OVERSHOOT (stealth pior que original Chrome):
- Medio-alto se implementado mal. Pontos criticos:
  1) Snapshot t0 deve usar performance.timeOrigin ou performance.timing.navigationStart REAL da pagina, nao do init script. Se script roda em add_init_script (antes do navigate), timing.navigationStart ainda nao existe → t0=0 = fingerprint suspeito. Precisa lazy-init no primeiro call apos load.
  2) loadTimes congelado mas com requestTime < startLoadTime < commitLoadTime < finishLoadTime em ordem realista. Stub atual ja erra ordem; patch precisa modelar deltas reais (ex: requestTime=0, startLoadTime=requestTime+0.001, etc.). Valores zerados ou identicos = red flag.
  3) wasNpnNegotiated:true + npnNegotiatedProtocol:"unknown" e inconsistente — Chrome moderno usa ALPN (h2/http1.1), nao NPN. Patch deve atualizar pra wasAlpnNegotiated:true, alpnNegotiatedProtocol:"h2".
  4) toString hardening: se chrome.loadTimes.toString() nao retornar "function loadTimes() { [native code] }" exato, fingerprint quebra. Precisa Proxy + Function.prototype.toString override consistente com outros stubs do arquivo (verificar se ja existe pattern).
  5) Object.keys(chrome.runtime) ordem importa. Chrome real: id, getURL, getManifest, connect, sendMessage, onMessage, onConnect, ... — adicionar so connect/sendMessage deixa surface menor que real = detectavel.

TEST_PLAN COBRE PARCIALMENTE:
- Cobre: timestamps congelados (ok), TypeError em connect (ok), Object.keys diff vs Chrome real (ok).
- NAO cobre:
  a) Comparacao em pagina HTTPS pos-navigate (t0 valido).
  b) toString() output das funcoes stub.
  c) Ordem das chaves de chrome.runtime (Object.keys preserva ordem de insercao — patch precisa inserir na ordem certa).
  d) Regressao: rodar fluxo login LinkedIn end-to-end pos-patch pra confirmar zero quebra.
  e) Validar contra CreepJS/bot.sannysoft.com/pixelscan antes/depois pra medir score.

VEREDICTO: valid=true. Beneficio > risco SE implementado com cuidado (lazy t0, deltas realistas, ALPN nao NPN, toString hardening, ordem de chaves). Patch atual e detectavel; nao aplicar = continuar detectavel. Test_plan precisa expandir com itens (a)-(e) acima.

---

### PATCH-014 — Warm-up 14d + acceptance rate guard >70%

- **Severity**: high · **Effort**: M · **Category**: behavior
- **Target**: `D:/dev-projects/main/hermes-cloud-studio/linkedin/stealth.py`
- **Verify score**: 2/3 lentes

**Descricao**: Contas <60d ou <150 conn precisam warm-up 14 dias antes de qualquer outreach: 10-15 acoes/dia ramp +5/sem, 5-10 conn/dia para conhecidos, likes/comments organicos. Monitorar acceptance rate; <40% = pausar.

**Sketch**:
```
1) AccountState {created_at, total_connections, acceptance_rate_7d, status: warming|active|cooldown}. 2) Se age<60d OR conn<150: forcar plano warmup com ramps. 3) Tracker de invites enviadas + accepted via /mynetwork/invitation-manager/sent/. 4) Calcular rate_7d; se <40% -> status=cooldown 7 dias, zero outreach, so engagement. 5) Bloquear send_invite se status != active.
```

**Test plan (lab)**: Simular 30 dias: assert ramp respeitado. Forcar acceptance 30% -> assert cooldown automatico. Logs de daily caps.

**Sources**: blog.closelyhq.com warm-up · linkedinsider.blog warm-up · botdog.co rejection · hyperclapper.com restricted-react

**Lentes**:
- FAIL (medium): Patch direção correta (warm-up + acceptance guard são best practices documentadas para evitar restrição LinkedIn), mas implementation_sketch tem falhas técnicas relevantes que justificam valid=false:

1) Threshold inconsistente: descrição diz "acceptance rate guard >70%" no título, mas sketch usa <40% como gatilho de cooldown. Gap entre 40-70% fica indefinido — não há banda intermediária (ex: throttle). Especificação ambígua = bug garantido.

2) Scraping de /mynetwork/invitation-manager/sent/ é frágil e detectável: endpoint requer sessão autenticada, HTML muda frequentemente, e polling regular desse path é sinal forte de automação (LinkedIn monitora padrões de acesso a páginas de gestão). Não há fallback se DOM mudar nem rate-limit do próprio scrape.

3) Janela 7d para acceptance_rate é estatisticamente fraca no início do warm-up: com 5-10 invites/dia nos primeiros dias, amostra <50 — variance alta, falsos positivos de cooldown. Falta min_sample_size antes de avaliar rate.

4) Aceitações no LinkedIn têm lag (média 3-7 dias, cauda até 30d). Calcular rate_7d sobre invites enviadas nos últimos 7d subestima rate real — invites recentes ainda não tiveram tempo de aceitar. Correto: medir rate sobre invites enviadas em janela mais antiga (ex: enviadas entre d-14 e d-7).

5) AccountState não persiste pending_invites com timestamp — sem isso, recalcular rate após restart é impossível. Sketch omite storage layer.

6) "age<60d OR conn<150" — conn<150 pode ser conta antiga e estável de nicho; forçar warm-up perpétuo em contas legítimas de baixa rede gera falso positivo. Falta condição de saída do warming além das duas iniciais.

7) Não trata withdrawn invites (LinkedIn auto-retira após 6 meses) nem distingue accepted vs ignored vs declined no cálculo.

8) Ramp "+5/sem" sem teto definido — sketch não diz quando warming termina (apenas after 14d? after threshold conn?).

9) Bloquear send_invite por status é necessário mas insuficiente: também precisa bloquear messages, profile views em massa, e endorsements — todos contam para o limite de "ações" mencionado (10-15/dia).

Direção válida, mas sketch precisa de revisão antes de implementar.
- OK (high): Infra base ja existe: limiter.py tem warmup_state SQLite, ramps per-action (warmup_action_multiplier), cooldown.py 210 linhas, connector.py 713 linhas com send_invite. Patch reusa stack. Effort M realista: (1) AccountState dataclass + tabela SQLite +30 LOC trivial; (2) age<60d/conn<150 check no bootstrap +20 LOC; (3) scrape /mynetwork/invitation-manager/sent/ — Patchright/Playwright suporta nativo, mesma sessao autenticada ja usada por connector/engager, sem hack; (4) rate_7d calc via SQL window sobre invites_log +40 LOC; (5) gate em send_invite +5 LOC. Total ~150-250 LOC, 1-2 dias. Sem dependencias novas (sqlite3 + playwright ja no requirements). Risco baixo: unico ponto fragil e seletor DOM da pagina invitation-manager (LinkedIn muda layout), mitigavel com fallback graceful + log. Patchright e estavel, mesmo pattern ja usado em viewer.py/engager.py.
- OK (medium): RISK lens. Target file errado mas patch é VÁLIDO — riscos gerenciáveis < beneficio (proteção anti-ban).

QUEBRA FLUXOS EXISTENTES?
- Sistema JÁ tem warmup robusto em `limiter.py` (warmup_state table, LURKING_PCT, warmup_action_multiplier, lurking_days). Não em `stealth.py` (esse arquivo é só browser anti-detection — patch aponta target errado).
- AccountState proposto duplica warmup_state existente. Risco: conflito de schema/lógica dupla se implementar sem consolidar.
- Bloquear send_invite por status != active vai PARAR contas em cooldown — comportamento desejado mas precisa coordenar com connector.py/engager.py que chamam send_invite. Se hoje há campanhas rodando sem essa gate, vão quebrar com "status=cooldown" silencioso.
- Tracker via scraping /mynetwork/invitation-manager/sent/ adiciona NOVA superfície de scraping → mais navegação automatizada → mais risco de detecção (LinkedIn monitora acesso a esse endpoint).

DETECÇÃO PIOR (overshoot)?
- Reduzir volume = SEMPRE melhor pra stealth, não pior. 10-15 ações/dia em conta nova é conservador e alinhado com docs LinkedIn (Sales Navigator novos: <20/dia).
- ÚNICO risco: polling do invitation-manager. Se rodar muito (ex: a cada hora) vira padrão bot. Mitigar: poll 1x/dia, dentro de sessão humana normal.
- 70% acceptance no titulo vs 40% no description = inconsistência. 70% é alto demais (média realista 30-50%); 40% threshold é razoável. Confirmar 40% como real.

TEST PLAN COBRE RISCOS?
- "Simular 30 dias" + "forçar acceptance 30%" cobre lógica de ramp/cooldown — OK.
- NÃO cobre: (a) integração com warmup_state existente, (b) impacto em campanhas live quando status muda pra cooldown, (c) overhead de polling no invitation-manager, (d) o que acontece com invites já enfileiradas quando entra cooldown.
- Falta: teste de regressão com fluxo connector.send_invite atual.

VEREDICTO: valid=true porém com caveats fortes. Beneficio (anti-ban, acceptance rate é sinal #1 que LI usa pra restrict accounts) > risco. Mas implementação precisa: (1) corrigir target pra limiter.py (não stealth.py), (2) extender warmup_state existente em vez de criar AccountState paralelo, (3) reconciliar 70% vs 40% threshold, (4) limitar polling invitation-manager a 1x/dia.

---

## Patches rejeitados (< 2 lentes valid)

- **PATCH-001** — Coerencia UA + platform + userAgentData + sec-ch-ua + oscpu (score 1/3)
  - FAIL: Diagnostico correto (stealth.py linha 109 hardcode 'Win32', sem userAgentData/sec-ch-ua/oscpu/maxTouchPoints — confirmado por leitura do arquivo). Direcao da tecnica (OSProfile per-account coerente) e valida. Mas implementation_sketch tem falhas logicas concretas:\n\n1. **oscpu em Chrome = nova mentira**. navigator.oscpu so existe em Firefox. Definir em UA Chrome cria divergencia que getHasLiedOs detecta. Deve ser condicional a familia do UA.\n\n2. **sec-ch-ua via set_extra_http_headers e incorreto**. Chromium envia Sec-CH-UA nativamente baseado no UA real. Injetar headers extras causa duplicacao/conflito visivel no servidor. O caminho correto e CDP `Network.setUserAgentOverride` com parametro `userAgentMetadata` — seta JS userAgentData E headers de saida de forma coerente em uma so chamada. Sketch nao menciona CDP.\n\n3. **userAgentData incompleto**. Sketch so override `getHighEntropyValues` (async). Faltam getters low-entropy sincronos: `navigator.userAgentData.brands`, `.mobile`, `.platform`. Detectores leem ambos.\n\n4. **navigator.vendor ausente**. Cross-check classico junto com platform ('Google Inc.' Chrome vs '' Firefox). Sketch omite.\n\n5. **WebGL renderer hardcoded (linhas 132-140 NVIDIA D3D11) nao acoplado ao OSProfile**. Se OSProfile seleciona macOS/Linux, WebGL vaza Windows/D3D11 — quebra exatamente a coerencia que o patch promete entregar. Escopo do patch deveria incluir acoplamento, ou explicitar dependencia de outro patch.\n\n6. **UA propriamente dito**: sketch fala de appVersion/platform mas nao especifica onde navigator.userAgent e o header HTTP UA sao setados de forma alinhada. Override JS-only deixa header HTTP nativo mismatch.\n\nTecnica resolve parcialmente a deteccao descrita, mas com esses gaps o patch ainda gera 'lied' badges em creepjs (oscpu lie em Chrome, sec-ch-ua duplicado, WebGL OS mismatch). Test_plan via creepjs vai expor isso — porem o sketch precisa ser corrigido antes de implementar.
  - FAIL: Risco > beneficio no estado atual.

PROBLEMA NA PREMISSA: Patch alega "Patch 5 hardcode Win32 enquanto UA pode ser Mac/Linux". Falso no codigo real:
1. `_STEALTH_SCRIPTS` (incluindo Patch 5 Win32) so injeta quando `not use_patchright` (linha 303). Caminho default e Patchright -> NENHUM patch JS roda, navigator.platform vem nativo do Chrome real.
2. `_random_user_agent()` esta DEFINIDA mas NUNCA chamada. launch_kwargs nao seta `user_agent` (comentario explicito linhas 264-265: "Do NOT pass user_agent"). UA = Chrome nativo, coerente com platform/oscpu/sec-ch-ua que o proprio Chrome emite.
3. Logo: na VM Linux rodando Chrome stable + Patchright, UA=Linux + platform=Linux + sec-ch-ua-platform=Linux ja batem nativamente. ZERO divergencia para getHasLiedOs flagrar.

RISCOS DE APLICAR:
- Overshoot stealth classico: override de navigator.userAgentData.getHighEntropyValues e proxy de Promise sao detectaveis via Function.prototype.toString, Proxy traps, e checagem se metodo e native code. Patchright explicitamente evita esses overrides porque eles VIRAM o sinal de deteccao (castle.io e creepjs detectam getter overrides em navigator.*).
- Patchright README: "do NOT pass custom headers or user_agent" — patch propoe set_extra_http_headers com sec-ch-ua, violando guideline e arriscando ERR_TOO_MANY_REDIRECTS no LinkedIn (problema ja documentado nas linhas 202-204).
- Fluxo cookie seeding e redirect-loop avoidance (linhas 308-375) foram tunados para Chrome nativo. Mudar UA/platform/locale via launch_persistent_context muda Accept-Language e pode invalidar li_at vinculado a fingerprint anterior do perfil persistente -> challenge/checkpoint.
- Determinismo por account_id e bom, mas trocar OS profile entre runs do MESMO account (se seed mudar) gera fingerprint instability -> LinkedIn marca como suspicious device change.

TEST PLAN INSUFICIENTE:
- Testa creepjs/browserleaks mas NAO testa LinkedIn end-to-end (login, feed, search, connect). Risco real e checkpoint/restriction, nao "lied badge".
- Nao mede regressao vs baseline atual (Patchright nativo). Falta A/B: N accounts com patch vs N sem.
- Nao valida estabilidade de fingerprint entre sessoes do mesmo account (cookie persistence + seed determinista).
- Nao cobre interacao com proxy egress (sec-ch-ua-platform forcado Mac mas proxy IP geo Brasil + timezone America/Cuiaba = nova incoerencia).

VEREDICTO: Patch resolve problema que nao existe no caminho Patchright (caminho default). So faria sentido no fallback Playwright vanilla — e mesmo la, melhor remover Patch 5 hardcode do que adicionar 6 superficies novas de override. Recomendacao: rejeitar PATCH-001; abrir patch menor "remove Patch 5 hardcode Win32 do fallback Playwright, deixar platform nativa" com 5% do esforco e zero risco de overshoot.
- **PATCH-002** — JA3/JA4 TLS fingerprint matching Chrome real (score 0/3)
  - FAIL: Patch tem premissa parcialmente valida mas implementation_sketch contem falhas tecnicas e contradicoes serias.

PROBLEMAS DE CORRECTNESS:

1) **stealth.py JA SUSA channel='chrome'** (linha 272) com fallback executable_path para Chrome real (linhas 226-234). A premissa do patch ("Patchright/Playwright Chromium ainda usa stack TLS do Chromium bundle") esta DESATUALIZADA — o codigo atual ja prioriza Chrome stable real. Quando Chrome stable e usado via channel='chrome', a stack TLS E a do Chrome stable, nao do Chromium. Severity "critical" injustificado.

2) **Camoufox e Firefox, nao Chrome** — sugerir "Camoufox (Firefox JA4 nativo)" como alternativa quebra o objetivo: LinkedIn baseline esperado e Chrome (UA spoof, window.chrome, WebGL ANGLE D3D11 ja injetados). Trocar para Firefox geraria MISMATCH entre JA4 (Firefox) e User-Agent/JS fingerprint (Chrome) → deteccao GARANTIDA. Falha logica grave.

3) **nodriver lanca Chrome stable real igual ao que ja esta sendo feito** via channel='chrome' + launch_persistent_context. Beneficio marginal/duplicado. nodriver usa CDP igual Playwright; nao da JA4 melhor que Chrome real ja em uso.

4) **--enable-features=PostQuantumKyber** — flag name esta possivelmente errada. Chrome 124+ usa `--enable-features=PostQuantumKyber` foi nome experimental; em Chrome 131 atual o X25519Kyber768Draft00 esta DEFAULT ENABLED, nao precisa flag. Em Chrome 135+ migrou para MLKEM (X25519MLKEM768) tambem default. Forcar feature flag manual pode atrapalhar (override defaults). Patch afirma "obrigatorio em 2026" sem fonte concreta sobre LinkedIn especificamente checar PQ KEX para bloqueio.

5) **curl_cffi impersonate='chrome131'** — sugestao razoavel PARA httpx fallback, mas patch nao identifica onde httpx e usado no stealth.py. stealth.py e Playwright-only; nao ha HTTP fallback aqui. Sketch mistura escopo.

6) **Validacao via tls.peet.ws** — tecnica valida MAS o sketch nao reconhece que TLS fingerprint via Playwright+channel='chrome' ja entrega JA4 do Chrome stable real (mesmo binario). Comparar com "Chrome 131 em maquina fisica" via peet.ws vai mostrar match identico se mesmo Chrome version — o "problema" descrito ja esta resolvido.

7) **Severity:critical sem evidencia** que LinkedIn bloqueia por JA4 antes do HTTP. Documentacao Scrapfly e generica sobre anti-bot; bloqueio LinkedIn observado historicamente e behavioral + cookies + IP, nao JA4 pre-HTTP em conta autenticada.

8) Trocar engine ("Camoufox OU nodriver") quebraria toda integracao Patchright + injeção de cookies + persistent context + WebRTC patches + connector.py/engager.py downstream. Effort:L subestimado — seria refactor massivo, alto risco regressao.

CONCLUSAO: Patch parte de premissa ja-resolvida no codigo, propõe alternativas com mismatch logico (Camoufox=Firefox), confunde feature flag PQ, e mistura escopo HTTP fallback nao-existente. valid=false.
  - FAIL: Lente FEASIBILITY: patch reprovado. Codigo atual ja faz parte do prometido (channel='chrome' via _detect_chrome_path + standard_paths em stealth.py:268-274), entao 50% da implementation_sketch e redundante. Resto tem risco alto e effort L subestimado:

1) JA3/JA4 do Chromium-launched-by-Playwright NAO e igual ao Chrome stable mesmo com channel='chrome' — Playwright injeta CDP que altera handshake ordering e a stack de rede e a mesma do binario, mas extensions/ALPN podem divergir por flags. Validar "JA4 hash deve ser identico" e teste falhavel: ja4 inclui ordem de cipher suites que muda entre minor versions Chrome (131 vs 132). Baseline fica obsoleto em 4 semanas.

2) Camoufox: e Firefox fork, trocar engine quebra TODO o codigo Patchright-specific (connector.py 30K, engager.py 34K, viewer.py 41K usam seletores/timing Chromium). Refactor = effort XL nao L.

3) nodriver: Python lib (ultrafunkamsterdam/nodriver) e DevTools-only, sem API Playwright. Mesma quebra de connector/engager. Lib instavel, breaking changes frequentes, sem suporte persistent_context maduro.

4) --enable-features=PostQuantumKyber: ja e default em Chrome 124+ stable. Flag e no-op redundante. Patch sugere como se fosse fix, nao e.

5) curl_cffi impersonate='chrome131': lib funciona mas (a) HTTP fallback no codigo nao foi mostrado existir relevante para LinkedIn login flow (tudo via browser context cookies), (b) chrome131 ja desatualizado (Chrome 141+ stable em 2026-06), impersonate strings tem que rastrear releases — manutencao continua.

6) tls.peet.ws: servico third-party, pode estar down/rate-limited. ja4db.com requer auth. Test plan depende de infra externa instavel.

7) Effort L (medio) irrealista. Avaliar+trocar engine + revalidar 100K+ linhas de fluxo LinkedIn + manter baseline JA4 atualizado = effort XL com risco de regredir features estaveis ja em producao.

Recomendacao: manter Patchright+channel='chrome' atual (ja implementado stealth.py:268-274), adicionar APENAS validacao opcional via curl_cffi para requests fora-do-browser SE existirem. Rejeitar troca de engine.

Arquivo relevante: D:\dev-projects\main\hermes-cloud-studio\linkedin\stealth.py (linhas 193-283).
  - FAIL: RISK lens reprova. Codigo ATUAL ja resolve 80% do patch (channel='chrome' + executable_path fallback + ignore --enable-automation + Patchright). Patch propoe overshoot que QUEBRA fluxos rodando.

QUEBRAS concretas:
1. "Trocar engine para Camoufox/nodriver" — descarta TODA arquitetura atual: stealth.py inteiro, connector.py (30K), viewer.py (41K), engager.py (34K). Camoufox=Firefox API diferente, nodriver=CDP raw sem Playwright. Custo: rewrite multi-modulo. Effort real != L, e XXL.
2. "Habilitar --enable-features=PostQuantumKyber" em Chrome 124+ — usuario roda Chrome stable (versoes UA listadas 135-137 ja tem PQ Kyber ON por DEFAULT desde Chrome 124). Forcar flag manualmente vira fingerprint anomalo (flag aparece em chrome://version) e pode CONFLITAR com flag default → JA4 pior, nao melhor.
3. "curl_cffi impersonate='chrome131'" — stealth.py NAO faz HTTP fallback. httpx nao existe nesse arquivo. Patch mistura escopo (talvez confunde com outro modulo). Aplicar aqui = no-op ou import morto.
4. Cookie seeding atual (linhas 308-375) tem logica anti-redirect-loop delicada (DURABLE_COOKIES, env LI_AT override). Trocar engine perde isso → regressao garantida ERR_TOO_MANY_REDIRECTS.

DETECCAO PIOR (overshoot):
- Camoufox tem JA4 Firefox, mas UA/navigator atuais sao Chrome (linha 442-450, _random_user_agent Chrome). Inconsistencia UA Chrome + JA4 Firefox = sinal forte de anti-detect tool.
- nodriver sem persistent_context perde user_data_dir per-conta → LinkedIn ve "novo device" toda sessao → challenge SMS.
- Flag manual PostQuantumKyber em build que ja tem on-by-default = duplo handshake config, sniffavel.

TEST PLAN INSUFICIENTE:
- tls.peet.ws valida JA4 isolado, NAO valida interacao com cookie state + persistent profile + LinkedIn challenges reais.
- "Sem usar conta LinkedIn ainda" — nao mede o que importa: taxa challenge/checkpoint em conta real. JA4 perfeito + comportamento bot ainda = ban.
- Falta A/B: baseline (codigo atual) vs patch em N contas warm pareadas durante 7d.

RISCO > BENEFICIO. Patch atual ja cobre ganho marginal de JA4 via channel='chrome' real. Resto e teatro de stealth com custo de rewrite.
- **PATCH-006** — Bezier mouse + minimum-jerk velocity + tremor (score 1/3)
  - FAIL: Tecnica direcionalmente correta (Bezier + minimum-jerk + tremor SAO estado-da-arte vs teleporte CDP). Mas implementation_sketch tem falhas logicas:

1) **Monkey-patch Locator.click nao funciona**: Locator e proxy gerado em runtime no Playwright Python (sync_api/async_api). Patching Locator.click globalmente quebra .click(force=True), .click(position=...), .click(modifiers=...), e Locators de iframe. Tambem nao intercepta page.click(), page.get_by_role().click(), nem fluxos que dependem do dispatchEvent interno do Playwright. Solucao correta: wrapper explicito human_click(locator) chamado pelos call-sites, nao monkey-patch.

2) **mouse.down/up sem context CDP fica detectavel mesmo assim**: Playwright mouse.move/down/up emitem eventos via CDP Input.dispatchMouseEvent que carregam flag isTrusted=false em alguns vetores e nao geram pointerrawupdate nem coalesced events. LinkedIn/Arkose checa PointerEvent.getCoalescedEvents() e movementX/Y consistency. Bezier+jerk no Playwright API ainda produz trajetoria sintetica detectavel. Patch nao endereca isso — precisa CDP Input.dispatchMouseEvent com timestamp jitter OU rodar via real input injection (Patchright ja melhora isso parcialmente).

3) **Cursor inicial desconhecido**: move_to(target) precisa de origem. Playwright nao expoe posicao atual do cursor — patch precisa rastrear estado em modulo (race conditions em codigo async).

4) **Minimum-jerk formula 10t^3-15t^4+6t^5 esta correta** (5th order polynomial, position profile), mas e profile de POSICAO escalar, nao de velocidade. Texto diz "minimum-jerk velocity" — confuso. Aplicar como time-warp em parametro Bezier funciona, so a descricao esta imprecisa.

5) **Tremor 1-3px gaussiano por frame e excessivo** em alta frequencia — humanos tem tremor ~0.1-0.5px @ 60Hz, picos maiores apenas em micro-corrections. 1-3px constante gera trajetoria mais ruidosa que humano, pode piorar score.

6) **Test plan fraco**: Shannon entropy de trajetoria nao e o que Arkose mede — eles usam features especificas (jerk distribution, dwell time, click-coordinate offset from element center, pointer event timing variance). fingerprint.com/bot-detection nao testa mouse dynamics.

7) **Falta o vetor real**: LinkedIn/Arkose pega bots principalmente por (a) navigator.webdriver, (b) CDP runtime detection, (c) ausencia de pointerrawupdate, (d) click coordinates centralizadas demais. Patch atual ja roda Patchright que mitiga (a)(b). Sem evidencia que mouse dynamics e o gargalo atual — pode ser premature optimization.

8) **severity=critical injustificado** sem telemetria mostrando que mouse e o vetor de deteccao em uso. Fluxo atual provavelmente nem chega a Arkose challenge.

Tecnica e valida mas sketch tem bugs (monkey-patch), parametros errados (tremor amplitude), test plan invalido (entropy), e prioridade questionavel (critical?).
  - FAIL: PATCH-006 deve ser rejeitado. Riscos > beneficios.

TARGET FILE ERRADO. Patch aponta D:/dev-projects/main/hermes-cloud-studio/linkedin/stealth.py — esse arquivo trata fingerprint/TLS/cookies, NAO mouse. Codigo de mouse humano ja existe em linkedin/human.py com: cubic Bezier (_bezier_point, _generate_bezier_path), control points aleatorios, tremor gaussian (sigma 1.2), overshoot 12% chance, perfil Fitts's Law (bell sin curve), click_human com gaussian offset + pre-click micro-pause. Patch reescreveria do zero algo ja implementado e em producao.

DUPLICACAO / CONFLITO. Se o sketch criar human_mouse.py novo + monkey-patch Locator.click, fica conflitando com click_human existente usado por connector.py/engager.py/viewer.py. Monkey-patch global em Locator.click quebra todos os .click() do codebase — inclusive nav clicks em pre-outreach (human.py linhas 301, 333, 363) que dependem do click sincrono atual. Quebra fluxo de checkpoint detection e pre-outreach.

EFEITO COLATERAL TIMING. Minimum-jerk 10t^3-15t^4+6t^5 + N pontos + 100-400ms hover + 50-150ms down/up adiciona ~600-1500ms por click. Engagement com lista grande de pessoas multiplica latencia. Rate-limiter em limiter.py / cooldown.py nao foi reavaliado contra novo timing.

OVERSHOOT STEALTH PIORA DETECCAO. Overshoot fixo em todo click vira PATTERN — bot detection moderno (Arkose/PerimeterX) faz frequency analysis: 100% overshoot rate eh tao suspeito quanto 0%. human.py atual usa 12% probabilistico, o que eh correto. Patch nao especifica taxa, sketch sugere overshoot em todo click ("antes do click: 100-400ms hover overshoot").

TELEPORT CLAIM INCORRETO. Premissa "Playwright .click() teleporta o cursor" eh falsa para este codebase — todos os fluxos criticos ja chamam click_human(), nao raw .click(). Auditoria do connector.py/engager.py confirmaria isso (nao feita pelo proposer).

TEST PLAN INSUFICIENTE. (a) "Shannon entropy > threshold humano" — threshold nao definido, sem baseline. (b) "Comparar com gravacao real do operador" — sem amostra, sem metrica de distancia (DTW? Frechet?). (c) fingerprint.com/bot-detection nao testa Arkose nem LinkedIn telemetria especifica. (d) Sem teste A/B contra producao para medir checkpoint rate antes/depois. (e) Sem teste de regressao do pre-outreach + nav clicks que dependem de timing sincrono. (f) Sem teste do monkey-patch nao quebrar locator.click(timeout=...) e outras opcoes.

RECOMENDACAO. Se quiser melhorar, fazer patch MENOR em human.py: (1) substituir bell sin curve por minimum-jerk no _fitts_delays (substituicao 1:1, baixo risco); (2) adicionar variancia no overshoot rate (manter probabilistico); (3) NAO monkey-patch global; manter API click_human explicita. Reescrever target_file de stealth.py para human.py, severidade M nao critical, effort S.
- **PATCH-010** — Typing humano: dwell 40-120ms, flight 80-400ms, digramas (score 1/3)
  - FAIL: Avaliação técnica do PATCH-010 sob lente CORRECTNESS:

PROBLEMA REAL? Sim. Playwright `.fill()` usa DOM `input` event direto, não dispara keydown/keypress/keyup nem respeita timing humano. Detectores anti-bot (PerimeterX, DataDome, LinkedIn próprio) monitoram exatamente isso: ausência de KeyboardEvent sequence, dwell time uniforme, ausência de variância log-normal. Premissa correta.

TÉCNICA RESOLVE? Parcialmente, mas com lacunas:

1. `keyboard.down(char)` + `keyboard.up(char)` — Playwright API correta é `page.keyboard.down(key)` onde `key` deve ser nome de tecla (ex: "a", "Shift+A"), não char arbitrário. Para chars uppercase/símbolos precisa modifier handling (Shift). Sketch ignora isso — vai quebrar em "Olá, mundo!" (acento, vírgula, !).

2. `sleep gauss(70,25)ms` para dwell — gaussiana é aproximação ok mas literatura (arxiv 2410.18233 citado, Killourhy-Maxion) mostra dwell tem distribuição log-normal, não normal. Patch menciona log-normal no test_plan mas implementa gauss. Inconsistência.

3. Flight time 80-400ms ponderado por digrama — conceito correto, mas tabela "Dvorak/Pydoll" não existe como banco público auditável. Pydoll tem heurística básica, não tabela empírica robusta. Sem fonte real da tabela, vira hand-waving.

4. Typo 2% + backspace + correção — bom sinal humano, mas detectores avançados também correlacionam typo rate com WPM e contexto (typo em palavra comum vs rara). Implementação ingênua pode criar pattern artificial detectável.

5. FALHA CRÍTICA OMITIDA: mouse movement, scroll, focus events, viewport. Typing humano isolado não derrota fingerprinting moderno — sinal composto. Patch escopo-restrito ok, mas claim "resolve detecção" é forte demais.

6. Layout do teclado: digrama "th" rápido assume QWERTY EN. Usuário escreve PT-BR (LinkedIn BR). Digramas PT são diferentes (nh, lh, ção). Tabela precisa ser PT-BR ou vira tell.

7. Test plan com KS test contra operador real — bom, mas N de amostras não especificado. KS test com n<30 é fraco.

CONCLUSÃO: Direção correta, execução com bugs (gauss vs log-normal, keyboard.down semantics, digramas EN vs PT, modifier keys). Não é production-ready como descrito. valid=false por dúvida técnica legítima conforme instrução.
  - FAIL: PATCH-010 invalido por 4 motivos:

1. ARQUIVO ERRADO: target_file=stealth.py, mas stealth.py so cuida de launch+JS patches+cookies. Typing humano JA EXISTE em linkedin/human.py:129 (type_human) com bigramas (_FAST_BIGRAMS/_SLOW_BIGRAMS), gauss(120,35), pausas em pontuacao, thinking pauses 3%. Aplicar em stealth.py duplica codigo e quebra separacao de responsabilidades.

2. DUPLICACAO/CONFLITO: human.py ja implementa ~70% do sketch (digramas, jitter gaussiano, micropausas). Patch nao referencia human.py existente. Risco alto de duas implementacoes divergentes sendo chamadas em pontos diferentes (engager vs viewer).

3. SKETCH PIOR QUE EXISTENTE em pontos chave:
   - sketch usa keyboard.down/up manual: introduz risco de stuck keys em chars com shift (maiusculas, !@#) e chars compostos (acentos PT-BR a/o/c). human.py usa page.keyboard.type(char) que ja emite keydown+keypress+keyup corretamente via CDP.
   - 2% typo+backspace: em campos LinkedIn com autocomplete/mention (@nome, #tag) backspace dispara dropdown reopens e pode submeter texto errado. Em search box dispara queries fantasma. Nao ha guard por contexto.
   - dwell 40-120ms proposto e MAIS RAPIDO que human.py atual (gauss 120,35 ~ 85-155ms). Acelerar = piorar fingerprint humano, nao melhorar.

4. TEST PLAN INSUFICIENTE: 
   - So mede dwell/flight contra KS test em lab. Nao testa: (a) compatibilidade com campos React-controlled do LinkedIn (mensagem, comentario, search) que reagem a InputEvent vs KeyboardEvent diferente; (b) acentuacao PT-BR (a, c, o) que requer dead keys; (c) interacao com autocomplete/@mention; (d) impacto em rate de bloqueio real (precisa A/B em conta sacrificial).
   - Nao define rollback se LinkedIn comecar a rejeitar mensagens.

RISCO > BENEFICIO: severity=high e effort=S enganosos. Mudanca toca caminho critico de envio de mensagem/comentario/connect note. Falha silenciosa (texto truncado, typo nao corrigido em campo enviado, mention errada) e pior que detecao marginal. Beneficio incremental zero — human.py ja cobre vetor principal.

RECOMENDACAO: rejeitar como esta. Reabrir como PATCH-010b mirando human.py com: (a) auditoria do type_human atual vs banco empirico, (b) ajustar constantes gauss se KS test mostrar gap, (c) typos so em textareas longos (>50 chars) com guard contra @/#, (d) zero refator de keyboard.type para down/up.
- **PATCH-011** — Canvas/Audio fingerprint noise per-account estavel (score 1/3)
  - FAIL: Tecnica geral (noise seeded por account) eh correta e enderecca o vetor descrito, mas implementation_sketch tem falhas logicas concretas: (1) descricao afirma "patch atual nao toca canvas" — falso, ja existe override em toDataURL linhas 145-160 (com Math.random nao-seeded). Sketch precisa SUBSTITUIR, nao adicionar, senao dupla aplicacao. (2) Override simultaneo de getImageData + toDataURL causa dupla aplicacao de noise quando pagina chama getImageData antes de toDataURL → hash NAO estavel entre runs (quebra o requisito central do patch). (3) Patch atual muta canvas real via putImageData (linha 156) — sketch repete o erro; correto eh clonar off-screen. (4) Audio: cobre apenas OfflineAudioContext.startRendering, omite AudioBuffer.getChannelData e AnalyserNode.getFloatFrequencyData que FingerprintJS/CreepJS tambem hashemam. (5) Sketch nao especifica como account_id chega ao JS (parametro de add_init_script? localStorage frageil?) — risco de implementacao incorreta. (6) toString protection do patch atual (linhas 177-188) reassign Function.prototype.toString — detectaveis via Function.prototype.toString.toString(); precisa Proxy. (7) Nao endereca correlacao com hardwareConcurrency=8/deviceMemory=8 hardcoded (linhas 113-114) — 1000 accounts com mesmos HC/DM + canvas distinto ainda clusterizam.
  - FAIL: RISCO > BENEFICIO. Patch tem 3 problemas serios:

1) **CONFLITO com codigo existente (linha 144-160)**: stealth.py JA tem canvas noise via `toDataURL` override usando `Math.random()` instavel. Patch novo precisa REMOVER o existente, nao adicionar — senao dupla mutacao. Sketch nao menciona migration. Pode quebrar fluxos atuais que dependem do hash atual ja "treinado" no LinkedIn (account com hash X vista por 30 dias, de repente hash Y -> trigger anomaly score).

2) **Determinismo cross-run e armadilha**: sketch quer "mesmo seed -> mesmo hash sempre". Mas LinkedIn coleta canvas em MULTIPLAS chamadas por sessao (login, feed, perfil, busca). Se override aplica noise no MESMO pixel toda chamada -> hash estavel mas DISTINTO do hash "natural" do hardware real do Cloud Run/VM. Pior: se accounts diferentes rodam no MESMO container Cloud Run, GPU/CPU subjacente identico -> canvas natural identico, e o seed-per-account vira o UNICO discriminante. LinkedIn ja sabe que canvas "deveria" variar com hardware; ver N accounts com hardwareConcurrency/deviceMemory/UA identicos mas canvas hash sempre distinto = sinal de farm.

3) **AudioContext OfflineRender override e RED FLAG**: castle.io e creepjs detectam override de `startRendering` (timing anomaly, prototype chain check, async return inspection). Amplitude 1e-7 em buffer Float32 pode cair abaixo do epsilon e nao mudar hash, OU mudar de forma detectavel (FFT bins zerados). Sketch nao especifica QUAL ponto do pipeline (pre/pos render). Overshoot classico.

4) **test_plan insuficiente**:
   - Testa apenas browserleaks + creepjs (detectores publicos, FRACOS vs LinkedIn proprietary).
   - NAO testa: (a) consistencia do hash apos N navegacoes na mesma sessao LinkedIn real, (b) que toString do override sobrevive ao Proxy trap do castle.io, (c) que `getImageData` override nao quebra LinkedIn upload de foto/avatar editor (eles usam canvas real), (d) A/B com account controle sem patch por 7 dias medindo challenge rate.
   - Sem rollback plan se challenge rate subir.

**Recomendacao**: REJEITAR como esta. Se for prosseguir, exigir:
- Remover override antigo (linha 144-160) primeiro
- Skip audio override (risco > beneficio, LinkedIn nao pesa audio tao alto quanto castle.io sugere)
- Apenas canvas com seed-per-account + GPU-derived salt (nao so account_id) pra evitar "N accounts mesma GPU virtual"
- Canary em 2 accounts low-value por 14 dias antes rollout
- Whitelist de canvas elements (skip canvas com width/height tipico de avatar editor LinkedIn)
- **PATCH-012** — navigator.plugins/mimeTypes coerente com Chrome moderno (score 1/3)
  - FAIL: Direção geral correta (remover Native Client, usar PluginArray/Plugin/MimeType reais com prototypes nativos), mas o implementation_sketch tem erro factual e omissões técnicas que comprometem correctness:

1. CONTAGEM ERRADA DE PLUGINS: sketch afirma "3 entradas estaticas que Chrome 131 retorna" (PDF Viewer, Chrome PDF Viewer, Chromium PDF Viewer). Chrome moderno (109+) retorna 5 plugins hardcoded e idênticos: "PDF Viewer", "Chrome PDF Viewer", "Chromium PDF Viewer", "Microsoft Edge PDF Viewer", "WebKit built-in PDF". Implementar apenas 3 produz mismatch detectável vs Chrome real (browserleaks/CreepJS comparam exatamente essa lista). Test plan ("matching Chrome 131 real") falharia.

2. PROXY sobre PluginArray.prototype NÃO ajusta instanceof por si só: `arr instanceof PluginArray` só vira true se o prototype chain incluir PluginArray.prototype. Sketch precisa especificar `Object.setPrototypeOf(arr, PluginArray.prototype)` OU Proxy com `getPrototypeOf` trap retornando PluginArray.prototype. Como está, "construir via Proxy sobre prototype" é ambíguo e implementador pode produzir Array comum com Proxy de getter — instanceof continuaria falso.

3. PLUGIN OBJECTS: sketch diz "cada plugin instanceof Plugin === true" mas não explica como instanciar Plugin (constructor é [[illegal constructor]] — não pode `new Plugin()`). Solução real: criar `Object.create(Plugin.prototype)` e definir name/filename/description/length via defineProperty + indexes numéricos pros MimeTypes embutidos. Sketch omite.

4. MIMETYPE BINDING: real Chrome tem cada Plugin com mimeTypes acessíveis por índice (`plugin[0]` retorna MimeType, `plugin['application/pdf']` idem) e cada MimeType.enabledPlugin aponta de volta. Sketch menciona apenas `[Symbol.iterator]` — insuficiente; precisa de cross-references bidirecionais + indexers numéricos/nominais. Sem isso, fingerprint inconsistente.

5. ESCOPO REAL DO PATCH no arquivo: bloco _STEALTH_SCRIPTS só é injetado quando `not use_patchright` (linha 303). Patchright trata plugins nativamente. Patch é relevante apenas em fallback Playwright. Severity "high" só se justifica nesse caminho — não foi qualificado.

6. NavigatorPlugins.refresh() existe na lista atual e deve ser preservado (sketch não menciona).

Conclusão: aprovar exige reescrever sketch com contagem correta (5 plugins), receita explícita de instanceof (setPrototypeOf), construção via Object.create(Plugin.prototype), cross-ref MimeType↔Plugin com indexers nomeados/numéricos, e condicionar relevância ao caminho não-Patchright.
  - FAIL: PATCH-012 mira `_STEALTH_SCRIPTS[3]` em stealth.py:85-100. Riscos analisados:

ESCOPO REAL: Patches JS so injetam quando use_patchright=False (linha 303). Patchright eh path padrao/recomendado. Patch so afeta fallback Playwright vanilla — baixo blast radius em prod.

RISCOS DE QUEBRAR LINKEDIN:
1. LinkedIn nao checa navigator.plugins para login/feed/messaging core flows. Fingerprint passivo, nao funcional. Quebra de fluxo: improvavel.
2. Construir PluginArray real via Proxy sobre window.PluginArray.prototype tem risco de TypeError se Proxy mal-formado — pode lancar erro em qualquer pagina que toque navigator.plugins. Bots de deteccao (FingerprintJS, PerimeterX) chamam isso — erro = sinal red flag pior que array fake.
3. `instanceof Plugin === true` exige spoof do prototype chain. Se errado, deteccao fica PIOR (plugins[0] instanceof Plugin === false eh assinatura conhecida de spoof ruim).

OVERSHOOT STEALTH:
- Chrome 131 baseline real: navigator.plugins retorna PluginArray COM 5 entradas (PDF Viewer, Chrome PDF Viewer, Chromium PDF Viewer, Microsoft Edge PDF Viewer, WebKit built-in PDF) em headed mode. Em headless e vazio. Patch propoe 3 — desatualizado vs Chrome 131 real (sketch contradiz proprio titulo).
- description sketch diz "Chrome 109+ tem plugins vazio por padrao" — entao spoof com 3 entradas EH overshoot. Real Chrome 131 headed em Win32 retorna 5 PDF viewers especificos. Mismatch = fingerprint inconsistente.
- mimeTypes spoof via Symbol.iterator: se nao linkar via .enabledPlugin reciproco, browserleaks detecta inconsistencia.

TEST_PLAN COBRE RISCOS?
- Cobre: instanceof checks, browserleaks matching.
- NAO cobre: regressao funcional LinkedIn (login flow, feed scroll, message send). NAO cobre: erro em pagina LinkedIn real causado por Proxy mal construido. NAO cobre: comparacao com REAL Chrome 131 plugins dump (so diz "matching" vago). NAO cobre: comportamento quando Patchright esta ativo (no-op confirmado?).
- Falta: snapshot real do navigator.plugins de Chrome 131 stock para baseline.

BENEFICIO MARGINAL: Patchright ja handle plugins nativamente. Patch so vale para fallback path. Severity=high eh exagerado dado escopo.

RISCO > BENEFICIO no estado atual do patch. Implementation sketch tem contradicao interna (Chrome 109+ vazio vs 3 entradas estaticas). Sem baseline Chrome 131 real validado e sem teste regressao LinkedIn, aplicar pode introduzir bugs piores que o problema atual.
- **PATCH-015** — Message NLP variation: template skeleton breaker (score 0/3)
  - FAIL: Falhas tecnicas multiplas:

1) TARGET_FILE ERRADO: stealth.py eh launcher de browser anti-deteccao (Patchright, navigator.webdriver, TLS fingerprint). Nao contem templates de mensagem. Mensageria fica em engager.py/connector.py. Patch nao pode ser aplicado no arquivo declarado.

2) PREMISSA NAO VERIFICADA: "LinkedIn NLP detecta skeleton sintatico" — afirmacao plausivel mas sem evidencia citada. Fontes (meet-lea, heysid, linkboost) sao vendors de outreach, nao papers nem reverse-eng do classificador do LinkedIn. Risco de otimizar contra ameaca nao confirmada.

3) hash(prospect_id) PARA SELECAO: determinismo cria bucket fixo prospect→skeleton. Se LinkedIn agrupar por sender, ainda ve mesmo skeleton repetido N vezes (1/12 frequencia). Pior: prospect_ids sequenciais podem cair no mesmo bucket por viés de hash. Correto seria rotacao com janela deslizante + weighted random anti-reuso recente.

4) SYNONYM SWAP 30% SEM POS-TAG: troca cega via wordlist PT-BR quebra concordancia (genero/numero), regencia verbal, e produz portugues estranho que aumenta suspeita humana e bayes-spam. Teste "manual review N=10" eh amostra insuficiente para 30% swap em msgs comerciais.

5) PERSONALIZATION SLOT via "profile activity scraper": scraping de feed/posts recentes do prospect eh exatamente o sinal que LinkedIn rastreia para detectar bot (acessos a /detail/recent-activity antes de connect request). Mitigacao proposta introduz NOVO vetor de deteccao mais forte do que o que tenta resolver.

6) METRICA JACCARD < 0.6 p95: Jaccard em bag-of-words ignora ordem. Skeleton com mesma estrutura sintatica passa Jaccard baixo via synonym swap. Metrica nao mede o que o patch alega resolver (skeleton sintatico). Correto seria similaridade de arvore sintatica (tree edit distance) ou embedding cosine.

7) "Hash skeleton final + sample N msgs/dia, garantir entropia minima" — entropia minima nao definida numericamente, nao acionavel.

8) Effort M subestimado: pool 8-12 skeletons x 3 intents = 24-36 redacoes humanas + wordlist PT-BR curada + scraper de atividade + telemetria entropia. Eh L/XL.

Recomendacao: rejeitar, reescrever com target correto (engager.py), remover scraper de atividade, trocar Jaccard por metrica sintatica, eliminar synonym swap automatico (usar variantes pre-redigidas)
  - FAIL: FEASIBILITY: rejeito patch como escrito. Razoes:

1) **target_file errado**: stealth.py cuida de fingerprint browser/JS patches, NAO de geracao de mensagens. Logica de templates/mensagens vive em connector.py (e config.py). Patch aplicado em stealth.py nao faz sentido arquitetural.

2) **Effort M subestimado** dado escopo real:
   - Pool 8-12 skeletons x 3 intents = 24-36 templates curados manualmente em PT-BR (trabalho de copy, nao codigo) — sozinho ja eh M.
   - Scraper de "sinal recente" (post titulo, job change) exige novo modulo Playwright navegando profile activity feed — pagina dinamica, lazy load, anti-scrape. Isso sozinho eh L/XL e adiciona risco de deteccao (mais navegacao = mais superficie).
   - Synonym swap PT-BR 30%: wordlist curada nao existe pronta confiavel; usar WordNet PT eh fragil, gera frases agramaticais. Alternativa LLM call por mensagem adiciona custo/latencia/dependencia externa.
   - Entropia Jaccard p95<0.6 + sample diario: telemetria/metrica nova, infra de scoring.
   - Total real: L (~1-2 semanas), nao M.

3) **Dependencias instaveis**:
   - Scraper de "post recente" depende de DOM LinkedIn que muda sem aviso (selectors quebram); aumenta manutencao.
   - Synonym swap automatico em PT-BR sem LLM produz mensagens estranhas — risco de reputacao pior que template repetido.
   - Profile activity feed exige scroll/render adicional → mais tempo na pagina → mais sinal anti-bot, contradiz objetivo stealth do projeto.

4) **Playwright/Patchright suporta**? Tecnicamente sim para scrape, mas conflita com cooldown.py/limiter.py — cada visita extra a profile consome budget diario LinkedIn (provavel ~80-100 views/dia limit). Reduz capacidade de outreach real.

5) **Test plan fraco**: Jaccard<0.6 mede tokens, nao detecta skeleton sintatico (NLP do LinkedIn usa embeddings/n-gramas POS, nao bag-of-words). Metrica nao valida hipotese.

Recomendacao: dividir em 2 patches menores
- PATCH-015a (S): pool de skeletons + hash(prospect_id) selector em connector.py. Sem scrape, sem synonym swap. Effort real S.
- PATCH-015b (L): personalization via signal scrape — patch separado, com analise de custo/budget LinkedIn.

Arquivos relevantes:
- D:/dev-projects/main/hermes-cloud-studio/linkedin/connector.py (target correto)
- D:/dev-projects/main/hermes-cloud-studio/linkedin/config.py (templates atuais)
- D:/dev-projects/main/hermes-cloud-studio/linkedin/limiter.py (budget constraint)
  - FAIL: PATCH-015 rejeitado. Motivos:

1) **target_file ERRADO**: patch aponta `stealth.py` (browser anti-detection — webdriver flag, TLS, CDP leak). Templates de mensagem moram em `connector.py` (`_generate_connection_note`, linhas 157-162, placeholders `{nome}/{empresa}/{titulo}` — NÃO `{firstName}/{company}`) e provavelmente `engager.py`. Aplicar em stealth.py quebra escopo do módulo e não toca o código real de mensagens.

2) **Placeholders inconsistentes**: sketch usa `{firstName}/{company}` (EN), código usa `{nome}/{empresa}/{titulo}` (PT-BR). Implementação cega quebra templates existentes em campaign_config.

3) **Overshoot stealth — risco real**:
   - "Scraper extrai sinal recente (post, job change) via profile activity" = visita extra a `/recent-activity/` por prospect ANTES de connect. Isso multiplica pageviews/perfil, gera padrão de navegação atípico (view→activity→connect em segundos) que LinkedIn detecta MELHOR que skeleton repetido. Contra-stealth.
   - Synonym swap 30% PT-BR sem wordlist curada vira texto agramatical → flag de spam manual + report do prospect (custo reputacional > Jaccard ganho).
   - Hash skeleton por prospect_id é determinístico: mesmo prospect revisitado em campanha nova reusa skeleton — não resolve o problema declarado.

4) **test_plan insuficiente**:
   - Jaccard p95<0.6 mede só similaridade léxica, não detecta skeleton sintático (que é a tese do patch — AST/POS-tag similarity ficaria de fora).
   - N=10 review manual não cobre regressão de sentido após synonym swap em escala.
   - Zero teste de connection acceptance rate antes/depois (KPI real). Zero teste de account health (warnings/restrictions) — métrica que importa pra "detecção pior".
   - Não testa interação com cooldown.py/limiter.py existentes (scraping extra pode estourar quota).

5) **Effort M subestimado**: pool 8-12 skeletons × 3 intents curados em PT-BR + wordlist sinônimos + scraper de activity + entropia monitor = L mínimo.

**Veredito**: risco > benefício. Reescrever patch com target correto (`connector.py` + `engager.py`), remover scraping de activity (usar só dados já coletados), trocar synonym swap por pool maior de skeletons human-written, KPI = acceptance rate + account health (não Jaccard).

## Research findings (raw)

- **[critical/fingerprint]** Cross-attribute fingerprint consistency (getHasLiedOs / getHasLiedLanguages) — LinkedIn valida coerencia entre navigator.userAgent, navigator.oscpu, navigator.platform, maxTouchPoints/msMaxTouchPoints e navigator.languages. Mismatch (ex: UA Windows + platform Linux, ou idioma preferencial != navigator.languages[0]) marca fingerprint como forjado. Patchright/anti-detect que so spoofa UA sem alinhar o resto cai aqui. _(https://blog.castle.io/detecting-forged-browser-fingerprints-for-bot-detection-lessons-from-linkedin/)_
- **[critical/fingerprint]** WebGL renderer vs UA class mismatch — LinkedIn checa se GPU exposto via WebGL UNMASKED_RENDERER bate com a classe do dispositivo declarado no UA (mobile Android nao pode expor GPU desktop Mac/Intel HD). Mismatch GPU<->UA dispara score de bot. _(https://blog.castle.io/detecting-forged-browser-fingerprints-for-bot-detection-lessons-from-linkedin/)_
- **[high/fingerprint]** Canvas/WebGL/Audio/Font unification checks — Defensores (LinkedIn) e ofensores (BotBrowser/CloakBrowser) confirmam que detecao moderna cruza outputs de Canvas 2D, WebGL pixel hash, AudioContext (OfflineAudioContext rendering) e enumeracao de fontes para verificar se sao mutuamente consistentes com hardware reportado (hardwareConcurrency, deviceMemory). Patches em runtime (JS-level) deixam artefatos detectaveis; so patches source-level em Chromium passam. _(https://github.com/CloakHQ/CloakBrowser ; https://www.geetest.com/en/article/how-to-defeat-botbrowser-in-2025)_
- **[critical/network]** JA3/JA4 TLS fingerprint — LinkedIn gera JA3/JA4 do TLS handshake e compara com baselines de browsers reais. JA4 (sucessor de JA3) cobre TLS 1.3 e QUIC/HTTP3. Clientes Python (httpx/requests) ou Node nativo tem JA3 distinto de Chrome real => bloqueio antes do HTTP. _(https://scrapfly.io/blog/posts/how-to-scrape-linkedin ; https://proxyhat.com/blog/tls-fingerprinting-explained)_
- **[high/network]** HTTP/2 frame fingerprint — Alem de TLS, ordem dos SETTINGS frames, WINDOW_UPDATE, header frame order e PRIORITY frames do HTTP/2 identificam a stack do cliente. Mismatch entre JA3 (Chrome) e h2 fingerprint (Go/Python) flagra automacao. _(https://scrapfly.io/blog/posts/how-to-scrape-linkedin)_
- **[critical/network]** IP reputation: datacenter vs residential vs mobile — LinkedIn expandiu detecao de proxy em 2025. Datacenter IPs queimam li_at em 1 sessao e retornam authwall. Residenciais flagged (~50% survival). Mobile IPs (~85% survival). ASN, geolocalizacao e historico de abuso entram no fraud score. _(https://use-apify.com/blog/best-proxies-linkedin-scraping-2026 ; https://salesso.com/blog/linkedin-proxy/)_
- **[critical/session]** Session continuity (li_at + IP + fingerprint binding) — li_at cookie e amarrado a IP de login + fingerprint + geo. Rotacao de IP no meio da sessao invalida cookie imediatamente. Sticky residencial 10-30min por sessao e necessario. Cookies sem trail organico (sem JSESSIONID, bcookie, lidc gerados via navegacao real) sao detectados. _(https://use-apify.com/blog/best-proxies-linkedin-scraping-2026 ; https://scrapfly.io/blog/posts/how-to-scrape-linkedin)_
- **[high/rate]** Authwall trigger em 3-5 perfis — Rate limit granular: usuarios free batem authwall apos 3-5 perfis em sequencia rapida sem comportamento de navegacao (sem scroll, sem hover, sem dwell time). Threshold cumulativo + ausencia de sinais comportamentais. _(https://scrapfly.io/blog/posts/how-to-scrape-linkedin)_
- **[high/behavior]** Activity pattern analysis (3AM, intervalos constantes, geo-mismatch) — Modelos comportamentais flagam atividade em horarios anomalos (3AM constante), intervalos perfeitamente regulares (ex: a cada 2min), e geo do IP != geo declarada no perfil. LinkedIn limita acoes free a ~100/dia (visits+invites+msgs combinados). _(https://salesso.com/blog/linkedin-proxy/ ; https://getsales.io/blog/linkedin-automation-safety-guide-2026/)_
- **[high/behavior]** Mouse dynamics / keystroke biometrics — Telemetria de movimentos (entropia da trajetoria, velocidade, aceleracao, pausas), dwell/flight time de teclas e padroes de scroll alimentam classificadores. Bots com mouse linear/teleportado ou typing instantaneo (Playwright .fill) sao detectados. Arkose/LinkedIn pre-classifica risco com esses sinais antes de servir desafio. _(https://ucaptcha.net/blog/funcaptcha-arkose-labs/ ; https://dl.acm.org/doi/10.1145/3640311)_
- **[high/challenge]** Arkose Labs (FunCaptcha/MatchKey) tiered challenge — LinkedIn usa Arkose em registro/login/acoes sensiveis. Telemetria (fingerprint+mouse+IP) classifica em tiers: low-risk passa sem challenge, mid recebe rotacao de imagem 3D, high recebe puzzles encadeados ou bloqueio direto. Dominio funcaptcha.com ainda em uso. _(https://ucaptcha.net/blog/funcaptcha-arkose-labs/ ; https://www.arkoselabs.com/arkose-matchkey/)_
- **[high/challenge]** Email/phone/ID verification escalation — Contas free com fraud score alto recebem step-up: verificacao por email, depois SMS/telefone, depois selfie/ID. Em 2025 LinkedIn intensificou ban + lawsuits (Proxycurl jan/2025, remocao Apollo/Seamless mar/2025). ~89% das contas restritas se recuperam em 7-14 dias se pararem automacao. _(https://expandi.io/blog/linkedin-account-restricted/ ; https://autoposting.ai/linkedin-account-restricted/)_
- **[medium/fingerprint]** BrowserGate — vigilancia via extensoes — Investigacao Medium (Akalin) reporta que LinkedIn coleta sinais de ~6000 extensoes instaladas no browser via probing silencioso (chrome-extension://ID/manifest.json fetch ou web_accessible_resources), criando fingerprint estavel mesmo com canvas/UA randomizados. Verificar antes de adotar como confirmado. _(https://medium.com/@makalin/the-great-browser-heist-inside-browsergate-linkedins-silent-6-000-extension-surveillance-machine-c731898363ea)_
- **[medium/fingerprint]** Patchright headless leaks (User-Agent 'Headless' + CDP traces) — Issue #46 patchright-python (abr/2025): modo headless ainda vaza 'HeadlessChrome' no UA e mantem traces CDP (Runtime.evaluate, console API hooks) detectaveis. Patchright cobre --disable-blink-features=AutomationControlled e remove --enable-automation mas headless precisa de overrides manuais. _(https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python/issues/46)_
- **[medium/network]** Post-quantum TLS expondo scrapers — Chrome 124+ habilita X25519Kyber768/MLKEM por default. Scrapers com stacks TLS antigas (sem PQ key exchange) ficam visivelmente diferentes do baseline Chrome real, agravando JA4 mismatch em 2025/2026. _(https://scrapfly.io/blog/posts/post-quantum-tls-bot-detection)_
- **[critical/fingerprint]** puppeteer-extra-stealth descontinuado e detectado por LinkedIn — Plugin foi descontinuado em fev/2025. LinkedIn e Cloudflare detectam padroes do stealth plugin diretamente. Stack Node.js stealth virou legacy; ecosystem Python (playwright-stealth, Camoufox) eh ativamente mantido em 2026. _(https://scrapfly.io/blog/posts/puppeteer-stealth-complete-guide ; https://roundproxies.com/blog/how-to-bypass-anti-bots/)_
- **[high/fingerprint]** Camoufox: spoofing C++ no Firefox (0% headless detection) — Camoufox modifica Firefox em nivel C++ antes do JS inspecionar, alcancando 0% headless detection vs 67% reducao do Patchright (JS patching de CDP leaks). Passou Instagram/LinkedIn/X/Reddit sem cookies em benchmark 2026. Trade-off: travado em Firefox, alguns sites servem conteudo diferente. _(https://github.com/daijro/camoufox ; https://camoufox.com/stealth/ ; https://kahtaf.com/blog/browser-automation-compared/)_
- **[high/fingerprint]** nodriver supera todos contra Cloudflare Turnstile — Benchmark 2026 (31 alvos Cloudflare): nodriver 28/28 OK, Patchright 25/28, Camoufox 25/28, CloakBrowser 26/28. nodriver passa canadianinsider (Turnstile) enquanto todo Chromium-patched falha. Automation-protocol fingerprinting eh camada separada de TLS/JS que Playwright-based nao resolve. _(https://ianlpaterson.com/blog/anti-detect-browser-benchmark-patchright-nodriver-curl-cffi/)_
- **[medium/fingerprint]** Patchright: limites contra Cloudflare alto e DataDome — Patchright patcheia Playwright Chromium fixando CDP leaks via JS isolation, ~67% reducao em headless detection. Falha em Cloudflare niveis altos e DataDome quando headless sem setup adicional. Funciona contra fingerprinting basico. _(https://github.com/pim97/anti-detect-browser-tools-tech-comparison ; https://roundproxies.com/blog/best-patchright-alternatives/)_
- **[critical/fingerprint]** LinkedIn coleta 48 caracteristicas + 65 params WebGL + 6167 extensoes — LinkedIn coleta 48 caracteristicas distintas por login (HW/SW), 65+ valores de WebGL parameters, e escaneia 6167 extensoes browser especificas (feb/2026, vs 461 em 2024 — projeto BrowserGate). ML detecta randomizacao excessiva E fingerprint estatico demais. _(https://medium.com/@makalin/the-great-browser-heist-inside-browsergate-linkedins-silent-6-000-extension-surveillance-machine-c731898363ea ; https://www.proxies.sx/use-cases/privacy/fingerprinting)_
- **[high/network]** Mobile proxies: 85% account survival vs 50% residential — Pos-expansao de deteccao LinkedIn 2025, mobile carrier IPs alcancam ~85% de sobrevivencia de conta vs ~50% de residential proxies. Gap aumentou significativamente. Datacenter IPs bloqueados instantaneamente. _(https://torchproxies.com/why-most-proxies-fail-linkedins-detection-in-2026/ ; https://dataimpulse.com/blog/best-proxies-for-linkedin/)_
- **[high/session]** ISP static proxy 1:1 por conta com sticky 24h-7d — Best practice 2026: 1 ISP static proxy dedicado por conta LinkedIn (~$2.3/IP/mes, escala ate 20-30 contas). Sticky session minimo 24h, ideal 7 dias. Rotating residential quebra continuidade de IP que LinkedIn espera. Cookies li_at/JSESSIONID expiram se IP/fingerprint/padrao mudar. _(https://research.aimultiple.com/linkedin-proxies/ ; https://use-apify.com/blog/best-proxies-linkedin-scraping-2026 ; https://sales-mind.ai/en/blog/post/how-to-find-linkedin-session-cookie)_
- **[high/rate]** Rate limit seguro: 20-30 conn/dia, 10-15 profile views/IP/hora — Limites 2026: 20-30 connection requests/dia (NAO 100), 10-15 profile pages/IP/hora, sessoes em horario comercial do timezone do IP. 100+ conn/semana = flag. Premium (Sales Nav/Recruiter) 150-200/sem. Manter taxa de aceite >70% obrigatorio. _(https://getsales.io/blog/linkedin-automation-safety-guide-2026/ ; https://www.dux-soup.com/blog/linkedin-automation-safety-guide-how-to-avoid-account-restrictions-in-2026)_
- **[high/behavior]** Warm-up 14 dias manual antes de qualquer automacao — Contas <60 dias ou <150 conexoes: comecar 10-15 req/dia, ramp +5/semana. 14 dias warm-up manual obrigatorio antes de automacao. Profile completo (foto, headline, experiencia) + 5-10 conn/dia para conhecidos + likes/comments organicos. LinkedIn rastreia Activity DNA (timing, padroes). _(https://blog.closelyhq.com/warm-up-new-linkedin-account-automation-without-getting-restricted/ ; https://linkedinsider.blog/linkedin-account-warm-up)_
- **[high/behavior]** Bezier curves cubicos + minimum-jerk velocity profile — Mouse humano: cubic Bezier com control points randomizados, velocity profile minimum-jerk (10t^3 - 15t^4 + 6t^5) produzindo curva bell-shaped (Fitts's Law). Adicionar tremor 1-3px por frame + micro-ajustes estocasticos sub-movimento. Ghost-cursor (Node) implementa isso. _(https://arxiv.org/html/2410.18233v1 ; https://roundproxies.com/blog/ghost-cursor/ ; https://www.researchgate.net/publication/393981520_Emulating_Human-Like_Mouse_Movement_Using_Bezier_Curves_and_Behavioral_Models_for_Advanced_Web_Automation)_
- **[high/behavior]** Typing: dwell 40-200ms, flight 80-400ms, digramas reais — Dwell time (keydown-keyup): 40-120ms humano, randomizar +-30ms (valor fixo eh detectavel). Flight time (release-press): 80-400ms. Delay entre digramas seguir bancos empiricos (th rapido, zq lento). Pydoll documenta isso. _(https://pydoll.tech/docs/deep-dive/fingerprinting/behavioral-fingerprinting/)_
- **[medium/behavior]** Cloud-based tools > browser extensions para evitar fingerprint — Extensoes browser causam fluctuacao local de IP + fingerprint instavel = trigger LinkedIn. Cloud-based automation com IP fixo + fingerprint consistente reduz deteccao. LinkedIn escaneia 6167 extensoes especificas (BrowserGate). _(https://salestarget.ai/blogs/linkedin-automation-safety-2026 ; https://medium.com/@makalin/the-great-browser-heist-inside-browsergate-linkedins-silent-6-000-extension-surveillance-machine-c731898363ea)_
- **[medium/behavior]** Personalizacao obrigatoria + engagement-first — Mensagens template identicas = flag instantaneo via ML. Personalizar referenciando post recente, mudanca de cargo ou anuncio de empresa. Engagement-first (likes/comments) antes de conn request aumenta acceptance rate. Acceptance <40% = restricao. _(https://www.heysid.com/resources/how-to-automate-linkedin-outreach-safely ; https://www.linkboost.co/blog/linkedin-relationship-building-automation-limits-2026/)_
- **[medium/network]** Arquitetura vencedora: API gerenciada > DIY scraping — Caso real: Selenium falhou em canvas fingerprint, Playwright+stealth durou mais mas caiu. Solucao que funcionou: Bright Data LinkedIn API (150M+ residential IPs, gerenciamento de sessao, CAPTCHA solving, DOM parsing internos). Batch 100 URLs/req, retry em 429. _(https://plainenglish.io/web-scraping/linkedin-banned-my-scraper-3-times-here-s-the-architecture-that-finally-worked)_
- **[medium/session]** Cookie injection Netscape format para sessoes autenticadas — Para dados protegidos (LinkedIn, Amazon): injetar cookies Netscape-format via endpoint dedicado (ex Camoufox /sessions/:userId/cookies) reaproveita sessao autenticada e bypassa login wall. Combinar com mesmo IP sticky para nao quebrar li_at. _(https://camoufox.com/stealth/ ; https://phantombuster.com/blog/linkedin-automation/linkedin-session-cookie-disconnected/)_
