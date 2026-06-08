-- ============================================================================
-- LinkedIn Fase 2 — Rich profile cache + connection tracking + post engagements
-- Applied at startup by server.py (local) and hermes_api.py (VM)
-- ============================================================================

-- Rich profile cache. Keyed by canonical LinkedIn URL.
CREATE TABLE IF NOT EXISTS linkedin_profiles (
    profile_url      TEXT PRIMARY KEY,        -- https://www.linkedin.com/in/{slug}
    name             TEXT,
    photo            TEXT,                    -- absolute URL (LinkedIn CDN)
    headline         TEXT,                    -- full headline (e.g., "Tech Recruiter @ Nubank | Hiring Eng")
    current_role     TEXT,                    -- parsed first segment ("Tech Recruiter")
    current_company  TEXT,                    -- parsed company name ("Nubank")
    company_domain   TEXT,                    -- for clearbit logo (best-effort)
    location         TEXT,                    -- "São Paulo, SP, Brasil"
    bio              TEXT,                    -- about section, truncated 300 chars
    mutual_count     INTEGER DEFAULT 0,
    degree           TEXT,                    -- "1st" | "2nd" | "3rd" | "out"
    top_skills       TEXT,                    -- JSON array, up to 5
    last_activity    TEXT,                    -- "há 2 dias" / "há 5h" / etc.
    first_seen_at    TEXT,                    -- ISO UTC
    last_seen_at     TEXT,                    -- ISO UTC, updated on every visit
    visit_count      INTEGER DEFAULT 0,
    extraction_meta  TEXT                     -- JSON with which selectors hit/missed
);

CREATE INDEX IF NOT EXISTS idx_li_profiles_company ON linkedin_profiles(current_company);
CREATE INDEX IF NOT EXISTS idx_li_profiles_last_seen ON linkedin_profiles(last_seen_at);

-- Connection lifecycle tracking. Status changes over time (refresh job).
CREATE TABLE IF NOT EXISTS linkedin_connections (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id         INTEGER,               -- references linkedin_campaigns(id)
    profile_url         TEXT NOT NULL,         -- references linkedin_profiles(profile_url)
    status              TEXT DEFAULT 'pending',-- pending | accepted | rejected | ignored
    note_sent           TEXT,
    sent_at             TEXT,
    status_updated_at   TEXT,
    refresh_attempts    INTEGER DEFAULT 0,
    UNIQUE(campaign_id, profile_url)
);

CREATE INDEX IF NOT EXISTS idx_li_conn_status ON linkedin_connections(status);
CREATE INDEX IF NOT EXISTS idx_li_conn_campaign ON linkedin_connections(campaign_id);

-- Post metadata cache.
CREATE TABLE IF NOT EXISTS linkedin_posts (
    post_url         TEXT PRIMARY KEY,
    author_url       TEXT,                    -- references linkedin_profiles(profile_url)
    text             TEXT,                    -- up to 2000 chars
    likes_at_capture INTEGER DEFAULT 0,
    comments_at_capture INTEGER DEFAULT 0,
    date_label       TEXT,                    -- "há 2h"
    first_seen_at    TEXT
);

-- Engagement records (one row per (campaign, post) pair).
CREATE TABLE IF NOT EXISTS linkedin_engagements (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id           INTEGER,
    post_url              TEXT,
    liked                 INTEGER DEFAULT 0,
    liked_at              TEXT,
    commented             INTEGER DEFAULT 0,
    comment_id            TEXT,                -- LinkedIn comment data-id (for edit/delete)
    comment_text          TEXT,
    comment_tone          TEXT,                -- "Profissional" | "Técnico" | "Casual"
    ollama_model          TEXT,
    validation_score      REAL,
    validation_note       TEXT,
    generation_attempts   INTEGER DEFAULT 1,
    created_at            TEXT,
    edited_at             TEXT,
    deleted_at            TEXT,
    UNIQUE(campaign_id, post_url)
);

CREATE INDEX IF NOT EXISTS idx_li_eng_campaign ON linkedin_engagements(campaign_id);
CREATE INDEX IF NOT EXISTS idx_li_eng_comment_id ON linkedin_engagements(comment_id);

-- Visited profiles pool (for connect mode="visited") — derived from view campaigns.
-- This is a view, not a table — kept in linkedin_profiles + linkedin_campaigns JOIN.
-- For convenience, an index:
CREATE INDEX IF NOT EXISTS idx_li_profiles_visit_count ON linkedin_profiles(visit_count DESC);
