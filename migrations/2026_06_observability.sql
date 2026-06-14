-- F.8.1 — Observability (cost + perf + errors inbox) backend foundation
-- Cross-ref: .claude/PLAN.md § "F.8 Decisões Cristalizadas" D2/D3/D4/D7/D10
-- D2 REUSE mcp_calls F.5.7 (NÃO criar tabela llm_calls)
-- D3 JSON custom rolling 1h (NÃO Prometheus) — perf_metrics hourly flush
-- D4 errors_inbox local + Sentry MCP F.5.6 hybrid query (F.8.2 implementa endpoint)
-- D7 NIM polling reusa nim_credit_history F.5.7 (já criada — schema balance_credits/source)
-- D10 retention manual F.future (SQLite sem partitions)
--
-- Apply PC:  python -c "import sqlite3; sqlite3.connect('hermes_local.db').executescript(open('migrations/2026_06_observability.sql','r',encoding='utf-8').read())"
-- Apply VM:  sqlite3 ~/.hermes/data/command_center.db < migrations/2026_06_observability.sql
-- Idempotente: CREATE IF NOT EXISTS + INSERT OR IGNORE.

-- 1) mcp_pricing — JOIN source pra /api/observability/costs USD estimate
-- D2 cost aggregate query: SUM(mc.cost_credits * COALESCE(p.cost_per_credit_usd, 0)) AS usd
CREATE TABLE IF NOT EXISTS mcp_pricing (
    model_id                     TEXT PRIMARY KEY,
    cost_per_credit_usd          REAL DEFAULT 0.0,    -- NIM credit-based USD/credit
    cost_per_1k_tokens_in_usd    REAL DEFAULT 0.0,    -- legacy paid model token pricing
    cost_per_1k_tokens_out_usd   REAL DEFAULT 0.0,
    notes                        TEXT,                -- pricing source URL/context
    updated_at                   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mcp_pricing_updated_at
    ON mcp_pricing(updated_at DESC);

-- 2) perf_metrics — hourly snapshot rolling 1h percentile (D3)
-- PC :55000 + VM :8420 + gateway :55401 → endpoint-keyed metrics
CREATE TABLE IF NOT EXISTS perf_metrics (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint          TEXT NOT NULL,              -- "GET /api/health" or service-scoped
    service           TEXT,                       -- 'pc' | 'vm' | 'gateway'
    recorded_at       TIMESTAMP NOT NULL,
    count             INTEGER NOT NULL,
    p50               REAL,
    p95               REAL,
    p99               REAL,
    min               REAL,
    max               REAL,
    avg               REAL
);

CREATE INDEX IF NOT EXISTS idx_perf_metrics_endpoint_time
    ON perf_metrics(endpoint, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_perf_metrics_service_time
    ON perf_metrics(service, recorded_at DESC);

-- 3) errors_inbox — local error triage (Sentry MCP hybrid F.8.2)
-- Categories: 'mcp_bypass' (F.5.4 banned-patterns) + 'brain_safety_gate' (F.6.4 destructive)
--             + 'validation_phase_fail' + 'nim_polling_error' + 'perf_flush_error' (F.8.1)
CREATE TABLE IF NOT EXISTS errors_inbox (
    id                TEXT PRIMARY KEY,           -- UUID string
    category          TEXT NOT NULL,
    severity          TEXT DEFAULT 'warning',     -- 'critical' | 'warning' | 'info'
    title             TEXT NOT NULL,
    message           TEXT,
    stack_trace       TEXT,                       -- truncated 2000 chars
    sentry_issue_id   TEXT,                       -- cross-ref Sentry MCP F.5.6 (F.8.2 populates)
    status            TEXT DEFAULT 'open',        -- 'open' | 'resolved' | 'wontfix'
    resolved_by       TEXT,
    resolved_at       TIMESTAMP,
    metadata_json     TEXT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_errors_inbox_status_time
    ON errors_inbox(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_errors_inbox_category
    ON errors_inbox(category, created_at DESC);

-- 4) Seed mcp_pricing — NIM Free Endpoints (zero cost) + NIM credit + Ollama PC + OpenRouter
-- Source: .claude/NVIDIA-MODELS-ROUTING-MATRIX.md §4 + .env HERMES_NIM_API_KEY
-- INSERT OR IGNORE: re-apply preserves manually-edited rows
INSERT OR IGNORE INTO mcp_pricing (model_id, cost_per_credit_usd, notes) VALUES
    -- NIM Free Endpoints (cost = 0)
    ('nvidia/mistral-nemotron',                       0.0, 'NIM Free Endpoint (best function calling any price F.6 Brain primary)'),
    ('nvidia/llama-3.3-nemotron-super-49b-v1',        0.0, 'NIM Free Endpoint (PT-BR official)'),
    ('nvidia/llama-3.1-nemotron-nano-8b-v1.1',        0.0, 'NIM Free Endpoint (classifier fast)'),
    ('nvidia/llama-3.1-nemotron-nano-4b-v1.1',        0.0, 'NIM Free Endpoint (classifier ultra-fast)'),
    ('meta/llama-4-scout-17b-16e-instruct',           0.0, 'NIM Free Endpoint (10M long context)'),
    ('meta/llama-4-maverick-17b-128e-instruct',       0.0, 'NIM Free Endpoint (1M long context)'),
    ('qwen/qwen3-coder-480b',                         0.0, 'NIM Free Endpoint (code gen agentic)'),
    ('mistralai/codestral-mamba-7b',                  0.0, 'NIM Free Endpoint (mamba ultra-fast)'),
    ('zhipu/glm-5.1',                                 0.0, 'NIM Free Endpoint (multilingual)'),
    ('nvidia/nv-embedqa-e5-v5',                       0.0, 'NIM Free Endpoint (embedding)'),
    -- NIM Credit-based (opt-in D3 F.5.7) — example $0.001/credit; owner adjusts via UPDATE
    ('deepseek-ai/deepseek-r1',                       0.001, 'NIM credit-based opt-in (reasoning premium)');

-- Ollama PC local — electricity ignored (cost = 0)
INSERT OR IGNORE INTO mcp_pricing (model_id, cost_per_credit_usd, notes) VALUES
    ('llama3.2:3b',           0.0, 'Ollama PC RTX 2060 6GB (electricity ignored)'),
    ('phi3:3.8b',             0.0, 'Ollama PC RTX 2060 6GB (electricity ignored)'),
    ('qwen2.5-coder:1.5b',    0.0, 'Ollama PC RTX 2060 6GB (electricity ignored)'),
    ('qwen2.5-coder:3b',      0.0, 'Ollama PC RTX 2060 6GB (electricity ignored)'),
    ('nomic-embed-text',      0.0, 'Ollama PC RTX 2060 6GB (embedding, no GPU)');

-- OpenRouter T4 último recurso (paid F.future opt-in)
INSERT OR IGNORE INTO mcp_pricing (model_id, cost_per_1k_tokens_in_usd, cost_per_1k_tokens_out_usd, notes) VALUES
    ('anthropic/claude-3.5-sonnet',  0.003, 0.015, 'OpenRouter paid F.future (T4 explicit force_provider)');
