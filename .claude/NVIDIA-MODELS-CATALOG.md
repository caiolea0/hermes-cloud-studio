# NVIDIA NIM Models Catalog — Hermes Cloud Studio Shortlist

> **Status**: Catalog inicial 2026-06-11 (32 modelos shortlist Hermes-relevant)
> **Source**: [build.nvidia.com/models](https://build.nvidia.com/models) + [docs.nvidia.com/nim](https://docs.nvidia.com/nim/large-language-models/latest/function-calling.html) + memory mem_mq9usnxr
> **Cross-ref**: `.claude/NVIDIA-INTEGRATION-PLAN.md` (seção 2 resumo + seção 6 per-chapter)
> **Refresh policy**: Mensal via cron `scripts/refresh_nim_catalog.py` (F.5.9 propose) — atualiza `mcp_llm_models` table

---

## Convenções tabela

- **free_endpoint**: `Yes` = zero credit consumption (Free Endpoints tag build.nvidia.com) · `Credit` = consome do balance 1000–5000 inicial · `?` = não validado individualmente, validar build.nvidia.com modelcard
- **function_calling**: `Auto` = oficialmente auto-enabled NVIDIA docs · `Yes` = community-tested + docs · `Manual` = requer `detailed thinking off` flag · `?` = não documentado
- **latency_p50**: `TBD — F.future smoke benchmark` quando dado público NIM não disponível — não bloquear catalog por falta de número
- **ollama_equivalent**: model id Ollama equivalent owner PC rodaria caso T1 sustentar (RTX 2060 6GB limites: modelos ≤8B funcionam, 14B-32B 4-bit lento)
- **use_case_hermes**: chapter-priorizado (F.6 Brain reasoning, F.4 code-gen synth, F.7 outreach PT-BR, F.5.6 generic, F.8 classifier light)

---

## Catálogo (32 modelos shortlist)

### Tier reasoning + agentic (F.6 Brain orchestrator)

| model_id | free_endpoint | context | function_calling | streaming | use_case_hermes | latency_p50 | ollama_equivalent | notes |
|---|---|---|---|---|---|---|---|---|
| `nvidia/llama-3.3-nemotron-super-49b-v1` | Yes | 64k | Auto | Yes | **F.6 Brain reasoning + F.7 PT-BR** | TBD smoke | none (49B > RTX 2060) | **PT oficial declarado**. Derivado Llama-3.3-70B post-trained reasoning + tool calling + agentic RAG. NVIDIA primary recommended. |
| `nvidia/llama-3.1-nemotron-ultra-253b-v1` | Credit | 128k | Auto | Yes | F.6 Brain premium opt-in D3 | TBD smoke | none | Ultra reasoning, premium. Use OPT-IN per-skill (D3). |
| `deepseek-ai/deepseek-r1` | Credit | 64k | Yes¹ | Yes | F.6 Brain reasoning premium | TBD smoke | none | Reasoning ponta. Function calling community-tested. Premium credit. |
| `deepseek-ai/deepseek-v3.2` | Yes | 128k | Yes¹ | Yes | F.6 Brain general-purpose | TBD smoke | none | DeepSeek V3.2 generation, free endpoint, function calling tested. |
| `meta/llama-4-maverick-17b-128e-instruct` | Yes | 1M | Auto | Yes | F.6 + F.7 long-context dossier | TBD smoke | `llama4:17b` if added | Most popular NIM model (22M uses 2026). Llama 4 family, MoE 17B-active. |
| `meta/llama-4-scout-17b-16e-instruct` | Yes | 10M | Auto | Yes | F.6 ultra-long context | TBD smoke | none | Scout variant maior context. F.6 owner conversation summarization. |
| `mistralai/mistral-large-3-675b` | Yes | 128k | Auto | Yes | F.6 SOTA backup | TBD smoke | none | Mistral Large 3 state-of-the-art general. Free endpoint. |
| `minimax/minimax-m2.7-230b` | Yes | 200k | Yes¹ | Yes | F.6 backup + F.4 backup | TBD smoke | none | Claude-grade coding NIM tests. 230B MoE. Free endpoint. |

¹ Function calling community-tested (docs.nvidia.com forums confirm). Validar caso a caso F.5.7 smoke.

### Tier code generation (F.4 Auto-Skill synthesis)

| model_id | free_endpoint | context | function_calling | streaming | use_case_hermes | latency_p50 | ollama_equivalent | notes |
|---|---|---|---|---|---|---|---|---|
| `qwen/qwen3-coder-480b` | Yes | 256k | Yes¹ | Yes | **F.4 skill synthesis code-gen default** | TBD smoke | none | Purpose-built agentic coding. 256k context = dossier inteiro. Free endpoint. |
| `qwen/qwen3-coder-32b` | Yes | 64k | Yes¹ | Yes | F.4 lighter alternative | TBD smoke | `qwen3-coder:32b` if added | Smaller variant, fits VM melhor se F.future self-host. |
| `meta/codellama-70b-instruct` | Yes | 16k | Yes¹ | Yes | F.4 fallback | TBD smoke | `codellama:70b` (slow PC) | Code-specialized backup. Context menor. |
| `mistralai/codestral-mamba-7b` | Yes | 256k | Yes¹ | Yes | F.4 lightweight code | TBD smoke | `codestral:7b` (cabe PC!) | Mamba arch, ultra-fast inference. **Único code model viável Ollama PC**. |

### Tier classifier + lightweight (F.6 intent classifier, F.5.6 generic light)

| model_id | free_endpoint | context | function_calling | streaming | use_case_hermes | latency_p50 | ollama_equivalent | notes |
|---|---|---|---|---|---|---|---|---|
| `nvidia/llama-3.1-nemotron-nano-8b-v1.1` | Yes | 128k | Auto | Yes | **F.6 classifier substitui qwen3:8b** | TBD smoke | `qwen3:8b` (current) | Nano variant 8B, function calling auto-enabled. Direct Ollama T1 replacement candidate. |
| `nvidia/llama-3.1-nemotron-nano-4b-v1.1` | Yes | 128k | Auto | Yes | F.6 ultra-light classifier | TBD smoke | `qwen2.5:3b` (current) | 4B classifier. Substitui qwen2.5:3b classifier daemon F.7 stop gates. |
| `zhipu/glm-4` | Yes | 128k | Yes¹ | Yes | F.6 reasoning lightweight | TBD smoke | none | GLM-4 Zhipu free endpoint. Reasoning + multilingual. |
| `zhipu/glm-4.7` | Yes | 128k | Yes¹ | Yes | F.6 reasoning updated | TBD smoke | none | GLM-4.7 newer variant, function calling tested. |
| `google/gemma-4-27b-it` | Yes | 8k | Yes¹ | Yes | F.6 lightweight classifier | TBD smoke | `gemma3:4b` (current) | Gemma 4 27B Google. Context limitado 8k, OK classifier. |
| `google/gemma-4-9b-it` | Yes | 8k | Yes¹ | Yes | F.6 lighter classifier | TBD smoke | `gemma3:4b` similar | 9B variant. PC Ollama equivalent. |

### Tier creative + multilingual (F.7 outreach PT-BR cobaia)

| model_id | free_endpoint | context | function_calling | streaming | use_case_hermes | latency_p50 | ollama_equivalent | notes |
|---|---|---|---|---|---|---|---|---|
| `nvidia/llama-3.3-nemotron-super-49b-v1` | Yes | 64k | Auto | Yes | **F.7 PT-BR primary** (same row reasoning) | TBD smoke | none | Repeat: PT oficial declarado. F.7 A/B test obrigatório vs Ollama qwen3:8b local primeira semana. |
| `meta/llama-3.3-70b-instruct` | Yes | 128k | Auto | Yes | F.7 PT-BR backup | TBD smoke | none | Llama 3.3 base, multilingual (PT testado community). Function calling auto-enabled. |
| `meta/llama-3.1-405b-instruct` | Yes | 128k | Auto | Yes | F.7 PT-BR premium | TBD smoke | none | 405B flagship, PT competent. Função calling official. |
| `mistralai/mistral-large-2-2411` | Yes | 128k | Auto | Yes | F.7 PT-BR fluent | TBD smoke | none | Mistral Large 2 2411 release. Multilingual native. |
| `mistralai/mixtral-8x22b-instruct` | Yes | 64k | Auto | Yes | F.7 PT-BR alt | TBD smoke | none | Mixtral MoE 22B-active. Multilingual. |

### Tier summarization + long context (F.7 cobaia dossier, F.6 chat memory)

| model_id | free_endpoint | context | function_calling | streaming | use_case_hermes | latency_p50 | ollama_equivalent | notes |
|---|---|---|---|---|---|---|---|---|
| `meta/llama-4-scout-17b-16e-instruct` | Yes | **10M** | Auto | Yes | **F.6 long-context primary** | TBD smoke | none | 10M context recordista F.6 chat session + cobaia history. |
| `google/gemini-pro-mod-summary-128k` | ? | 128k | ? | Yes | F.6 summarization | TBD smoke | none | Validate exact model_id build.nvidia.com — placeholder name. |
| `meta/llama-3.1-70b-instruct` | Yes | 128k | Auto | Yes | F.7 dossier reading | TBD smoke | none | Llama 3.1 70B standard. Long context + function calling. |

### Tier embeddings (F.6 memory + F.7 prospect matching)

| model_id | free_endpoint | context | function_calling | streaming | use_case_hermes | latency_p50 | ollama_equivalent | notes |
|---|---|---|---|---|---|---|---|---|
| `nvidia/nv-embedqa-e5-v5` | Yes | 512 | N/A | N/A | F.6 memory retrieval + F.7 prospect matching | TBD smoke | `nomic-embed-text` (current) | NVIDIA embedding flagship. Replacement Ollama nomic-embed-text? Validate dim compatibility. |
| `nvidia/nv-embedqa-mistral-7b-v2` | Yes | 4k | N/A | N/A | F.6 long-doc embedding | TBD smoke | none | 4k context embedding. F.7 long prospect bio matching. |
| `nvidia/llama-3.2-nv-embedqa-1b-v2` | Yes | 8k | N/A | N/A | F.6 lightweight embedding | TBD smoke | none | 1B Llama 3.2-based embedding. Quick. |

### Tier specialty (Kimi, MiniMax, GLM-5)

| model_id | free_endpoint | context | function_calling | streaming | use_case_hermes | latency_p50 | ollama_equivalent | notes |
|---|---|---|---|---|---|---|---|---|
| `moonshotai/kimi-k2.6` | Yes | 200k | Yes¹ | Yes | F.6 reasoning alt | TBD smoke | none | Kimi K2.6 reasoning, function calling community-tested. |
| `zhipu/glm-5.1` | Yes | 200k | Yes¹ | Yes | F.6 reasoning newer | TBD smoke | none | GLM-5.1 newest Zhipu, advanced reasoning. |

---

## Use-case → Recommended model decision matrix

| Use-case | Primary (T2 NIM Free default) | Backup T2 | Premium T3 opt-in | Local T1 Ollama equivalent |
|---|---|---|---|---|
| **F.6 Brain reasoning + intent classify** | `nvidia/llama-3.3-nemotron-super-49b-v1` | `mistralai/mistral-large-3-675b` | `nvidia/llama-3.1-nemotron-ultra-253b-v1` | `qwen3:8b` (existing) |
| **F.6 intent classifier light** | `nvidia/llama-3.1-nemotron-nano-8b-v1.1` | `zhipu/glm-4` | — | `qwen2.5:3b` (existing) |
| **F.4 skill synthesis code-gen** | `qwen/qwen3-coder-480b` | `minimax/minimax-m2.7-230b` | `deepseek-ai/deepseek-r1` | `codestral:7b` (cabe RTX 2060) |
| **F.7 outreach PT-BR creative** | `nvidia/llama-3.3-nemotron-super-49b-v1` | `meta/llama-3.3-70b-instruct` | `meta/llama-3.1-405b-instruct` | `qwen3:8b` (existing) |
| **F.6 long-context chat memory** | `meta/llama-4-scout-17b-16e-instruct` | `meta/llama-4-maverick-17b-128e-instruct` | — | none |
| **F.6/F.7 embeddings retrieval** | `nvidia/nv-embedqa-e5-v5` | `nvidia/llama-3.2-nv-embedqa-1b-v2` | — | `nomic-embed-text` (existing) |
| **F.5.6/F.8 generic light** | `zhipu/glm-4` | `google/gemma-4-9b-it` | — | `gemma3:4b` (existing) |
| **F.4 code-gen lightweight** | `mistralai/codestral-mamba-7b` | `qwen/qwen3-coder-32b` | — | `codestral:7b` |

---

## Validations pendentes (F.5.7 implementação real)

1. **Free Endpoint tag confirmation per model_id**: build.nvidia.com modelcard cada modelo lista "Free Endpoint" badge OU credit consumption rate. Esta tabela assume baseado web search agregado — validar individual antes hard-coded `mcp_llm_models.free_endpoint`.

2. **Function calling per model_id real test**: NVIDIA docs declaram Auto pra Llama 3.x/Mistral/Nemotron. Community-tested DeepSeek/GLM/Qwen3/Kimi. F.5.7 smoke test invoca cada modelo com tool_choice="auto" + tool schema simples (`get_current_time`) — pass/fail registrado em catalog.

3. **PT-BR quality benchmark**: NVIDIA NÃO publica BR-PT específico. F.7 A/B test obrigatório (seção 6.4 PLAN). Skill scoring rubric: gramática + tom natural + persona Cuiabá + CTA appropriate. Owner avalia 100 outputs/provider primeira semana cobaia.

4. **Latency p50 measurement**: TBD em todas rows. F.5.7 ou F.6 inicial deploy mede:
   - `route(task_type, model_hint, prompt)` por 50 samples
   - Calcula p50/p95/p99 latency_ms por (provider, model)
   - Update `mcp_llm_models` row OR JSON sidecar `.claude/audits/nim-latency-{YYYY-MM}.json`

5. **Context window effective vs documented**: declarados context windows são "max", efetivo throughput pode degradar > 50% tokens (Llama 4 1M context — não vai chegar real-use, mas validate F.6 chat session limits).

6. **Embedding dimension compatibility**: `nv-embedqa-e5-v5` vs `nomic-embed-text` (Ollama atual) — dims iguais? Mismatch força reindex agentmemory MCP. Validate ANTES F.5.7 declarar embedding tier T2 default.

---

## Modelos EXCLUÍDOS catalog (decisão deliberada)

- **Vision/multimodal models** (Llama Vision, Pixtral, Cosmos): F.5.7 escopo é text-only. F.future considerar pra cobaia screenshot analysis F.3 lab.
- **Modelos < 4B parâmetros não-NVIDIA**: irrelevantes vs Ollama qwen2.5:3b local (latency T1 < T2 cloud trip sempre).
- **Modelos credit-only sem free counterpart**: incluídos apenas como Premium T3 opt-in (DeepSeek R1, Nemotron Ultra). Outros credit-only descartados — owner zero-paid-pref forte.
- **Modelos com função calling unsupported documentado**: irrelevantes F.6 Brain dispatch (precisa tool calling). Lista validar F.5.7 smoke.

---

**Refresh next**: 2026-07-15 (cron mensal F.5.9 proposal alinhado audit dia 15 pattern F.5.5).
