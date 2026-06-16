-- F.7 C5 — Cobaia autotune triggers table (idempotent via CREATE TABLE IF NOT EXISTS)
-- Records auto-tune synthesis events triggered by sustained KPI breaches (D10)

CREATE TABLE IF NOT EXISTS cobaia_autotune_triggers (
    id TEXT PRIMARY KEY,                    -- UUID
    account_handle TEXT NOT NULL,
    trigger_at TEXT NOT NULL,               -- ISO UTC when breach detected
    kpi_breached TEXT NOT NULL,             -- 'reply_rate' | 'accept_rate' | 'view_to_connect'
    kpi_value REAL NOT NULL,                -- actual KPI value at breach time
    kpi_threshold REAL NOT NULL,            -- D3 threshold that was breached
    sustained_hours INTEGER NOT NULL,       -- hours below threshold at trigger
    synthesis_run_id TEXT NULL,             -- FK → synthesis_runs.id (F.4.2 C3 scaffold)
    result_status TEXT NULL,                -- 'queued' | 'completed' | 'failed' | 'no_pr'
    result_pr_url TEXT NULL,                -- PR URL if synthesis created one
    created_at TEXT NOT NULL,
    updated_at TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_cobaia_autotune_account
    ON cobaia_autotune_triggers(account_handle, trigger_at DESC);

CREATE INDEX IF NOT EXISTS idx_cobaia_autotune_kpi
    ON cobaia_autotune_triggers(account_handle, kpi_breached, trigger_at DESC);
