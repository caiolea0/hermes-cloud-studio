# HARNESS-EXTENSION-PATCH — Fase F

Documento de orientação humana para estender `scripts/validate_implementation.py` com os novos `assert kinds` exigidos pela **Fase F — Visual + WS + Regression + Ecosystem**. NÃO é um patch git aplicável direto: é um guia passo-a-passo + pseudo-código pronto pra colar.

Aplicar este patch **antes** de rodar:

```bash
python scripts/validate_implementation.py --phase F
```

---

## 1. Introdução

### 1.1 O que este patch estende

O harness atual (`scripts/validate_implementation.py`, 366 linhas) cobre 8 `kinds`:

```
grep_present, grep_absent, file_exists, count_max,
line_count_max, sqlite_table, sqlite_column, http_test
```

A Fase F introduz 10 `kinds` novos, focados em validação ponta-a-ponta de UI, contratos WebSocket, regressões de fases anteriores e presença de assets do ecossistema Claude Code (workflows, skills, subagents, MCPs):

| Kind                       | Categoria         | Implementação                                |
|----------------------------|-------------------|----------------------------------------------|
| `ui_visible`               | Visual            | Playwright headless + locator                |
| `ws_subscribed`            | Contrato WS       | websocket-client connect + subscribe + recv  |
| `endpoint_consumed`        | UI ↔ API binding  | grep especializado em `dashboard/app.js`     |
| `regression_phase_pass`    | Meta-validação    | subprocess recursivo do próprio harness      |
| `table_exists`             | DB (alias)        | Wrapper sobre `sqlite_table` com VM/PC auto  |
| `screenshot_match`         | Visual diff       | Playwright screenshot + Pillow pixel diff    |
| `workflow_exists`          | Ecossistema       | file_exists em `.claude/workflows/<name>.md` |
| `mcp_registered`           | Ecossistema       | grep em `.claude/settings.json` mcpServers   |
| `skill_exists`             | Ecossistema       | file_exists em `.claude/skills/<name>/`      |
| `subagent_exists`          | Ecossistema       | file_exists em `.claude/agents/<name>.md`    |

### 1.2 Por quê

Fase A→E validou **código fonte estático** (regex em arquivos). Fase F precisa provar:

- O dashboard **realmente renderiza** o que a Fase B disse que mandava por WS.
- WebSocket **realmente emite** os eventos `/ws/health`, `/ws/daemon`, `/ws/queue`.
- Mudanças da Fase F **não regrediram** Fases A–E (smoke recursivo).
- Skills/workflows/subagents/MCPs documentados existem no disco e estão registrados.

### 1.3 Mudança de regex de fase (CRÍTICO)

Linha 84 do harness atual:

```python
m_phase = re.match(r"^-?\s*phase:\s*([A-E](?:\.\d+)?)", s)
```

só aceita fases `A–E`. Trocar por:

```python
m_phase = re.match(r"^-?\s*phase:\s*([A-Z](?:\.\d+)?)", s)
```

Sem esse swap, o parser **ignora silenciosamente** todos os findings `phase: F`.

---

## 2. Por tipo novo de assert

Cada subseção tem: **(a)** pseudo-código colável, **(b)** exemplo no CHECKLIST, **(c)** limitações/testabilidade.

---

### 2.1 `ui_visible`

Renderiza o dashboard em Chromium headless, navega até a URL alvo e confirma que o seletor CSS está visível (não `display:none`, não `aria-hidden`).

#### Pseudo-código

```python
def check_ui_visible(target: str, pattern: str) -> dict:
    """target = URL (http://localhost:8765/dashboard)
       pattern = CSS selector (#health-status-led, .daemon-row[data-state='running'])
       description opcional na 3a parte: timeout em ms (default 5000)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "reason": "playwright nao instalado (pip install playwright)"}

    url = target.strip()
    selector = pattern.strip()
    timeout_ms = 5000

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={"width": 1280, "height": 800})
            page = ctx.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            try:
                page.wait_for_selector(selector, state="visible", timeout=timeout_ms)
                visible = True
            except Exception:
                visible = False
            text = page.locator(selector).first.text_content() if visible else None
            browser.close()
        if visible:
            return {"ok": True, "text": (text or "")[:120]}
        return {"ok": False, "reason": f"selector {selector} nao visivel em {url}"}
    except Exception as e:
        return {"ok": False, "reason": f"ui check failed: {e}"}
```

