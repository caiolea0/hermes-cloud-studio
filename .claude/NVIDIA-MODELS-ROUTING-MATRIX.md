# NVIDIA NIM + Ollama Routing Matrix — Hermes Cloud Studio

> **Status**: Auditoria completa 2026-06-11 (corrige catalog Sessão B com gaps + deprecations + Ollama RTX 2060 sweet spot)
> **Source**: WebSearch atual build.nvidia.com 2026 + Ollama benchmark RTX 2060 6GB (databasemart + morphllm + sitepoint + localaimaster)
> **Cross-ref**: `.claude/NVIDIA-MODELS-CATALOG.md` (32 shortlist Sessão B) + `.claude/NVIDIA-INTEGRATION-PLAN.md` (architecture 4-tier)
> **Aplicação**: F.5.7 hermes-llm MCP implementação real consome esta matrix como ground truth routing decisions

---

## 0. Sumário executivo

**Topologia 3-tier fallback eficiente** (owner-imposed: T1 cloud primary → T2 cloud premium → T3 PC local até migração VM GPU futura):

```
Skill request → hermes-llm.route(task_type, prompt)
  ↓
T1: NIM Free Endpoint (cloud, $0, 40 RPM cap)        ← primary
  ↓ fallback if: 429 rate limit / 5xx / timeout >max_latency_ms / 401 auth fail
T2: NIM credit-based premium (cloud, 5000 credits)   ← OPT-IN per-skill via YAML
  ↓ fallback if: balance esgotado / model unavailable / timeout
T3: Ollama PC local RTX 2060 6GB (offline-safe, lento)  ← final fallback (até VM GPU F.future)
  ↓ fallback if: PC offline / model not loaded / VRAM OOM
T4: OpenRouter (existente, paid)                     ← último recurso explicit owner override only
```

**Decisão arquitetural inviolável**: T3 Ollama PC local = **sempre disponível offline** garantindo Hermes nunca trava se NIM cap/down. Owner upgrade VM GCP GPU (e2-standard → g2-standard com L4) é F.future decision pós-F.7 cobaia validar use-case.

**Rate limit caveat global**: NIM Free 40 RPM hard cap aplicado por API key. Brain F.6 chain calls (e.g., reasoning → classify → outreach gen) consome 3-5 RPM/skill_run. Capacidade estimada: ~8-13 skill_runs/min sustained antes 429.

---

## 1. Tasks Hermes mapeadas (12 tasks)

Por chapter:

| # | Task | Chapter | Frequência |
|---|---|---|---|
| 1 | Brain reasoning + intent decide | F.6 | Alta (cada chat msg owner) |
| 2 | Brain intent classifier light | F.6 daemon | Muito alta (cada 30s ping cobaia state) |
| 3 | Skill synthesis code-gen | F.4 | Baixa (semanal owner-trigger) |
| 4 | Skill synthesis code-gen lightweight | F.4 | Baixa |
| 5 | LinkedIn outreach generation PT-BR | F.7 | Média (8-15/dia cobaia daily caps) |
| 6 | LinkedIn message reply suggestion PT-BR | F.7 | Baixa (owner inbox triage) |
| 7 | Long-context chat memory summarization | F.6 + F.7 | Média (session boundary) |
| 8 | Embeddings retrieval (prospect matching) | F.6 + F.7 | Alta (cada prospect scoring) |
| 9 | Generic light text (tags + extract) | F.5.6 + F.8 | Baixa |
| 10 | Document/CSV summarization | F.7 dossier read | Baixa |
| 11 | OCR + vision (screenshot analysis) | F.future F.3 lab evolve | Muito baixa (F.future) |
| 12 | Speech-to-text (owner voice commands) | F.future | Muito baixa (F.future) |

---

## 2. Catalog NIM 2026 — Corrigido (gaps + deprecations)

### 2.1 NOVOS modelos faltando catalog Sessão B (adicionar F.5.7)

| model_id | tier | context | function_calling | use_case Hermes priority | source |
|---|---|---|---|---|---|
| `deepseek-ai/deepseek-v4-flash` | Free Endpoint? | **1M tokens** | Yes | F.4 code-gen ultra-fast + F.6 long-context | NIM 2026 catalog (284B MoE) |
| `nvidia/mistral-nemotron` | Free Endpoint? | 128k | **Auto (NVIDIA "best at any price")** | F.6 Brain orchestrator PRIMARY candidate | NIM official declaration |
| `nvidia/llama-3.1-nemotron-ultra-550b-v1` | **Credit** | 128k | Auto | F.6 premium D3 opt-in (flagship) | NVIDIA 2026 release |
| `nvidia/nemotron-3-nano-omni` | Free? | 128k | Auto | F.future omnimodal cobaia screenshot analysis | NVIDIA omnimodal release |

