-- F.5.7 — mcp_calls extension (cost tracking multi-provider) + mcp_llm_models catalog + nim_credit_history
-- Cross-ref: .claude/NVIDIA-MODELS-ROUTING-MATRIX.md §5 + .claude/NVIDIA-INTEGRATION-PLAN.md §5.1
-- Pattern: idempotente IF NOT EXISTS + ALTER TABLE ADD COLUMN (SQLite gracefully handles duplicates via error catch nas migrations runner).
-- Apply VM: sqlite3 ~/.hermes/data/command_center.db < migrations/2026_06_mcp_llm_extension.sql
-- Apply PC: sqlite3 hermes_local.db < migrations/2026_06_mcp_llm_extension.sql

-- 1) Extend mcp_calls — 5 colunas extras pra cost tracking per provider
-- SQLite NÃO suporta ADD COLUMN IF NOT EXISTS — runner deve catch duplicate column error.
ALTER TABLE mcp_calls ADD COLUMN provider TEXT;        -- 'nim_free' | 'nim_credit' | 'ollama_pc' | 'openrouter'
ALTER TABLE mcp_calls ADD COLUMN model TEXT;           -- exact model_id e.g. 'nvidia/llama-3.3-nemotron-super-49b-v1'
ALTER TABLE mcp_calls ADD COLUMN tokens_in INTEGER;    -- prompt tokens
ALTER TABLE mcp_calls ADD COLUMN tokens_out INTEGER;   -- completion tokens
ALTER TABLE mcp_calls ADD COLUMN cost_credits REAL;    -- NIM credits consumed (0.0 free / X.X credit-based)

CREATE INDEX IF NOT EXISTS idx_mcp_calls_provider ON mcp_calls(provider);
CREATE INDEX IF NOT EXISTS idx_mcp_calls_model ON mcp_calls(model);

-- 2) Catalog NIM models — mirror routing_matrix config.yaml + capability tags
CREATE TABLE IF NOT EXISTS mcp_llm_models (
    model_id           TEXT PRIMARY KEY,                 -- e.g. 'nvidia/mistral-nemotron'
    provider           TEXT NOT NULL,                    -- 'nim_free' | 'nim_credit' | 'ollama_pc' | 'openrouter'
    free_endpoint      INTEGER DEFAULT 0,                -- bool: 1 = zero credit consumption
    context_window     INTEGER,                          -- tokens (e.g. 128000, 1000000)
    function_calling   INTEGER DEFAULT 0,                -- bool: native FC support
    streaming          INTEGER DEFAULT 0,                -- bool
    json_mode          INTEGER DEFAULT 0,                -- bool: structured output
    ptbr_official      INTEGER DEFAULT 0,                -- bool: PT-BR officially declared
    capabilities       TEXT,                             -- JSON array tags: ['reasoning','code','vision','embeddings']
    latency_p50_ms     INTEGER,                          -- F.5.7 deploy mede (NULL inicial)
    deprecated_at      TIMESTAMP,                        -- NULL = active
    last_refresh_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mcp_llm_models_provider ON mcp_llm_models(provider);
CREATE INDEX IF NOT EXISTS idx_mcp_llm_models_active ON mcp_llm_models(deprecated_at);

-- Seed primeiros 12 modelos canonical NVIDIA-MODELS-ROUTING-MATRIX.md §4 (subset)
INSERT OR REPLACE INTO mcp_llm_models (model_id, provider, free_endpoint, context_window, function_calling, streaming, ptbr_official, capabilities) VALUES
  ('nvidia/mistral-nemotron',                       'nim_free',   1, 128000,  1, 1, 0, '["reasoning","tool_use","best_at_any_price"]'),
  ('nvidia/llama-3.3-nemotron-super-49b-v1',        'nim_free',   1, 64000,   1, 1, 1, '["reasoning","tool_use","ptbr_official","creative"]'),
  ('nvidia/llama-3.1-nemotron-nano-8b-v1.1',        'nim_free',   1, 128000,  1, 1, 0, '["classifier","tool_use","fast"]'),
  ('nvidia/llama-3.1-nemotron-nano-4b-v1.1',        'nim_free',   1, 128000,  1, 1, 0, '["classifier_light","tool_use","ultra_fast"]'),
  ('meta/llama-4-scout-17b-16e-instruct',           'nim_free',   1, 10000000,1, 1, 0, '["long_context","summarize","reasoning"]'),
  ('meta/llama-4-maverick-17b-128e-instruct',       'nim_free',   1, 1000000, 1, 1, 0, '["long_context","reasoning","tool_use"]'),
  ('qwen/qwen3-coder-480b',                         'nim_free',   1, 256000,  1, 1, 0, '["code_gen","agentic","tool_use"]'),
  ('mistralai/codestral-mamba-7b',                  'nim_free',   1, 256000,  1, 1, 0, '["code_gen","mamba","ultra_fast"]'),
  ('deepseek-ai/deepseek-r1',                       'nim_credit', 0, 64000,   1, 1, 0, '["reasoning_premium","tool_use"]'),
  ('zhipu/glm-5.1',                                 'nim_free',   1, 200000,  1, 1, 0, '["reasoning","multilingual","generic"]'),
  ('nvidia/nv-embedqa-e5-v5',                       'nim_free',   1, 512,     0, 0, 0, '["embedding"]'),
  ('llama3.2:3b',                                   'ollama_pc',  1, 8192,    1, 1, 0, '["classifier","fast_local","ptbr_ok"]'),
  ('phi3:3.8b',                                     'ollama_pc',  1, 8192,    1, 1, 0, '["brain_dispatch","function_calling","local"]'),
  ('qwen2.5-coder:1.5b',                            'ollama_pc',  1, 8192,    1, 1, 0, '["code_gen_light","ultra_fast_local"]'),
  ('qwen2.5-coder:3b',                              'ollama_pc',  1, 8192,    1, 1, 0, '["code_gen","quality_local"]'),
  ('nomic-embed-text',                              'ollama_pc',  1, 2048,    0, 0, 0, '["embedding","no_gpu"]');

-- 3) NIM credit balance history — F.5.9 cron daily 09h BRT polling
CREATE TABLE IF NOT EXISTS nim_credit_history (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    balance_credits          REAL NOT NULL,             -- credits remaining
    free_rpm_window_count    INTEGER,                   -- 40 RPM cap usage current window
    recorded_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source                   TEXT DEFAULT 'cron_daily'  -- 'cron_daily' | 'manual_check' | 'auto_disable_trigger'
);

CREATE INDEX IF NOT EXISTS idx_nim_credit_history_recorded_at ON nim_credit_history(recorded_at DESC);
