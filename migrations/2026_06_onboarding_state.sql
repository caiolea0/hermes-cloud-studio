-- UX-RM-F3-A: onboarding wizard state persistence
CREATE TABLE IF NOT EXISTS onboarding_state (
    user_id TEXT PRIMARY KEY DEFAULT 'owner',
    last_step INTEGER DEFAULT 0,
    state_json TEXT,
    completed INTEGER DEFAULT 0,
    completed_at TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);