#### Exemplo no CHECKLIST

```
### MERGED-F-001
- phase: F.1
  - ui_visible: http://localhost:8765/dashboard / #ws-health-led.connected / Verde quando WS health subiu
  - ui_visible: http://localhost:8765/dashboard / .daemon-card[data-status='running'] / Card daemon mostra status
```

#### Limitações

- Requer dashboard subido na porta esperada **antes** de rodar (`PORTS.json` → 8765).
- Sem servidor → todas as checks falham (não é regressão de código, é ambiente). Considerar SKIP automático: se `requests.get(url, timeout=2)` retorna ConnectionError, marcar `skipped=true` em vez de FAIL.
- Headless ≠ headful: alguns CSS reagem a `prefers-reduced-motion` ou viewport.
- Não detecta regressões puramente visuais (cor errada, posicionamento) — use `screenshot_match` pra isso.

#### Testabilidade

```bash
# Dry: spawn dashboard antes
python -m hermes_api_v2 &  # ou comando do projeto
sleep 2
python scripts/validate_implementation.py --finding MERGED-F-001
```

---

### 2.2 `ws_subscribed`

Conecta no WebSocket, envia subscribe (se aplicável), e recebe pelo menos 1 mensagem dentro do timeout.

#### Pseudo-código

```python
def check_ws_subscribed(target: str, pattern: str) -> dict:
    """target = ws URL (ws://localhost:8765/ws/health)
       pattern = chave/regex que precisa aparecer no payload JSON (ex: 'status' ou '\"event\":\"health\"')
       description (3a parte) opcional: timeout segundos (default 5)."""
    try:
        from websocket import create_connection
    except ImportError:
        return {"ok": False, "reason": "websocket-client nao instalado (pip install websocket-client)"}

    url = target.strip()
    expected = pattern.strip()
    timeout_s = 5

    try:
        ws = create_connection(url, timeout=timeout_s)
        # Alguns endpoints precisam subscribe explicito:
        if "subscribe" in expected.lower():
            ws.send(json.dumps({"action": "subscribe"}))
        msg = ws.recv()
        ws.close()
        if re.search(expected, msg):
            return {"ok": True, "sample": msg[:200]}
        return {"ok": False, "reason": f"payload sem '{expected}': {msg[:200]}"}
    except Exception as e:
        return {"ok": False, "reason": f"ws check failed: {e}"}
```

#### Exemplo no CHECKLIST

```
### MERGED-F-010
- phase: F.2
  - ws_subscribed: ws://localhost:8765/ws/health / "service":"api" / Health WS emite status do API
  - ws_subscribed: ws://localhost:8765/ws/daemon / "daemon_state" / Daemon WS emite estado
  - ws_subscribed: ws://localhost:8765/ws/queue / "queue_size" / Queue WS emite tamanho
```

#### Limitações

- Dependência runtime: `pip install websocket-client` (não confundir com `websockets`).
- Mesma questão de ambiente que `ui_visible`: server precisa estar UP.
- Não valida **sequência** de mensagens — só presença da primeira matching. Pra ordem, usar runner customizado.
- Token de auth: se WS exige `Authorization`, expandir runner pra ler `os.environ.get("HERMES_WS_TOKEN")` e passar via header.

#### Testabilidade

```bash
# Manual: usa wscat antes
wscat -c ws://localhost:8765/ws/health
# Se retornar JSON, harness vai passar.
python scripts/validate_implementation.py --phase F.2
```

---

### 2.3 `endpoint_consumed`