### 2.2 Modelos catalog Sessão B com status DEPRECATED 2026

| model_id catalog | Status 2026 | Ação F.5.7 implementação |
|---|---|---|
| `moonshotai/kimi-k2.6` | K2 Instruct/Thinking deprecated, K2.6 incerto | **Validar build.nvidia.com modelcard** antes hard-code; substituir `deepseek-ai/deepseek-v4-flash` |
| `zhipu/glm-4.7` | **DEPRECATED** confirmado | Substituir `zhipu/glm-5.1` (já no catalog) — F.5.7 não inclui glm-4.7 |
| `google/gemma-4-27b-it` | Validar exact ID Gemma 4 vs Gemma 3 27B deprecated | Confirmar build.nvidia.com cardlist 2026 |

### 2.3 Catalog Sessão B confirmado ativos (sem mudança)

Outras 28 rows do `NVIDIA-MODELS-CATALOG.md` (Nemotron Super 49B, Nano 8B/4B, DeepSeek R1/V3.2, Llama 4 Maverick/Scout, Mistral Large 3, MiniMax M2.7, GLM-4, Qwen3 Coder 480B/32B, Codestral Mamba, Llama 3.x family, embeddings nv-embedqa-*) — todas confirmadas ativas WebSearch 2026.

---

## 3. Ollama RTX 2060 6GB — sweet spot real (corrige catalog)

WebSearch revela performance real benchmark RTX 2060 6GB:

| model | tok/s | VRAM | Function calling | Use Hermes |
|---|---|---|---|---|
| `llama3.2:3b` | **50.41 (fastest)** | 60% | Native JSON mode | **Classifier intent primary T3** |
| `qwen2.5:3b` | 36.02 | 65% | Yes | Classifier light backup |
| `phi3:3.8b` | ~40 | 70% | **Native function calling + JSON** | **F.6 Brain dispatch T3** (tool calling local) |
| `gemma3:4b` | ~30 | 75% | Limited | Light text gen |
| `qwen2.5-coder:1.5b` | 60+ | 50% | Yes | F.4 code-gen lightweight ultra-fast |
| `qwen2.5-coder:3b` | 35 | 70% | Yes | F.4 code-gen better quality |
| `nomic-embed-text` | 200+ (no GPU) | <100MB | N/A | Embeddings (atual) — manter |
| `llama3.1:8b` | 7-9 (slow) | 80% | Yes | **EVITAR — tight, lento** |
| `qwen3:8b` (atual) | 7-9 (slow) | 80% | Yes | **MIGRAR PARA llama3.2:3b** |
| `codestral:7b` | 12-15 | 85% | Yes | F.4 backup só (slow) |

### Recomendação Ollama PC RTX 2060 stack final (T3 fallback)

Owner deve `ollama pull` estes modelos (substitui setup atual):

```bash
# Stack recomendado T3 RTX 2060 6GB (FASTEST per task)
ollama pull llama3.2:3b               # 50 tok/s — intent classifier primary
ollama pull phi3:3.8b                 # native function calling — Brain dispatch local
ollama pull qwen2.5:3b                # classifier light backup
ollama pull qwen2.5-coder:1.5b        # code-gen ultra-fast 60+ tok/s
ollama pull qwen2.5-coder:3b          # code-gen better quality (slower)
ollama pull gemma3:4b                 # light text gen (mantém atual)
ollama pull nomic-embed-text          # embeddings (mantém atual)

# DEPRECAR (lento RTX 2060):
# ollama rm qwen3:8b      # 7-9 tok/s tight VRAM
# ollama rm llama3.1:8b   # similar issue
```

**Trade-off documentado**: T3 Ollama tem qualidade reasoning inferior a NIM Free Nemotron Super 49B. Aceitável porque T3 é fallback emergency (offline-safe), NÃO primary. Owner upgrade VM GPU F.future remove esta restrição.

---

## 4. Routing Matrix 3-tier per task (PRINCIPAL DELIVERABLE)

### 4.1 Task 1 — Brain reasoning + intent decide (F.6)

| Tier | Provider | Model | Free? | Context | FC | Trigger fallback |
|---|---|---|---|---|---|---|
| **T1** primary | NIM | `nvidia/mistral-nemotron` | Yes¹ | 128k | Auto | 429/5xx/timeout>30s/auth fail |
| **T2** backup | NIM | `nvidia/llama-3.3-nemotron-super-49b-v1` | Yes | 64k | Auto | T1 fallback OR PT-BR explicit (Super 49B PT oficial) |
| **T3** premium opt-in | NIM | `deepseek-ai/deepseek-r1` | Credit | 64k | Yes | Owner skill YAML `force_provider: nim-credit` D3 |
| **T4** local fallback | Ollama PC | `phi3:3.8b` | Free local | 8k | **Native** | T1+T2+T3 falhar OR NIM cap atingido |

