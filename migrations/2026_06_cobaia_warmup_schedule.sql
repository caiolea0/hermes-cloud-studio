-- F8-A — Cobaia today's queue scheduling table (idempotent via IF NOT EXISTS)
-- Stores planned warmup actions per day for the Today's Queue widget.

CREATE TABLE IF NOT EXISTS cobaia_warmup_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_handle TEXT NOT NULL DEFAULT 'cobaia',
    action TEXT NOT NULL,       -- 'view' | 'engage' | 'connect' | 'follow' | 'message'
    eta TEXT NOT NULL,          -- ISO8601 datetime (local timezone)
    description TEXT,           -- human-readable label for the queue item
    completed INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,
    skipped INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cobaia_schedule_eta
    ON cobaia_warmup_schedule(account_handle, eta);

CREATE INDEX IF NOT EXISTS idx_cobaia_schedule_today
    ON cobaia_warmup_schedule(eta, completed);