`grep_present` especializado em `dashboard/app.js`: confirma que o endpoint REST ou WS está **consumido** pelo front (fetch/WebSocket constructor).

#### Pseudo-código

```python
def check_endpoint_consumed(target: str, pattern: str) -> dict:
    """target = caminho do app.js (default dashboard/app.js)
       pattern = endpoint (/api/health, /ws/daemon)."""
    p = _resolve_path(target if target else "dashboard/app.js")
    if not p.exists():
        return {"ok": False, "reason": f"app.js nao existe: {target}"}
    content = p.read_text(encoding="utf-8", errors="ignore")
    endpoint = pattern.strip()
    # Heuristica: fetch(`...endpoint...`) OU new WebSocket(`...endpoint...`) OU axios/fetch literal
    patterns = [
        rf"fetch\([`'\"][^`'\"]*{re.escape(endpoint)}",
        rf"new\s+WebSocket\([`'\"][^`'\"]*{re.escape(endpoint)}",
        rf"axios\.[a-z]+\([`'\"][^`'\"]*{re.escape(endpoint)}",
        rf"url:\s*[`'\"][^`'\"]*{re.escape(endpoint)}",
    ]
    for pat in patterns:
        if re.search(pat, content):
            return {"ok": True, "via": pat}
    return {"ok": False, "reason": f"endpoint {endpoint} nao consumido em {target}"}
```

#### Exemplo no CHECKLIST

```
### MERGED-F-020
- phase: F.3
  - endpoint_consumed: dashboard/app.js / /api/health / Front consome health endpoint
  - endpoint_consumed: dashboard/app.js / /ws/queue / Front abre WS de queue
```

#### Limitações

- Falsos negativos se o endpoint for **montado dinamicamente** (`fetch(API_BASE + "/health")` com `API_BASE` em variável). Solução: padronizar literal ou adicionar pattern extra.
- Não valida **uso correto** (poderia chamar e ignorar resposta). Combinar com `ui_visible` pra cobrir uso real.

#### Testabilidade

Estático — não precisa de servidor. Roda em qualquer máquina.

---

### 2.4 `regression_phase_pass`

Roda o próprio harness recursivamente pra uma fase A–E e confirma `summary.fail == 0`. Garante que Fase F não regrediu fases anteriores.

#### Pseudo-código

```python
def check_regression_phase_pass(target: str, pattern: str) -> dict:
    """target = identificador de fase (A, B, C, D, E ou C.2)
       pattern = '' (ignorado)."""
    phase = target.strip()
    try:
        out = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--phase", phase, "--json"],
            capture_output=True, text=True, timeout=120,
        )
        if out.returncode not in (0, 2):
            return {"ok": False, "reason": f"recursive call exit {out.returncode}: {out.stderr[:200]}"}
        report = json.loads(out.stdout)
        fail = report.get("summary", {}).get("fail", -1)
        total = report.get("summary", {}).get("total", 0)
        if fail == 0 and total > 0:
            return {"ok": True, "phase": phase, "total": total}
        return {"ok": False, "reason": f"phase {phase} tem {fail}/{total} FAIL", "flags": report.get("flags", [])}
    except Exception as e:
        return {"ok": False, "reason": f"regression call failed: {e}"}
```

#### Exemplo no CHECKLIST

```
### MERGED-F-030
- phase: F.4
  - regression_phase_pass: A /  / Fase A continua 100% PASS
  - regression_phase_pass: B /  / Fase B continua 100% PASS
  - regression_phase_pass: C /  / Fase C continua 100% PASS
  - regression_phase_pass: D /  / Fase D continua 100% PASS
  - regression_phase_pass: E /  / Fase E continua 100% PASS