¹ Mistral Nemotron status free endpoint validar build.nvidia.com modelcard F.5.7 smoke (NIM declara "best function calling any price" sem clarificar paywall).

### 4.2 Task 2 — Intent classifier light daemon (F.6 ping 30s)

Alta frequência, latency-sensitive (<2s ideal):

| Tier | Provider | Model | Free? | Trigger fallback |
|---|---|---|---|---|
| **T1** primary | NIM | `nvidia/llama-3.1-nemotron-nano-8b-v1.1` | Yes | 429/5xx/timeout>5s |
| **T2** backup | NIM | `nvidia/llama-3.1-nemotron-nano-4b-v1.1` | Yes | T1 fallback |
| **T3** local | Ollama PC | `llama3.2:3b` | Free local | NIM cap (FASTEST 50 tok/s) |

### 4.3 Task 3 — Skill synthesis code-gen pesado (F.4 owner-trigger)

Latency-tolerant (>30s OK), quality-critical:

| Tier | Provider | Model | Free? | Context | Trigger fallback |
|---|---|---|---|---|---|
| **T1** primary | NIM | `qwen/qwen3-coder-480b` | Yes | 256k | 429/5xx/timeout>60s |
| **T2** backup | NIM | `deepseek-ai/deepseek-v4-flash` | Yes¹ | **1M** | T1 fallback OR ultra-long context |
| **T3** premium | NIM | `minimax/minimax-m2.7-230b` | Yes | 200k | OPT-IN owner skill YAML |
| **T4** local fallback | Ollama PC | `qwen2.5-coder:3b` | Free local | 8k | NIM cap |

¹ DeepSeek V4 Flash status free validar — alternative `mistralai/codestral-mamba-7b` (free, Mamba arch ultra-fast).

### 4.4 Task 4 — Skill synthesis code-gen lightweight (F.4 simple skills)

| Tier | Provider | Model | Free? | Trigger fallback |
|---|---|---|---|---|
| **T1** | NIM | `mistralai/codestral-mamba-7b` | Yes | 429/5xx/timeout>20s |
| **T2** | NIM | `qwen/qwen3-coder-32b` | Yes | T1 fallback |
| **T3** local | Ollama PC | `qwen2.5-coder:1.5b` | Free local | NIM cap (60+ tok/s) |

### 4.5 Task 5 — LinkedIn outreach generation PT-BR (F.7 cobaia)

**CRÍTICO**: reply rate cobaia depende qualidade PT-BR. A/B test obrigatório primeira semana.

| Tier | Provider | Model | PT-BR? | Trigger fallback |
|---|---|---|---|---|
| **T1** primary | NIM | `nvidia/llama-3.3-nemotron-super-49b-v1` | **PT oficial declarado** | 429/5xx/timeout>15s |
| **T2** backup | NIM | `meta/llama-3.3-70b-instruct` | Multilingual tested | T1 fallback |
| **T3** premium | NIM | `meta/llama-3.1-405b-instruct` | PT competent | OPT-IN se reply rate T1<T2 baseline |
| **T4** local fallback | Ollama PC | `llama3.2:3b` | OK PT mas limited reasoning | NIM cap (NÃO qwen3:8b lento) |

A/B test logging: `cobaia_daily_metrics.reply_rate_by_provider` JSON `{nim_super_49b: X%, nim_llama_70b: Y%, ollama_llama32_3b: Z%}` segmentation primeira semana.

### 4.6 Task 6 — LinkedIn reply suggestion PT-BR (F.7 inbox triage)

Mesmo stack Task 5 (mesma natureza), latency tolerant maior (>20s OK owner-reactive não real-time).

### 4.7 Task 7 — Long-context summarization (F.6 chat memory + F.7 dossier)

| Tier | Provider | Model | Context | Trigger fallback |
|---|---|---|---|---|
| **T1** primary | NIM | `meta/llama-4-scout-17b-16e-instruct` | **10M** | 429/5xx/timeout>45s |
| **T2** backup | NIM | `meta/llama-4-maverick-17b-128e-instruct` | 1M | T1 fallback |
| **T3** backup | NIM | `deepseek-ai/deepseek-v4-flash` | 1M | If T1+T2 down |
| **T4** local fallback | Ollama PC | `gemma3:4b` (8k context) | 8k | Truncate prompt + summarize chunked NIM cap |

