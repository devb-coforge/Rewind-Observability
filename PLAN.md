# Agent Session Observability — Initial Plan

A containerized, single-user web app that indexes local coding-agent transcripts (Claude Code, Codex CLI) from mounted folders. This build is a transcript viewer, a usage tracker, an OpenTelemetry export, path-boundary alerts, and a private evals kept on this machine.

**Stack:** Python 3.12 + FastAPI (uv) · SQLite (FTS5) · React + TypeScript (Vite) · Docker / Compose

---

## 1. Scope

**In scope (v1)**
- Agents: Claude Code, Codex CLI
- Viewing after the fact (no live tailing)
- Transcript viewer: messages, thinking, tool calls paired with their results, subagents
- Usage tracker: tokens, estimated cost, models, tool usage, errors, durations, activity over time
- Usage and cost are best-effort estimates for understanding activity, not billing-grade accounting. Prefer reported usage when available, avoid obvious double-counting, and show unavailable values as unknown.
- OpenTelemetry export: one trace per session, spans for turns and tool calls, sent OTLP to a configured collector. Structural attributes and usage only, unless content export is explicitly enabled. Export is off when no endpoint is set.
- Path-boundary alerts: flag tool calls whose path sits outside the session's recorded project directory. Lexical comparison only. No git, and no read of the project working tree.
- Private evals: freeze a session slice into a local case, label it pass or fail, and compare cost and pass rate by model across those cases. The app does not re-run models.
- Claude Code and Codex CLI are equal priorities: both must work in the initial ingestion and transcript-viewer milestones.
- Search across sessions
- Editable session notes, stored locally in the app's writable data volume
- Hide and restore projects: hiding removes a project and its sessions from normal views without deleting source files
- Runs as one Docker image; sources mounted read-only

**Out of scope (v1)**
- Cursor and other agents (the adapter interface leaves room for them)
- Live streaming, file watchers, SSE
- Redaction, multi-user, auth beyond binding to localhost
- CI (simple pytest + vitest only)
- An MCP server over the index
- Joining sessions to git commits, cost-per-commit, or pull-request narratives
- Re-running an eval case against a live model (that would send prompt text off the machine)

---

## 2. Architecture

```
 Host folders (ro)                    Container
 ~/.claude  ─┐        ┌───────────────────────────────────────────┐
 ~/.codex   ─┼──────► │ /sources/*                                │
             │        │   │                                       │
             │        │   ▼                                       │
             │        │ Scanner ─► Adapter registry ─► Canonical  │
             │        │  (detect + parse)              events     │
             │        │                                  │        │
             │        │                                  ▼        │
             │        │                     SQLite index (/data)  │
             │        │                                  │        │
             │        │ FastAPI  /api/*  ◄───────────────┘        │
             │        │    └── serves built React SPA at /        │
             │        └───────────────────────────────────────────┘
                              ▲  127.0.0.1:8080
                           Browser
```

- **The source files are the source of truth**; the SQLite index is a cache you can always rebuild.
- **User data is separate from the index:** session notes and hidden-project preferences live in `/data/user.db` in the same local Docker volume. Reindexing or rebuilding `/data/index.db` never removes user data. Source mounts remain read-only.
- **Ingest is incremental**, triggered at startup and by `POST /api/reindex` (plus a "Rescan" button in the UI).
  - It tracks `(path, size, mtime, last_offset, adapter_version)` per file and parses only appended bytes.
  - If a file is truncated or rewritten, or the adapter version changes, that file is fully re-parsed.

---

## 3. Repository layout

```
Observability-System/
├── PLAN.md
├── README.md
├── Dockerfile                 # multi-stage: node build → python runtime
├── docker-compose.yml
├── config.example.yaml
├── backend/
│   ├── pyproject.toml         # uv
│   ├── src/obs/
│   │   ├── main.py            # FastAPI app, static mount
│   │   ├── config.py          # pydantic-settings: sources, db path, pricing
│   │   ├── models.py          # canonical Pydantic models
│   │   ├── db/
│   │   │   ├── schema.sql
│   │   │   └── repo.py        # queries (sqlite3, no ORM)
│   │   ├── user_data.py       # /data/user.db: session notes, hidden projects
│   │   ├── ingest/
│   │   │   ├── scanner.py     # walk sources, file state, dispatch
│   │   │   └── pipeline.py    # adapter → normalize → write
│   │   ├── adapters/
│   │   │   ├── base.py        # Adapter protocol
│   │   │   ├── claude_code.py
│   │   │   └── codex.py
│   │   ├── analytics/
│   │   │   ├── pricing.py     # model → $/Mtok table (yaml-overridable)
│   │   │   └── queries.py
│   │   └── api/
│   │       ├── sources.py
│   │       ├── sessions.py
│   │       ├── search.py
│   │       └── analytics.py
│   └── tests/
│       ├── fixtures/          # small real-world sample transcripts
│       ├── test_claude_code_adapter.py
│       ├── test_codex_adapter.py
│       └── test_api.py
└── frontend/
    ├── package.json
    ├── vite.config.ts         # dev proxy /api → :8080
    └── src/
        ├── api/               # generated types (openapi-typescript) + fetch client
        ├── pages/             # Sessions, SessionDetail, Analytics, Search, Sources
        ├── components/
        │   ├── timeline/      # EventRow, ToolCallCard, ThinkingBlock, DiffView...
        │   └── charts/
        └── main.tsx
```