```

#### Limitações

- **Recursão**: NUNCA listar `regression_phase_pass: F` (loop infinito). Guarda explicito:
  ```python
  if phase.startswith("F"):
      return {"ok": False, "reason": "recursão na propria Fase F bloqueada"}
  ```
- Lento: 5 chamadas A–E podem somar 30–60s. Cachear via `--json` em `validation-report-<phase>.json` se virar gargalo.

#### Testabilidade

```bash
python scripts/validate_implementation.py --finding MERGED-F-030
```

---

### 2.5 `table_exists`

Alias semântico de `sqlite_table` com auto-detect de DB padrão: se `target` vazio, usa `data/hermes.db` (PC) ou `~/.hermes/hermes.db` (VM via SSH).

#### Pseudo-código

```python
def check_table_exists(target: str, pattern: str) -> dict:
    """target = caminho do .db ('' = default por kind)
       pattern = nome da tabela."""
    if not target.strip():
        target = "data/hermes.db"  # default PC
    return check_sqlite_table(target, pattern)
```

#### Exemplo no CHECKLIST

```
### MERGED-F-040
- phase: F.5
  - table_exists: data/hermes.db / phase_f_audit / Log de Fase F existe
  - table_exists: ~/.hermes/hermes.db / phase_f_audit / Log presente na VM
```

#### Limitações + testabilidade

Mesmas do `sqlite_table` (já documentado no harness existente). Wrapper só reduz boilerplate.

---

### 2.6 `screenshot_match`

Tira screenshot via Playwright e compara pixel-a-pixel com baseline em `.claude/screenshots/baseline/<finding>.png`. Tolerância configurável.

#### Pseudo-código

```python
def check_screenshot_match(target: str, pattern: str) -> dict:
    """target = URL
       pattern = nome do baseline (sem extensao, ex: dashboard_idle)
       description opcional: 'threshold:0.05' (5% pixels diff aceitos)."""
    try:
        from playwright.sync_api import sync_playwright
        from PIL import Image, ImageChops
    except ImportError:
        return {"ok": False, "reason": "playwright + Pillow necessarios"}

    url = target.strip()
    base_name = pattern.strip()
    threshold = 0.02  # default 2%
    baseline = BASE_DIR / ".claude" / "screenshots" / "baseline" / f"{base_name}.png"
    actual = BASE_DIR / ".claude" / "screenshots" / "actual" / f"{base_name}.png"
    actual.parent.mkdir(parents=True, exist_ok=True)

    if not baseline.exists():
        return {"ok": False, "reason": f"baseline ausente: {baseline}. Gerar com --capture-baselines"}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
            page.goto(url, wait_until="networkidle", timeout=8000)
            page.screenshot(path=str(actual), full_page=False)
            browser.close()

        img_a = Image.open(baseline).convert("RGB")
        img_b = Image.open(actual).convert("RGB")
        if img_a.size != img_b.size:
            return {"ok": False, "reason": f"size mismatch {img_a.size} vs {img_b.size}"}
        diff = ImageChops.difference(img_a, img_b)
        bbox = diff.getbbox()
        if bbox is None:
            return {"ok": True, "diff_pct": 0.0}
        # Conta pixels nao-zero
        nonzero = sum(1 for px in diff.getdata() if any(px))
        total = img_a.width * img_a.height
        diff_pct = nonzero / total
        ok = diff_pct <= threshold
        return {"ok": ok, "diff_pct": round(diff_pct, 4), "threshold": threshold,
                "actual": str(actual.relative_to(BASE_DIR))}
    except Exception as e:
        return {"ok": False, "reason": f"screenshot check failed: {e}"}
```

#### Exemplo no CHECKLIST

```
### MERGED-F-050
- phase: F.6
  - screenshot_match: http://localhost:8765/dashboard / dashboard_idle / threshold:0.03
```

#### Limitações

- Baselines precisam ser **gerados manualmente** primeira vez. Adicionar flag CLI `--capture-baselines` que captura sem comparar.
- Anti-aliasing + fontes diferentes (Chromium versão) → falsos positivos. 2% threshold default cobre razoável.
- Animações: deve usar `wait_until=networkidle` + opcionalmente `page.add_style_tag(content="*{animation:none!important;transition:none!important}")`.
- Não rodar em CI sem fontes embarcadas — gera diff gigante.

#### Testabilidade

```bash
# Primeira vez (capturar baseline manualmente):
# 1. Subir dashboard
# 2. Rodar playwright manual:
python -c "from playwright.sync_api import sync_playwright; \
  p=sync_playwright().start(); b=p.chromium.launch(); pg=b.new_context().new_page(); \
  pg.goto('http://localhost:8765/dashboard'); pg.wait_for_load_state('networkidle'); \
  pg.screenshot(path='.claude/screenshots/baseline/dashboard_idle.png'); b.close()"