### 4.8 Task 8 — Embeddings retrieval (F.6 + F.7 high freq)

Validar dim compatibility **OBRIGATÓRIO** antes substituir.

| Tier | Provider | Model | Dim | Trigger fallback |
|---|---|---|---|---|
| **T1** primary | NIM | `nvidia/nv-embedqa-e5-v5` | 1024 (validar) | 429/5xx/timeout>3s |
| **T2** backup | NIM | `nvidia/llama-3.2-nv-embedqa-1b-v2` | 2048 (validar) | T1 fallback OR long-doc |
| **T3** local | Ollama PC | `nomic-embed-text` | 768 (atual) | NIM cap (sem GPU consumption) |

**Caveat dim mismatch**: NIM dims ≠ nomic-embed-text 768 → reindex `agentmemory` MCP obrigatório se T1/T2 ativados. F.5.7 validation step: smoke compare cosine similarity 10 same-prompt embeddings T1 vs T3 → se < 0.85 reindex full.

### 4.9 Task 9 — Generic light text (F.5.6 + F.8 tags/extract)

| Tier | Provider | Model | Trigger fallback |
|---|---|---|---|
| **T1** | NIM | `zhipu/glm-5.1` (substitui glm-4.7 deprecated) | 429/5xx |
| **T2** | NIM | `google/gemma-4-9b-it` (validar ID) | T1 fallback |
| **T3** local | Ollama PC | `gemma3:4b` | NIM cap |

### 4.10 Task 10 — Document/CSV summarization (F.7 dossier read)

Mesma stack Task 7 (long-context summarization).

### 4.11 Task 11 — OCR + vision F.future

| Tier | Provider | Model | F.future status |
|---|---|---|---|
| **T1** | NIM | `nvidia/nemotron-3-nano-omni` (omnimodal) | F.future cobaia screenshot |
| **T2** | NIM | Llama Vision family validar build.nvidia.com | F.future backup |
| **T3** local | Ollama PC | `llava-phi3:3.8b` (multimodal compact) | F.future (defer install) |

### 4.12 Task 12 — Speech-to-text F.future

| Tier | Provider | Model |
|---|---|---|
| **T1** | NIM | `openai/whisper-large-v3` (NIM hosts via Riva) |
| **T3** local | Whisper.cpp PC (não Ollama) | F.future install |

---

## 5. Failure + cap detection logic

### 5.1 Per-call failure triggers (fallback automático T1→T2→T3)

```python
# Pseudo-código pra hermes-llm/_policy.py F.5.7 implementação real

FALLBACK_TRIGGERS = {
    "rate_limit": lambda r: r.status_code == 429,
    "server_error": lambda r: 500 <= r.status_code < 600,
    "timeout": lambda r: isinstance(r, asyncio.TimeoutError),
    "auth_fail": lambda r: r.status_code in (401, 403),
    "empty_response": lambda r: not r.text or len(r.text) < 10,
    "model_unavailable": lambda r: "model_not_found" in str(r.text).lower(),
}

ABORT_TRIGGERS_NO_FALLBACK = {
    "client_error": lambda r: r.status_code == 400,  # malformed prompt
    "force_provider_set": lambda call: call.force_provider != "",
    "explicit_no_fallback": lambda call: call.no_fallback is True,
}
```

### 5.2 Cap detection (RPM 40 NIM Free)

```python
# Sliding window 60s tracking calls timestamps per API key
class RpmLimiter:
    WINDOW_SECONDS = 60
    MAX_RPM_NIM_FREE = 38   # margin 2 sobre 40 cap NIM declared

    async def can_proceed(self) -> bool:
        now = time.monotonic()
        # Drop timestamps > 60s old
        self.calls = [t for t in self.calls if now - t < self.WINDOW_SECONDS]
        if len(self.calls) < self.MAX_RPM_NIM_FREE:
            self.calls.append(now)
            return True
        # Cap atingido — fallback T3 immediate (NÃO queue 60s)
        return False
```

### 5.3 Health check periódico T1/T2/T3 status

Endpoint `get_provider_status()` (hermes-llm tool 3 catalog Sessão B):

```python
async def get_provider_status() -> dict:
    """Health 3 providers paralelo timeout 2s each."""
    results = await asyncio.gather(
        _ping_ollama_pc(),     # T3 local PC :11434
        _ping_nim_free(),       # T1 NIM /v1/models
        _ping_nim_credit(),     # T2 NIM credit balance check
        return_exceptions=True,
    )
    return {
        "ollama_pc": {"up": not isinstance(results[0], Exception), "latency_ms": ...},
        "nim_free": {"up": ..., "rpm_remaining": MAX_RPM - len(self.calls)},
        "nim_credit": {"up": ..., "balance_remaining": ...},
    }
```

