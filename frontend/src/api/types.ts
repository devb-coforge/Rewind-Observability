export type Usage = {
  input_tokens: number | null;
  output_tokens: number | null;
  cache_read_tokens: number | null;
  cache_write_tokens: number | null;
};

export type PathHit = {
  path?: string;
  resolved?: string;
  kind?: string;
  outside?: boolean;
  dismissed?: boolean;
  allowed?: boolean;
  event_id?: string;
};

export type Session = {
  id: string;
  agent: string;
  native_id: string;
  source_path: string;
  project_cwd: string | null;
  project_name: string | null;
  project_id: string;
  project_hidden: boolean;
  git_branch: string | null;
  models: string[];
  parent_session_id: string | null;
  started_at: string | null;
  ended_at: string | null;
  duration_sec: number | null;
  title: string | null;
  n_events: number;
  n_user_msgs: number;
  n_tool_calls: number;
  n_tool_errors: number;
  tokens_in: number | null;
  tokens_out: number | null;
  tokens_cache_read: number | null;
  tokens_cache_write: number | null;
  est_cost_usd: number | null;
  cost_partial: boolean;
  usage_coverage: string;
  boundary_count: number;
};

export type ChildSession = {
  id: string;
  title: string | null;
  agent: string;
  started_at: string | null;
};

export type Note = {
  text: string;
  updated_at: string | null;
};

export type SessionDetail = Session & {
  children: ChildSession[];
  note: Note | null;
};

export type ObsEvent = {
  id: string;
  session_id: string;
  parent_id: string | null;
  seq: number;
  ts: string | null;
  role: string;
  kind: string;
  text: string | null;
  tool_name: string | null;
  tool_call_id: string | null;
  tool_input: Record<string, unknown> | null;
  tool_output_preview: string | null;
  is_error: boolean;
  model: string | null;
  usage: Usage | null;
  raw: { path: string; offset: number; length: number };
  paths: PathHit[];
};

export type Project = {
  project_id: string;
  agent: string;
  name: string;
  cwd: string | null;
  hidden: boolean;
  n_sessions: number;
};

export type SearchHit = {
  event_id: string;
  session_id: string;
  seq: number;
  kind: string;
  ts: string | null;
  snippet: string;
  session_title: string | null;
  project_name: string | null;
  agent: string;
  project_id: string;
};

export type Summary = {
  sessions: number;
  tokens_in: number | null;
  tokens_out: number | null;
  tokens_cache_read: number | null;
  tokens_cache_write: number | null;
  est_cost_usd: number | null;
  usage_coverage: string;
  cost_coverage: string;
  tool_calls: number;
  tool_errors: number;
  median_duration_sec: number | null;
  sessions_missing_usage: number;
  sessions_missing_start: number;
};

export type SeriesPoint = {
  bucket: string;
  group: string;
  value: number | null;
};

export type ToolStat = {
  tool_name: string;
  calls: number;
  errors: number;
  error_rate: number;
};

export type SourceInfo = {
  path: string;
  agent: string | null;
  detected: boolean;
  exists: boolean;
  files: number;
  sessions: number;
};

export type SourcesResponse = {
  sources: SourceInfo[];
  last_indexed_at: string | null;
  otel: {
    enabled: boolean;
    endpoint: string;
    include_content: boolean;
    protocol: string;
    last_error: string | null;
  };
};

export type BoundaryPath = {
  path: string | null;
  resolved: string | null;
  kind: string | null;
  event_id: string;
  dismissed: boolean;
  allowed: boolean;
};

export type ToolSummary = {
  tool_name: string | null;
  paths: string[];
  is_error: boolean;
};

export type BenchmarkCase = {
  id: string;
  session_id: string;
  project_id: string | null;
  project_cwd: string | null;
  project_name: string | null;
  agent: string;
  model: string | null;
  prompt: string | null;
  final_message: string | null;
  tool_summary: ToolSummary[];
  tokens_in: number | null;
  tokens_out: number | null;
  tokens_cache_read: number | null;
  tokens_cache_write: number | null;
  est_cost_usd: number | null;
  from_seq: number | null;
  to_seq: number | null;
  verdict: "unset" | "pass" | "fail" | string;
  note: string | null;
  created_at: string;
  updated_at: string;
};

export type BenchmarkGroup = {
  model: string;
  n: number;
  n_verdict: number;
  pass_rate: number | null;
  median_cost: number | null;
  median_tokens: number | null;
};

export type Filters = {
  agent?: string;
  project?: string;
  model?: string;
  from?: string;
  to?: string;
  include_hidden?: boolean;
};
