-- UX-RM-F1-B: daemon sequence engine tables
-- inbox_replies: inbound channel messages waiting handling
-- sequence_enrollments: follow-up schedule per prospect
-- telegram_stop_signals: human STOP override for auto-response
-- Idempotent (IF NOT EXISTS). Apply on PC + VM.

CREATE TABLE IF NOT EXISTS inbox_replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL,
    channel TEXT NOT NULL DEFAULT 'unknown',
    body TEXT NOT NULL DEFAULT '',
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    handled INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_inbox_replies_handled
    ON inbox_replies(handled, received_at);

CREATE TABLE IF NOT EXISTS sequence_enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id INTEGER NOT NULL,
    sequence_id TEXT NOT NULL DEFAULT 'default',
    current_step INTEGER NOT NULL DEFAULT 0,
    next_action_at TIMESTAMP NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (prospect_id, sequence_id)
);
CREATE INDEX IF NOT EXISTS idx_seq_enrollments_due
    ON sequence_enrollments(completed, next_action_at);

CREATE TABLE IF NOT EXISTS telegram_stop_signals (
    prospect_id INTEGER NOT NULL,
    channel TEXT NOT NULL DEFAULT 'all',
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (prospect_id, channel)
);