### 5.4 Premium credit balance monitoring (D3 OPT-IN)

Cron daily 09h BRT (alinhar F.5.5 audit dia 15 pattern):
- GET `https://integrate.api.nvidia.com/v1/account/credits`
- INSERT `nim_credit_history` table row
- Alert thresholds:
  - balance < 1000 → toast dashboard + Sentry log
  - balance < 200 → Telegram notification owner
  - balance < 50 → AUTO disable T2 routing temporariamente até refill

---

## 6. Validações pendentes F.5.7 smoke

1. **Free Endpoint badge confirmation** per modelo NEW seção 2.1 (`deepseek-v4-flash`, `mistral-nemotron`, `nemotron-3-ultra-550b`, `nemotron-3-nano-omni`) — build.nvidia.com modelcard
2. **Function calling real test** cada T1/T2 modelo: invoke `get_current_time` tool simple → pass/fail registrado `mcp_llm_models` table
3. **PT-BR A/B test obrigatório** F.7 cobaia primeira semana: 100 outreach NIM Super 49B vs 100 NIM Llama 3.3 70B vs 100 Ollama llama3.2:3b → reply_rate_by_provider segmentation
4. **Embedding dim compat** Task 8: smoke 10 same-prompt cosine similarity T1 vs T3 — se < 0.85 reindex agentmemory full
5. **Latency p50 baseline** per (tier, task) — Run 50 samples F.5.7 deploy → update `mcp_llm_models.latency_p50_ms`
6. **NIM credit balance endpoint exact** — F.5.7 implementação confirma URL real (assumido `/v1/account/credits`, pode ser diferente)
7. **Mistral Nemotron paywall status** — NIM declara "best function calling at any price" sem clarificar free vs credit
8. **Kimi K2.6 deprecation** check — incerto, validar build.nvidia.com OR remove catalog

---

## 7. Gap analysis catalog Sessão B → matriz final

| Item | Catalog Sessão B | Esta matrix | Action F.5.7 |
|---|---|---|---|
| Total modelos shortlist | 32 | 36 (+4 novos) | Append catalog rows |
| Deprecated incluídos | glm-4.7 + Kimi K2.6 (incerto) | Removidos/substituídos | Update catalog rows |
| Ollama RTX 2060 modelos | qwen3:8b (lento) primary | `llama3.2:3b` primary | `ollama pull` stack §3 |
| 3-tier explicit por task | Decision matrix simples | 12 tasks × 3-4 tiers | Hard-code `hermes-llm/config.yaml` |
| Failure detection logic | Mencionado abstract | Pseudo-código pronto | Implement F.5.7 `_policy.py` |
| Cap RPM 40 handling | Não explicit | RpmLimiter classe | Implement F.5.7 `_adapters.py` |
| Credit polling | Cron daily mencionado | Endpoint + thresholds explicit | F.5.9 cron implement |
| PT-BR A/B test | Mencionado seção 6.4 PLAN | Procedure explícito Task 5 | F.7 implementation gate |

---

## 8. Cross-refs

- `.claude/NVIDIA-INTEGRATION-PLAN.md` — architecture 4-tier (T4 OpenRouter mantém como último recurso owner-explicit)
- `.claude/NVIDIA-MODELS-CATALOG.md` — base 32 shortlist (esta matrix corrige + amplia)
- `.claude/PLAN.md` — F.5.6 ✅ CLOSED + F.5.7 NOVA proposta (esta matrix consumida)
- `mem_mq9usnxr` — NIM descobertas pesquisa orquestrador
- WebSearch sources:
  - [aitoolsmentor 46 free models 2026](https://www.aitoolsmentor.com/blog/free-ai-models-nvidia-nim-complete-guide-2026)
  - [build.nvidia.com/models](https://build.nvidia.com/models) live catalog
  - [databasemart RTX 2060 Ollama benchmark](https://www.databasemart.com/blog/ollama-gpu-benchmark-rtx2060)
  - [localaimaster best Ollama 2026](https://localaimaster.com/blog/best-ollama-models)
  - [morphllm 12 models ranked](https://www.morphllm.com/best-ollama-models)

---

**Status**: Routing matrix COMPLETE pronta consumo F.5.7. Owner orquestrador (você) cristaliza F.5.7 decisões D1-D6 → prompt sessão dedicada → owner Claude implementação real consome esta matrix como ground truth.
