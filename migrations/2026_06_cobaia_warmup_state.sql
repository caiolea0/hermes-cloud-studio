-- F.7 C1 — Cobaia warmup state + daily metrics (idempotent via CREATE TABLE IF NOT EXISTS)

CREATE TABLE IF NOT EXISTS cobaia_warmup_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_handle TEXT NOT NULL UNIQUE,
    started_at TEXT NOT NULL,
    current_day INTEGER NOT NULL DEFAULT 0,
    phase TEXT NOT NULL DEFAULT 'lurking',  -- 'lurking' | 'ramp' | 'normal' | 'paused'
    paused_at TEXT,
    pause_reason TEXT,
    last_check_at TEXT,
    consecutive_errors INTEGER NOT NULL DEFAULT 0,
    config_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS cobaia_daily_metrics (
    date TEXT NOT NULL,
    account_handle TEXT NOT NULL,
    views_count INTEGER DEFAULT 0,
    connects_sent INTEGER DEFAULT 0,
    connects_accepted INTEGER DEFAULT 0,
    replies_received INTEGER DEFAULT 0,
    engagements_count INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,
    PRIMARY KEY (date, account_handle)
);

CREATE INDEX IF NOT EXISTS idx_cobaia_daily_metrics_account ON cobaia_daily_metrics(account_handle, date DESC);