# Depois:
python scripts/validate_implementation.py --finding MERGED-F-050
```

---

### 2.7 `workflow_exists`

Confirma `.claude/workflows/<name>.md` existe e não-vazio.

#### Pseudo-código

```python
def check_workflow_exists(target: str, pattern: str) -> dict:
    """target = nome do workflow (sem extensao)
       pattern = '' ou 'non-empty'."""
    name = target.strip()
    p = BASE_DIR / ".claude" / "workflows" / f"{name}.md"
    if not p.exists():
        return {"ok": False, "reason": f"workflow ausente: .claude/workflows/{name}.md"}
    if p.stat().st_size == 0:
        return {"ok": False, "reason": f"workflow vazio: {name}.md"}
    return {"ok": True, "size": p.stat().st_size}
```

#### Exemplo

```
### MERGED-F-060
- phase: F.7
  - workflow_exists: linkedin-anti-detection-sweep /  / Workflow stealth sweep registrado
  - workflow_exists: hermes-bug-hunt-deep /  / Workflow bug hunt profundo
```

#### Limitações + testabilidade

Estático, trivialmente testável. Não valida **conteúdo semântico** do workflow — apenas presença.

---

### 2.8 `mcp_registered`

Grep em `.claude/settings.json` (ou `settings.local.json`) seção `mcpServers` procurando o nome do MCP.

#### Pseudo-código

```python
def check_mcp_registered(target: str, pattern: str) -> dict:
    """target = nome do MCP (chave em mcpServers)
       pattern = '' ou comando esperado (substring)."""
    name = target.strip()
    candidates = [
        BASE_DIR / ".claude" / "settings.json",
        BASE_DIR / ".claude" / "settings.local.json",
    ]
    for cfg in candidates:
        if not cfg.exists():
            continue
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
        except Exception:
            continue
        mcps = data.get("mcpServers") or data.get("mcp_servers") or {}
        if name in mcps:
            entry = mcps[name]
            if pattern and pattern not in json.dumps(entry):
                return {"ok": False, "reason": f"MCP {name} registrado mas sem pattern '{pattern}'"}
            return {"ok": True, "where": str(cfg.relative_to(BASE_DIR))}
    return {"ok": False, "reason": f"MCP {name} nao registrado em settings*.json"}
```

#### Exemplo

```
### MERGED-F-070
- phase: F.8
  - mcp_registered: agentmemory / 3111 / MCP agentmemory aponta porta 3111
  - mcp_registered: hermes-stealth /  / MCP stealth registrado
```

#### Limitações

- Não valida que o MCP **inicia** — só que está listado. Pra liveness, combinar com http_test no endpoint do MCP.

#### Testabilidade

Estático. Roda em qualquer máquina.

---

### 2.9 `skill_exists`

Confirma `.claude/skills/<name>/SKILL.md` (formato canônico) OU `.claude/skills/<name>.md`.

#### Pseudo-código

```python
def check_skill_exists(target: str, pattern: str) -> dict:
    name = target.strip()
    candidates = [
        BASE_DIR / ".claude" / "skills" / name / "SKILL.md",
        BASE_DIR / ".claude" / "skills" / f"{name}.md",
    ]
    for c in candidates:
        if c.exists() and c.stat().st_size > 0:
            return {"ok": True, "where": str(c.relative_to(BASE_DIR))}
    return {"ok": False, "reason": f"skill ausente: {name} (procurado em skills/{name}/SKILL.md e skills/{name}.md)"}
