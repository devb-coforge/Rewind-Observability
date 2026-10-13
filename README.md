# Obs

A single-user web app that indexes local agent transcripts. It is a transcript viewer, a usage tracker, an OpenTelemetry export, path-boundary alerts, and a private benchmark. The transcript files stay read-only. Notes, hidden projects, path allows, and benchmark cases live in a separate database on the app volume.

Usage and cost are estimates for understanding activity. They are not billing numbers. Missing usage stays unknown.

## Run with Docker

```bash
PUID=$(id -u) PGID=$(id -g) docker compose up --build
```

Open http://127.0.0.1:8080. The port is bound to localhost only.

Compose mounts:

- `~/.claude` at `/sources/claude` (read-only)
- `~/.codex` at `/sources/codex` (read-only)
- `~/.cursor` at `/sources/cursor` (read-only)
- a named volume `obs-data` at `/data`

The process drops to `PUID` and `PGID` before reading transcripts or writing the database. The command above uses your host user's IDs so private transcript folders remain readable. Compose defaults to `502` and `20` when these variables are omitted; those defaults often differ from Linux account IDs.

If a rescan reports `Permission denied` for `/sources/claude` or `/sources/codex`, recreate the container with your host IDs:

```bash
PUID=$(id -u) PGID=$(id -g) docker compose up -d --build --force-recreate obs
```

Source folders must allow that user to read files and traverse directories. A permission failure aborts the scan and preserves the previous index, including during a full rebuild.

To index another folder, add a read-only volume and include the container path in `OBS_SOURCES`:

```yaml
volumes:
  - /path/on/the/host:/sources/extra:ro
environment:
  OBS_SOURCES: /sources/claude,/sources/codex,/sources/extra
```

Each source root maps to an agent by **folder name**: the last path component must be `.claude` or `claude` for Claude Code, `.codex` or `codex` for Codex, and `.cursor` or `cursor` for Cursor. That covers the home folders and Docker mounts at `/sources/claude`, `/sources/codex`, and `/sources/cursor`. Other locations need a symlink or mount with one of those names.

Indexed files outside the configured source roots are removed on every rescan, so test fixtures or old paths do not linger after you change `OBS_SOURCES`.

A rescan reads appended bytes. **Full rebuild** on the Sources page reparses every file. Rebuilding the index does not delete notes, hidden-project preferences, path allows, or benchmark cases.

Codex conversation names are imported from `session_index.jsonl` in each configured Codex source root (normally `~/.codex`). Rescan refreshes renamed conversations even when their transcripts have not changed. Sources containing only transcripts use the first user message as the title. The Codex index is read-only; the app does not open Codex's internal state database.

## Cursor

Cursor Agent JSONL transcripts are imported from `~/.cursor/projects/<workspace>/agent-transcripts/`. Both flat `<id>.jsonl` files and `<id>/<id>.jsonl` directories are supported, including subagents. Messages, thinking, tool inputs, available tool results, and turn completion/error records appear in the timeline and search.

Cursor transcripts often omit timestamps, models, token usage, tool call IDs, and tool outputs. Missing values stay unknown; no cost or duration is inferred from file metadata. Sessions are grouped by the workspace folder name. Its encoding is lossy, so it is not decoded into a project path: path alerts require an explicit `cwd` in the transcript. Legacy text transcripts and history stored only in Cursor's internal SQLite databases (including CLI chat storage) are not imported.

Docker includes Cursor by default. For an existing local setup, add `$HOME/.cursor` to `OBS_SOURCES` in `backend/.env`, restart the backend, and rescan.

Cursor's saved sidebar names are imported by conversation ID from its local metadata databases, opened in read-only mode. Rescan refreshes renames without reparsing transcripts. Local `~/.cursor` sources automatically use Cursor's standard `User` directory: `~/Library/Application Support/Cursor/User` on macOS, `$XDG_CONFIG_HOME/Cursor/User` (default `~/.config/Cursor/User`) on Linux, and `%APPDATA%/Cursor/User` on Windows. Set `OBS_CURSOR_USER_DATA_DIR` or `cursor_user_data_dir` for another installation. Unavailable metadata preserves imported names; unnamed conversations use their first user message.

For Docker, add a read-only mount of that `User` folder at `/sources/cursor/user-data`, for example on macOS:

```yaml
volumes:
  - "${HOME}/Library/Application Support/Cursor/User:/sources/cursor/user-data:ro"
```

Conversation names and recorded creation dates are imported from the databases; transcript content still comes from JSONL files. Creation dates let Cursor sessions appear in daily charts and date filters. Last-update times are not treated as completion times, so duration stays unknown when the transcript has no end time. Sessions without a recorded creation date remain in the session total but are excluded from daily charts.

## What is stored where

