-- UX-RM-F3-B: ICP Profile table
CREATE TABLE IF NOT EXISTS icp_profile (
    user_id TEXT PRIMARY KEY DEFAULT 'owner',
    industries TEXT,
    company_size_min INTEGER,
    company_size_max INTEGER,
    revenue_range TEXT,
    job_titles TEXT,
    seniority_levels TEXT,
    countries TEXT,
    states TEXT,
    cities TEXT,
    keywords_include TEXT,
    keywords_exclude TEXT,
    max_prospects_per_day INTEGER DEFAULT 5,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
