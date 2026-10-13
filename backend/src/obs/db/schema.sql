PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS files (
  path TEXT PRIMARY KEY,
  agent TEXT NOT NULL,
  size INTEGER NOT NULL,
  mtime REAL NOT NULL,
  last_offset INTEGER NOT NULL,
  adapter_version INTEGER NOT NULL,
  session_id TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  agent TEXT NOT NULL,
  native_id TEXT NOT NULL,
  source_path TEXT NOT NULL,
  project_cwd TEXT,
  project_name TEXT,
  project_id TEXT NOT NULL,
  git_branch TEXT,
  models_json TEXT NOT NULL DEFAULT '[]',
  parent_session_id TEXT,
  started_at TEXT,
  ended_at TEXT,
  title TEXT,
  source_title TEXT,
  n_events INTEGER NOT NULL DEFAULT 0,
  n_user_msgs INTEGER NOT NULL DEFAULT 0,
  n_tool_calls INTEGER NOT NULL DEFAULT 0,
  n_tool_errors INTEGER NOT NULL DEFAULT 0,
  tokens_in INTEGER,
  tokens_out INTEGER,
  tokens_cache_read INTEGER,
  tokens_cache_write INTEGER,
  est_cost_usd REAL,
  cost_partial INTEGER NOT NULL DEFAULT 0,
  usage_coverage TEXT NOT NULL DEFAULT 'none',
  boundary_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS session_models (
  session_id TEXT NOT NULL,
  model TEXT NOT NULL,
  PRIMARY KEY (session_id, model)
);

CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  parent_id TEXT,
  seq INTEGER NOT NULL DEFAULT 0,
  ts TEXT,
  role TEXT NOT NULL,
  kind TEXT NOT NULL,
  text TEXT,
  tool_name TEXT,
  tool_call_id TEXT,
  tool_input_json TEXT,
  tool_output_preview TEXT,
  is_error INTEGER NOT NULL DEFAULT 0,
  model TEXT,
  usage_json TEXT,
  usage_origin TEXT,
  message_id TEXT,
  raw_path TEXT NOT NULL,
  raw_offset INTEGER NOT NULL,
  raw_length INTEGER NOT NULL,
  paths_json TEXT,
  block_index INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS event_blobs (
  event_id TEXT PRIMARY KEY,
  tool_output TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
  event_id UNINDEXED,
  session_id UNINDEXED,
  text,
  tool_name,
  preview
);

CREATE TABLE IF NOT EXISTS export_state (
  session_id TEXT PRIMARY KEY,
  last_seq INTEGER NOT NULL,
  last_error TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_session_models_model ON session_models(model);
CREATE INDEX IF NOT EXISTS idx_events_session_seq ON events(session_id, seq);
CREATE INDEX IF NOT EXISTS idx_events_raw_path ON events(raw_path);
CREATE INDEX IF NOT EXISTS idx_files_session ON files(session_id);
