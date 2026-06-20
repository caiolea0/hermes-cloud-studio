-- UX-RM-F6-B: Template editor tables
-- templates: reusable message templates per channel with spintax support
-- Idempotent (IF NOT EXISTS). Apply on PC + VM.

CREATE TABLE IF NOT EXISTS templates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT    NOT NULL DEFAULT 'owner',
    name        TEXT    NOT NULL,
    channel     TEXT    NOT NULL,
    action_type TEXT,
    subject     TEXT,
    body        TEXT    NOT NULL,
    category    TEXT    DEFAULT 'intro',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_templates_channel ON templates(channel);
