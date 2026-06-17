-- F.7 P5 hardening — Hunter.io email verifier cache (30d TTL)
-- Idempotent (CREATE IF NOT EXISTS).
-- Cache verify_email calls so quota 50/mo Hunter free tier no esgota.

CREATE TABLE IF NOT EXISTS hunter_email_cache (
    email TEXT PRIMARY KEY,
    status TEXT NOT NULL,        -- 'valid' | 'invalid' | 'accept_all' | 'unknown'
    score INTEGER,               -- 0-100
    smtp_check INTEGER,          -- 0/1
    mx_records INTEGER,          -- 0/1
    disposable INTEGER,          -- 0/1
    webmail INTEGER,             -- 0/1
    raw_json TEXT,               -- Hunter full response
    verified_at TEXT NOT NULL,   -- ISO UTC
    expires_at TEXT NOT NULL     -- +30d TTL ISO UTC
);

CREATE INDEX IF NOT EXISTS idx_hunter_expires ON hunter_email_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_hunter_status ON hunter_email_cache(status);