---

## 4. Canonical data model

```python
class Session:
    id: str                    # "<agent>:<native_id>"
    agent: Literal["claude_code", "codex"]
    native_id: str
    source_path: str           # container path
    project_cwd: str | None    # host path recorded in transcript
    project_name: str | None   # basename of cwd
    git_branch: str | None
    models: list[str]
    parent_session_id: str | None   # subagent / sidechain parent
    started_at: datetime | None     # UTC
    ended_at: datetime | None
    title: str | None          # first user prompt, truncated
    # denormalized stats for fast lists
    n_events, n_user_msgs, n_tool_calls, n_tool_errors: int
    tokens_in, tokens_out, tokens_cache_read, tokens_cache_write: int | None
    est_cost_usd: float | None

class Event:
    id: str
    session_id: str
    parent_id: str | None
    seq: int                   # stable order within session
    ts: datetime | None
    role: Literal["user", "assistant", "system", "tool"]
    kind: Literal["message", "thinking", "tool_call", "tool_result",
                  "system", "summary", "unknown"]
    text: str | None
    tool_name: str | None
    tool_call_id: str | None   # pairs call ↔ result
    tool_input: dict | None
    tool_output: str | None    # large bodies lazy-loaded
    is_error: bool
    model: str | None
    usage: Usage | None        # in / out / cache_read / cache_write
    raw_ref: RawRef            # file + byte offset + length → "view raw"
```

**Rule:** never drop data. Unrecognized lines become `kind="unknown"` with a raw reference.

---

## 5. Adapters

```python
class Adapter(Protocol):
    name: str
    version: int
    def detect(self, root: Path) -> bool: ...
    def discover(self, root: Path) -> Iterable[Path]: ...       # session files
    def parse(self, path: Path, start_offset: int) -> Iterable[ParsedItem]: ...
```

**Claude Code** (`~/.claude/projects/<encoded-cwd>/*.jsonl`)
- Reads one JSON object per line: `type` (user/assistant/summary/system), `uuid`, `parentUuid`, `isSidechain`, `cwd`, `gitBranch`, `timestamp`, `message.content[]` blocks.
- Splits each line's content blocks into separate Events (text / thinking / tool_use / tool_result).
- Reads usage from `message.usage`. It dedupes repeated assistant chunks that share `message.id`, so tokens aren't double-counted.
- Sidechains and subagent files link to their parent session.

**Codex CLI** (`~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`)
- Reads `session_meta` for the id, cwd, timestamps and git info, and `turn_context` for model info.
- Maps `response_item` entries: message, reasoning, function_call, and function_call_output (paired via `call_id`).
- Reads token counts from `event_msg` token-count events. Other `event_msg` entries become system/unknown.

**Shared**
- Tolerates a truncated last line (stops and keeps the offset), stray non-JSON lines, and fields that are missing.
- Normalizes all timestamps to UTC.
- Fixtures for tests come from real, trimmed, sanitized transcripts from both agents. Validate the canonical model against both formats before finalizing the schema.
- Usage is best-effort: use reported counts and straightforward deduplication or cumulative-count handling where the format requires it. Missing usage stays unknown; sophisticated reconciliation is outside v1 scope.

---

## 6. Storage (SQLite)

- `files(path PK, agent, size, mtime, last_offset, adapter_version, session_id)`
- `sessions(...)` with indexes on agent, project, started_at, and model
- `events(...)`, with large `tool_output` bodies in `event_blobs` so list queries stay light
- `events_fts` (FTS5 over text, tool_name, and a tool_input/output preview) for search
- Stored in a WAL-mode db at `/data/index.db`, in a Docker named volume