| Location | Contents |
|---|---|
| Mounted transcript folders | Source of truth. Never written. |
| `/data/index.db` | Sessions, events, search. Safe to delete; a rescan rebuilds it. |
| `/data/user.db` | Session notes, custom project names, hidden projects, path allows, benchmark cases. |

Use the pencil on a project header in Sessions to change its display name. The name applies to every agent sharing that recorded path. Cursor workspaces without a recorded path join a project when their encoded workspace folder matches exactly one known path; unmatched or ambiguous workspaces remain separate. Renames update `sessions.project_name` in `index.db` and are preserved in `user.db` across rescans and full rebuilds. Renaming does not change paths. The trash icon hides the project's agent entries, with Undo available.

Back up the volume, including `user.db`:

```bash
docker run --rm -v observability-system_obs-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/obs-data.tgz -C /data .
```

The volume name is `<compose-project>_obs-data`. `docker volume ls` shows the exact name.

## Pricing

By default, prices come from OpenRouter's public `https://openrouter.ai/api/v1/models` catalog. No API key is required. The catalog is cached in `openrouter-pricing.json` in the data directory for 24 hours, and refreshed on startup or rescan when stale. Charts read stored estimates without calling OpenRouter. A failed refresh keeps the last successful cache; failures without a cache leave costs unknown and are retried on a later rescan (at most once every five minutes).

Provider prefixes and Claude decimal version names are normalized (`gpt-6.1-sol` → `openai/gpt-6.1-sol`, `claude-sonnet-5-5` → `anthropic/claude-sonnet-5.5`). Unknown models stay unknown. Cache read/write rates and catalog prompt-length pricing tiers are applied where recorded token usage permits. Codex cached input is included in its input count and is charged once. Estimates use current catalog rates, not historical billing rates, and exclude non-token charges such as web search and per-request fees.

Rescans recalculate existing sessions when the pricing table changes, even if transcripts have not changed. Frozen benchmark cases keep their original estimates. Only the public catalog is requested; no transcript content is sent to OpenRouter.

For a manual/offline override, set `OBS_PRICING_FILE` (or `pricing_file` in config) to your own YAML table, such as `pricing.yaml`. That table uses USD per million tokens and longest-prefix matching. It replaces OpenRouter pricing.

## OpenTelemetry

Export is off until `otel.endpoint` is set (or `OBS_OTEL_ENDPOINT`). With an endpoint, ingest sends one trace per session over OTLP/HTTP. Tool calls and their results are one span. Span ids are derived from session and event ids, so a later export updates the same spans.

By default the export is structure and usage only: agent, model, project name, kind, tool name, status, tokens, estimated cost. Prompt text, thinking, tool input, and tool output stay on this machine unless `include_content` is true (`OBS_OTEL_INCLUDE_CONTENT=true`). That flag is what can send transcript text off the machine. A path outside the recorded directory is exported as the boolean `obs.path_outside_cwd`, not as the path. Benchmark cases are not exported.

If the collector is down, ingest still commits. The error is shown on the Sources page and the export is retried on the next scan.

```yaml
otel:
  endpoint: "http://127.0.0.1:4318/v1/traces"
  include_content: false
  protocol: http/protobuf
```

From the host, `127.0.0.1` inside the container is the container itself. Use `host.docker.internal` or a collector on the compose network.

## Path alerts

The check compares paths found in tool calls with the session's recorded project directory. It is lexical: `.` and `..` are collapsed, and the project tree is not mounted, so symlink escapes are not detected. Shell commands are flagged only when they contain an absolute path outside that directory. Sessions with no recorded directory produce no alerts. Allowing a path stores a prefix in `user.db` for that project.

## Benchmark

Freeze a whole session, or a sequence range, from the session page. The case copies the prompt, model, token and cost estimates, a tool and path summary, and the final assistant message. Pass and fail are labels you set. The summary compares models on the cases you froze, which is a biased sample of your work. The app does not call a model provider.

## Local development

Backend (Python 3.12+, [uv](https://docs.astral.sh/uv/)):

```bash
cd backend
uv sync --extra dev
cp .env.example .env   # edit paths and port if needed
uv run obs
```

`backend/.env` is loaded automatically. Defaults are `127.0.0.1:8080` (`OBS_HOST`, `OBS_PORT`). Docker sets `OBS_HOST=0.0.0.0` so the published port works.

Frontend:

```bash
cd frontend
npm install
cp .env.example .env   # match OBS_PORT to the backend
npm run dev
```

The dev server proxies `/api` using `OBS_HOST` and `OBS_PORT` from `frontend/.env`. Open http://127.0.0.1:5173.

Regenerate the OpenAPI types while the API is running:

```bash
npm run gen:api
```

## Tests

```bash
cd backend && uv run pytest
cd frontend && npm test
```