```

#### Exemplo

```
### MERGED-F-080
- phase: F.9
  - skill_exists: hermes-bug-hunt /  /
  - skill_exists: hermes-deploy /  /
  - skill_exists: hermes-status /  /
  - skill_exists: hermes-stealth-audit /  /
  - skill_exists: hermes-li-lab /  /
```

#### Limitações + testabilidade

Estático. Não valida frontmatter da skill (description/trigger). Se quiser, expandir com regex de `description:` no YAML.

---

### 2.10 `subagent_exists`

Confirma `.claude/agents/<name>.md` existe e tem frontmatter mínimo (`name:`, `description:`).

#### Pseudo-código

```python
def check_subagent_exists(target: str, pattern: str) -> dict:
    name = target.strip()
    p = BASE_DIR / ".claude" / "agents" / f"{name}.md"
    if not p.exists():
        return {"ok": False, "reason": f"subagent ausente: .claude/agents/{name}.md"}
    content = p.read_text(encoding="utf-8", errors="ignore")
    # Frontmatter minimo
    if not re.search(r"^name:\s*\S+", content, re.MULTILINE):
        return {"ok": False, "reason": "frontmatter sem 'name:'"}
    if not re.search(r"^description:\s*\S+", content, re.MULTILINE):
        return {"ok": False, "reason": "frontmatter sem 'description:'"}
    return {"ok": True, "size": p.stat().st_size}
```

#### Exemplo

```
### MERGED-F-090
- phase: F.9
  - subagent_exists: hermes-prospector /  /
  - subagent_exists: hermes-outreach-writer /  /
  - subagent_exists: hermes-stealth-guardian /  /
```

#### Limitações + testabilidade

Estático. Não executa o subagent — só confirma definição.

---

## 3. Como integrar ao `validate_implementation.py` existente

Ordem dos passos:

### Passo 3.1 — Expandir regex de fase

**Localização**: linha 84.

```diff
-    m_phase = re.match(r"^-?\s*phase:\s*([A-E](?:\.\d+)?)", s)
+    m_phase = re.match(r"^-?\s*phase:\s*([A-Z](?:\.\d+)?)", s)
```

### Passo 3.2 — Adicionar as 10 novas funções

Inserir o **bloco completo** após `check_http_test` (linha 252), **antes** do `# ───── Runner ─────` (linha 254). Ordem sugerida: estáticos primeiro (mais rápidos, sem dependência externa), dinâmicos depois:

1. `check_workflow_exists`
2. `check_skill_exists`
3. `check_subagent_exists`
4. `check_mcp_registered`
5. `check_table_exists`
6. `check_endpoint_consumed`
7. `check_ui_visible`
8. `check_ws_subscribed`
9. `check_screenshot_match`
10. `check_regression_phase_pass`

### Passo 3.3 — Registrar no `CHECK_RUNNERS`

Linha 256, expandir o dict:

```python
CHECK_RUNNERS = {
    "grep_present": check_grep_present,
    "grep_absent": check_grep_absent,
    "file_exists": check_file_exists,
    "count_max": check_count_max,
    "line_count_max": check_line_count_max,
    "sqlite_table": check_sqlite_table,
    "sqlite_column": check_sqlite_column,
    "http_test": check_http_test,
    # Fase F
    "ui_visible": check_ui_visible,
    "ws_subscribed": check_ws_subscribed,
    "endpoint_consumed": check_endpoint_consumed,
    "regression_phase_pass": check_regression_phase_pass,
    "table_exists": check_table_exists,
    "screenshot_match": check_screenshot_match,
    "workflow_exists": check_workflow_exists,
    "mcp_registered": check_mcp_registered,
    "skill_exists": check_skill_exists,
    "subagent_exists": check_subagent_exists,
}
```

### Passo 3.4 — Atualizar texto de ajuda do argparse

Linha 300, trocar:

```diff
-    p.add_argument("--phase", help="Run só esta fase (A/B/C/D/E)")
+    p.add_argument("--phase", help="Run só esta fase (A/B/C/D/E/F)")
```