**Local user data** lives separately in `/data/user.db` in the same volume:
- `session_notes(session_id PK, text, updated_at)`: one editable plain-text note per session, keyed by stable `<agent>:<native_id>`. Saving empty text clears the note.
- `project_preferences(project_id PK, hidden, updated_at)`: persistent hide/restore state. Project identity uses the agent and normalized recorded host `cwd`, not the display basename. Sessions without a recorded `cwd` belong to an explicit per-agent unknown-project group.
- `boundary_dismissals(project_id, path_prefix, updated_at)`: paths you have marked as allowed outside the recorded cwd. Dismissals survive reindex.
- `eval_cases(...)`: frozen session slices and your pass/fail verdict. See section 15. Cases survive reindex because they are copies, not pointers into the transcript.
- Notes and preferences survive incremental scans, full reindexing, and temporary source removal. Retain them even when their indexed session or project is absent so they reconnect when the same identity returns.
- These writes affect only the local app data volume. No transcript or host project files are edited or deleted. The README documents backing up the volume, including `user.db`.

---

## 7. Analytics (v1)

| Metric | Breakdown |
|---|---|
| Sessions per day/week | agent, project |
| Tokens (in/out/cache) and estimated cost | agent, model, project, day |
| Session duration and turns per session | agent, project |
| Tool usage counts | tool name, agent |
| Tool error rate | tool name |
| Top projects by activity | — |
| Model mix over time | agent |

- Cost comes from `pricing.yaml` (per-model $/Mtok, which the user can override). It is shown as an estimate, and models without a price show "—".
- Token totals are also labeled as estimates. Sessions with unavailable usage show "—"; aggregate totals reflect known usage and indicate when coverage is incomplete.
- All analytics endpoints accept common filters: `agent`, `project`, `model`, `from`, `to`.
- Hidden projects are excluded from default project/session lists, search, and analytics. An explicit `include_hidden=true` option includes them; direct session links remain accessible and indicate when the project is hidden.

---

## 8. API

```
GET  /api/health
GET  /api/sources                       # mounted roots, detected agent, file counts
POST /api/reindex                       # incremental; ?full=true to rebuild
GET  /api/projects
PATCH /api/projects/{project_id}         # {hidden: true|false}; local preference only
GET  /api/sessions?agent=&project=&model=&from=&to=&q=&sort=&cursor=
GET  /api/sessions/{id}                 # metadata + stats + child sessions
GET  /api/sessions/{id}/note             # local note + updated_at
PUT  /api/sessions/{id}/note             # {text: "..."}; empty text clears it
GET  /api/sessions/{id}/events?cursor=&limit=&kinds=
GET  /api/events/{id}/output            # lazy full tool output
GET  /api/events/{id}/raw               # raw source line(s)
GET  /api/search?q=&agent=&project=
GET  /api/analytics/summary
GET  /api/analytics/timeseries?metric=&bucket=day&group_by=
GET  /api/analytics/tools
GET  /api/boundary?project=&from=&to=             # sessions with outside-cwd paths
GET  /api/sessions/{id}/boundary                  # paths, event ids, dismissed or not
PUT  /api/boundary/dismissals                     # {project_id, path_prefix}; local allow
DELETE /api/boundary/dismissals?project_id=&path_prefix=
POST /api/evals/cases                         # freeze {session_id, from_seq?, to_seq?}
GET  /api/evals/cases?project=&model=&verdict=
GET  /api/evals/cases/{id}
PATCH /api/evals/cases/{id}                   # {verdict, note}
DELETE /api/evals/cases/{id}
GET  /api/evals/summary?group_by=model        # pass rate, cost, tokens
```

Frontend TypeScript types are generated from `/openapi.json` using `openapi-typescript`.
Project APIs expose an opaque URL-safe `project_id`; the server maps it to the stable project identity. Project/session list, search, and analytics endpoints accept `include_hidden` (default `false`).

---

## 9. Frontend

- **Sessions:** a filterable, sortable table of sessions (agent, project, title, start, duration, tokens, cost, errors), grouped by project.
  - Each project group has a **Hide project** action. It immediately disappears from normal views; a **Show hidden projects** toggle reveals hidden groups with a **Restore project** action. Explain that hiding leaves source files untouched, and offer an Undo action after hiding.
- **Session detail:**
  - Virtualized timeline (TanStack Virtual). Tool calls are collapsed by default, thinking is hidden behind a toggle, and calls are paired with their results.
  - Specialized renderers for edit/patch diffs, shell commands and output, file reads, and Markdown.
  - Side panel with stats, models, and a list of subagents; "view raw" on any event.
  - A **Session note** editor with explicit Save and Clear actions, visible saved/saving/error status, and protection against silently discarding unsaved edits. Notes are plain text and render safely. Saving updates the local note without changing the transcript.
