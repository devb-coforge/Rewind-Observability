CREATE TABLE IF NOT EXISTS session_notes (
  session_id TEXT PRIMARY KEY,
  text TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_preferences (
  project_id TEXT PRIMARY KEY,
  hidden INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_names (
  project_key TEXT PRIMARY KEY,
  project_name TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS boundary_dismissals (
  project_id TEXT NOT NULL,
  path_prefix TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (project_id, path_prefix)
);

CREATE TABLE IF NOT EXISTS eval_cases (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  session_title TEXT,
  project_id TEXT,
  project_cwd TEXT,
  project_name TEXT,
  agent TEXT NOT NULL,
  model TEXT,
  prompt TEXT,
  final_message TEXT,
  tool_summary_json TEXT NOT NULL,
  tokens_in INTEGER,
  tokens_out INTEGER,
  tokens_cache_read INTEGER,
  tokens_cache_write INTEGER,
  est_cost_usd REAL,
  from_seq INTEGER,
  to_seq INTEGER,
  verdict TEXT NOT NULL DEFAULT 'unset',
  note TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_eval_model ON eval_cases(model);
CREATE INDEX IF NOT EXISTS idx_eval_project ON eval_cases(project_id);