### Passo 3.5 — Instalar dependências runtime

```bash
pip install playwright websocket-client Pillow
python -m playwright install chromium
```

Adicionar essas linhas em `requirements.txt` (ou `requirements-dev.txt`):

```
playwright>=1.40
websocket-client>=1.6
Pillow>=10
```

### Passo 3.6 — (Opcional) Flag `--capture-baselines` pra `screenshot_match`

Modo de bootstrap pra gerar baselines pela primeira vez sem falhar:

```python
p.add_argument("--capture-baselines", action="store_true",
               help="Captura screenshots e salva como baseline (overwrites)")
```

E dentro de `check_screenshot_match`, se `args.capture_baselines`, copiar `actual` → `baseline` em vez de comparar.

### Passo 3.7 — Smoke test após patch

```bash
# Garante que parser não quebrou nada
python scripts/validate_implementation.py --phase A --json | python -m json.tool > /dev/null
echo "exit=$?"  # Esperado: 0 ou 2 (nunca 1)
```

---

## 4. Comando pra rodar Fase F

```bash
# Pré-requisito: dashboard + WS + DB UP localmente
python -m hermes_api_v2  # background, porta 8765 (ou conforme PORTS.json)

# Validar tudo de F
python scripts/validate_implementation.py --phase F

# Validar uma sub-fase específica
python scripts/validate_implementation.py --phase F.2   # apenas WS
python scripts/validate_implementation.py --phase F.6   # apenas screenshots

# Validar um finding específico
python scripts/validate_implementation.py --finding MERGED-F-030

# Output JSON pra pipeline
python scripts/validate_implementation.py --phase F --json > .claude/validation-F.json

# Reabrir tasks pros findings que falharam
python scripts/validate_implementation.py --phase F --apply-flags
```

Exit codes (inalterados):

- `0` — todos PASS
- `1` — erro interno (parser, dependência faltando)
- `2` — pelo menos 1 finding FAIL

---

## 5. Findings dummy iniciais Fase F

Anexar este bloco ao final de `.claude/VALIDATION-CHECKLIST.md` (ou criar `VALIDATION-CHECKLIST-FASE-F.md` separado e fazer o harness ler ambos via glob). Mapeamento sub-fase ↔ categoria:

| Sub-fase | Foco                          | Kinds dominantes                    |
|----------|-------------------------------|-------------------------------------|
| F.1      | UI render                     | `ui_visible`                        |
| F.2      | WS contracts                  | `ws_subscribed`                     |
| F.3      | UI↔API binding                | `endpoint_consumed`                 |
| F.4      | Regression A–E                | `regression_phase_pass`             |
| F.5      | DB tables novos               | `table_exists`, `sqlite_column`     |
| F.6      | Visual diff                   | `screenshot_match`                  |
| F.7      | Workflows                     | `workflow_exists`                   |
| F.8      | MCPs                          | `mcp_registered`                    |
| F.9      | Skills + subagents            | `skill_exists`, `subagent_exists`   |

### Bloco a colar no checklist

