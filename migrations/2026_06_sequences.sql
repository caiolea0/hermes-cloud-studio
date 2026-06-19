-- UX-RM-F6-A: Canvas Sequence Builder schema
-- sequences: draft/active/paused/archived multi-channel outreach sequences
-- sequence_nodes: drag-drop canvas nodes (start/action/delay/condition/end)
-- sequence_edges: directed edges connecting nodes (default/if_true/if_false)

CREATE TABLE IF NOT EXISTS sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'owner',
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sequence_nodes (
    id TEXT PRIMARY KEY,
    sequence_id INTEGER NOT NULL,
    node_type TEXT NOT NULL,
    channel TEXT,
    action_type TEXT,
    position_x REAL NOT NULL DEFAULT 0,
    position_y REAL NOT NULL DEFAULT 0,
    config_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (sequence_id) REFERENCES sequences(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sequence_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sequence_id INTEGER NOT NULL,
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    edge_type TEXT NOT NULL DEFAULT 'default',
    FOREIGN KEY (sequence_id) REFERENCES sequences(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sequence_nodes_seq ON sequence_nodes(sequence_id);
CREATE INDEX IF NOT EXISTS idx_sequence_edges_seq ON sequence_edges(sequence_id);