- **Analytics:** a KPI row plus charts (Recharts), all sharing a global filter bar.
- **Search:** full-text hits that deep-link into the session timeline.
- **Sources:** what's mounted, what was detected, last index time, and a Rescan button.
- **Boundary:** a count on the session row, the offending events marked in the timeline, and the path list in the side panel. Dismissing a path prefix allows it for that project.
- **Evals:** from a session, freeze the whole session or a turn range as a case. A cases page shows your verdict, the prompt, the tool and path summary, and pass rate plus estimated cost by model.
- **Libraries:** TanStack Query for data fetching, React Router, and Tailwind + shadcn/ui (swappable).

---

## 10. Containerization

- **Dockerfile:** stage 1 is `node:20-alpine`, which builds the frontend. Stage 2 is `python:3.12-slim` with uv, which installs the backend and copies in `dist/`. It runs as a non-root user (`PUID`/`PGID`) with `uvicorn --host 0.0.0.0 --port 8080`.
- **docker-compose.yml:**

```yaml
services:
  obs:
    build: .
    ports: ["127.0.0.1:8080:8080"]   # never exposed beyond localhost
    volumes:
      - ~/.claude:/sources/claude:ro
      - ~/.codex:/sources/codex:ro
      - obs-data:/data
    environment:
      OBS_SOURCES: /sources/claude,/sources/codex   # or config.yaml
volumes:
  obs-data:
```

- Each source can either declare its agent explicitly in `config.yaml` or rely on `detect()`.
- To add more folders, users add a volume line to the compose file. The README explains this.

---

## 11. Testing

- **Backend (pytest):** adapter tests against fixtures, covering block splitting, call/result pairing, usage dedupe, truncated last lines, and unknown lines. Incremental-ingest tests (append → only new events) and API smoke tests using `TestClient` with a temp db.
- **Local user data (pytest):** note save/read/clear; project hide/restore; consistent hidden-project filtering across lists, search, and analytics; notes/preferences surviving a full index rebuild and source disappearance/reappearance.
- **Frontend (vitest + Testing Library):** event renderers and pairing logic, note editing/save failure behavior, and hide/restore interactions.
- **OpenTelemetry (pytest):** span mapping for a message and a paired tool call/result; stable ids across a second export; content attributes absent by default; a boundary violation exports a boolean and not the path; eval case text is never exported; ingest succeeds when the collector is down; no export when the endpoint is empty.
- **Path boundary (pytest):** a file tool inside cwd is quiet; `../` and an absolute path outside cwd alert; a relative path resolves against the recorded cwd; a missing cwd produces no alerts; a shell command alerts only on an absolute path outside cwd; a dismissal hides that prefix and survives reindex.
- **Evals (pytest):** freezing a case copies the prompt, model, usage, and tool/path summary into `user.db`; a full reindex leaves the case in place; summary pass rate and cost group by model; deleting a case removes only that row.
- **Manual:** `docker compose up` against real `~/.claude` and `~/.codex` folders. Confirm a collector receives traces only after an endpoint is configured.

---

## 12. Milestones

| # | Deliverable | Done when |
|---|---|---|
| M0 | Repo scaffold: uv backend, Vite frontend, Dockerfile, compose, README | `docker compose up` serves a hello page and `/api/health` |
| M1 | Canonical models validated against both agents, SQLite schema, scanner, **Claude Code and Codex adapters** + tests | Both real source folders index; fixtures verify session/event counts, call/result pairing, and basic usage handling |
| M2 | Sessions list and Session detail timeline for **both agents**, local session notes, project hide/restore | Can comfortably read both agents' sessions, save and clear notes, and hide/restore projects without modifying sources; user data survives full reindexing |
| M3 | Ingestion and viewer reliability for **both agents** | Append/retry and truncated-line tests pass for each adapter; resumed sessions and available subagent links render correctly |
| M4 | Usage tracker: analytics endpoints, pricing, Analytics page | Charts filter by agent, project, model, and date. Tokens, estimated cost, tool usage, errors, and duration are visible |
| M5 | Search (FTS5), Sources page, polish, raw view | Search deep-links to events; README is complete |
| M6 | OpenTelemetry export | With an endpoint set, a collector receives one trace per session and tool spans carry status and usage. Content is absent unless enabled. With no endpoint, ingest and the UI behave as before |
| M7 | Path-boundary alerts | Sessions show outside-cwd file and shell paths. Dismissals stick. No project directory is mounted to answer the check |
| M8 | Private evals | A frozen case survives reindex, takes a pass/fail verdict, and the summary compares models on those cases. The app never calls a model provider |