```markdown
## FASE F — Visual + WS + Regression + Ecosystem

### MERGED-F-001
- phase: F.1
  - ui_visible: http://localhost:8765/dashboard / #ws-health-led / LED de health WS renderiza
  - ui_visible: http://localhost:8765/dashboard / .daemon-card / Card daemon presente

### MERGED-F-002
- phase: F.1
  - ui_visible: http://localhost:8765/dashboard / #queue-counter / Contador de queue renderiza
  - ui_visible: http://localhost:8765/dashboard / .prospects-table tbody tr / Pelo menos 1 linha de prospect

### MERGED-F-010
- phase: F.2
  - ws_subscribed: ws://localhost:8765/ws/health / "service" / Health WS emite payload com service
  - ws_subscribed: ws://localhost:8765/ws/daemon / "daemon_state" / Daemon WS emite estado
  - ws_subscribed: ws://localhost:8765/ws/queue / "queue_size" / Queue WS emite tamanho

### MERGED-F-011
- phase: F.2
  - ws_subscribed: ws://localhost:8765/ws/linkedin / "li_health" / WS LinkedIn health emite

### MERGED-F-020
- phase: F.3
  - endpoint_consumed: dashboard/app.js / /api/health / Front consome /api/health
  - endpoint_consumed: dashboard/app.js / /api/prospects / Front consome lista prospects
  - endpoint_consumed: dashboard/app.js / /ws/health / Front abre WS health
  - endpoint_consumed: dashboard/app.js / /ws/daemon / Front abre WS daemon
  - endpoint_consumed: dashboard/app.js / /ws/queue / Front abre WS queue

### MERGED-F-030
- phase: F.4
  - regression_phase_pass: A /  / Fase A 100% PASS
  - regression_phase_pass: B /  / Fase B 100% PASS
  - regression_phase_pass: C /  / Fase C 100% PASS
  - regression_phase_pass: D /  / Fase D 100% PASS
  - regression_phase_pass: E /  / Fase E 100% PASS

### MERGED-F-040
- phase: F.5
  - table_exists: data/hermes.db / phase_f_audit / Tabela de auditoria Fase F
  - sqlite_column: data/hermes.db / phase_f_audit.created_at / Coluna timestamp

### MERGED-F-041
- phase: F.5
  - table_exists: ~/.hermes/hermes.db / phase_f_audit / Tabela espelhada na VM

### MERGED-F-050
- phase: F.6
  - screenshot_match: http://localhost:8765/dashboard / dashboard_idle / threshold:0.03

### MERGED-F-051
- phase: F.6
  - screenshot_match: http://localhost:8765/dashboard/prospects / prospects_list / threshold:0.05

### MERGED-F-060
- phase: F.7
  - workflow_exists: linkedin-anti-detection-sweep /  /
  - workflow_exists: hermes-bug-hunt-deep /  /
  - workflow_exists: hermes-deploy-rollback /  /

### MERGED-F-070
- phase: F.8
  - mcp_registered: agentmemory / 3111 / MCP agentmemory porta 3111
  - mcp_registered: hermes-stealth /  / MCP stealth registrado

### MERGED-F-080
- phase: F.9
  - skill_exists: hermes-bug-hunt /  /
  - skill_exists: hermes-deploy /  /
  - skill_exists: hermes-status /  /
  - skill_exists: hermes-stealth-audit /  /
  - skill_exists: hermes-li-lab /  /

### MERGED-F-090
- phase: F.9
  - subagent_exists: hermes-prospector /  /
  - subagent_exists: hermes-outreach-writer /  /
  - subagent_exists: hermes-stealth-guardian /  /
```

---

## 6. Checklist final de aplicação

- [ ] Editar regex de fase (`[A-E]` → `[A-Z]`) — passo 3.1
- [ ] Colar 10 funções `check_*` antes do bloco Runner — passo 3.2
- [ ] Expandir `CHECK_RUNNERS` com 10 entradas novas — passo 3.3
- [ ] Atualizar `--phase` help string — passo 3.4
- [ ] `pip install playwright websocket-client Pillow && python -m playwright install chromium` — passo 3.5
- [ ] (Opcional) Adicionar flag `--capture-baselines` pra screenshots — passo 3.6
- [ ] Smoke test: `python scripts/validate_implementation.py --phase A --json` retorna válido — passo 3.7
- [ ] Anexar bloco de findings F-001..F-090 ao `VALIDATION-CHECKLIST.md` — seção 5
- [ ] Gerar baselines de screenshot na primeira vez — seção 2.6
- [ ] Subir dashboard + WS local antes de rodar `--phase F`
- [ ] Rodar `python scripts/validate_implementation.py --phase F --apply-flags`
- [ ] Reabrir tasks pros findings em FLAGS via TaskCreate

---

**Fim do patch.** Atualizar este documento se novos `assert kinds` surgirem em fases G+.