---

## 13. OpenTelemetry export

Sessions and events are already span-shaped. The exporter uses that shape. It does not read git, and it does not expose an MCP server.

- **Identity.** One trace per session. Span and trace ids are derived from the stable session and event ids, so a reindex updates the same spans instead of duplicating them.
- **Spans.** User and assistant messages, thinking, and tool calls. A tool call and its result are one span: start at the call, end at the result, status `ERROR` when `is_error` is set. A subagent session links to its parent via `parent_session_id`; it stays its own trace.
- **Always exported.** Agent, model, project name, event kind, tool name, status, token counts, estimated cost, timestamps.
- **Content stays local unless asked.** Prompt text, thinking, tool input, and tool output are omitted unless `include_content` is true. That flag is the first path that can send transcript text off the machine.
- **Off by default.** `otel.endpoint` empty means the exporter does nothing. Ingest and the UI do not depend on a collector.
- **When it runs.** After a successful ingest, export events not yet acknowledged. A row in the index records the last exported sequence per session. Collector errors are stored and shown on the Sources page; they do not fail ingest.
- **Protocol.** OTLP over HTTP. Protobuf is the default; JSON is acceptable if it keeps the client smaller.

```yaml
otel:
  endpoint: ""            # empty disables export
  include_content: false
  protocol: http/protobuf
```

A span for an outside-cwd tool call may include the boolean attribute `obs.path_outside_cwd=true`. The path string stays local with the rest of the content.

---

## 14. Path-boundary alerts

No git and no working tree. The check compares paths found in tool calls with the session's recorded `project_cwd`.

- **Where paths come from.** During ingest, pull paths out of known tool-argument fields (`file_path`, `path`, `notebook_path`, and the same idea under either agent). Store them on the event. A tool with no recognized path field produces no alert.
- **Shell.** Flag a shell command only when it contains an absolute path outside the cwd. Relative paths inside a command string are left alone. Structured file tools are the reliable signal.
- **Inside or outside.** Resolve relative paths against `project_cwd`. Collapse `.` and `..` lexically. A path is inside when it equals the cwd or sits under it. Do not call `realpath` and do not stat the file.
- **No cwd.** If the session has no recorded project directory, skip boundary checks. Do not alert on every path.
- **Allowlist.** A dismissal in `user.db` is a path prefix allowed for that project. Config may also list prefixes. Dismissed paths stay visible as allowed, and they drop off the default alert list.
- **UI.** Session list shows a count. The timeline marks the event. The side panel lists the paths.

---

## 15. Private evals

A case is a copy of work you already did, plus a verdict you assign. Comparison is across those cases. Nothing is sent to a model provider.

Freeze from a session, either the whole session or a sequence range starting at a user turn:

- Prompt text, agent, model, project cwd
- Tool-call summary: tool name, paths, error flag. Full tool output is not copied
- Token totals and estimated cost, as known at freeze time
- The final assistant message, as the reference for what happened
- Verdict: unset, pass, or fail, and a short note

Cases live in `user.db`. Rebuilding the index does not delete them. Deleting a case deletes that row only.

The summary groups cases by model (and can filter by project): count, pass rate among cases that have a verdict, median estimated cost, median tokens. Models are compared on the cases you chose to freeze, which is a biased sample of your work, and the page should say so.

---

## 16. Risks and mitigations

- **Agent formats change without notice:** tolerant parsers, `unknown` events, `adapter_version` triggering a re-index, fixture tests.
- **Usage double-counting** from streamed or duplicated assistant chunks: dedupe by message id, with tests.
- **Resumed or forked sessions** duplicating history: dedupe events by native uuid within a project.
- **Very large sessions or tool outputs:** cursor pagination, a separate blob table, a virtualized UI.
- **Usage and cost accuracy:** best-effort estimates, explicitly labeled; missing values remain unknown and pricing is user-editable. Billing-grade reconciliation is outside v1 scope.
- **Host and container path mismatch:** store both and group by the recorded host `cwd`.
- **Export duplicates spans on reindex:** derive trace and span ids from stable session and event ids.
- **Collector unreachable:** ingest commits first; export failure is recorded and retried on the next run.
- **Transcript text leaving the machine:** content attributes are off unless `include_content` is set. The default export is structure and usage only. Eval cases are user data and are not exported.
- **Path boundary is lexical:** `..` is caught, symlink escapes are not, because the project tree is not mounted. Shell alerts trust absolute paths only. Compare host path to host cwd, both as recorded in the transcript.
- **An eval verdict is yours:** pass/fail is a label you set. The app does not infer correctness from git, and it does not replay the prompt.
