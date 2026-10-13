# Setup and sources

How to run the app, which transcript folders it reads, and where its data lives.

## Docker and sources

```bash
docker compose up --build
```

Open http://127.0.0.1:8080. The port is bound to localhost only.

Compose mounts:

- `~/.claude` at `/sources/claude` (read-only)
- `~/.codex` at `/sources/codex` (read-only)
- `~/.cursor` at `/sources/cursor` (read-only)
- a named volume `obs-data` at `/data`

The process drops to `PUID` and `PGID` before reading transcripts or writing the database. Compose defaults to `1000` for both IDs, so hosts with UID and GID `1000` can use `docker compose up -d --build` directly. The command above supplies your host user's IDs for accounts with different IDs.

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

A rescan reads appended bytes. **Full rebuild** on the Sources page reparses every file. Rebuilding the index does not delete notes, hidden-project preferences, path allows, or eval cases.

Codex conversation names are imported from `session_index.jsonl` in each configured Codex source root (normally `~/.codex`). Rescan refreshes renamed conversations even when their transcripts have not changed. Sources containing only transcripts use the first user message as the title. The Codex index is read-only; the app does not open Codex's internal state database.

Claude Code session names come from recorded `custom-title` (`customTitle`) or `ai-title` (`aiTitle`) entries, with custom names taking precedence. Without a saved name, the first user prompt supplies the title; local command notices, output, and slash-command markup are skipped. Sessions with neither a saved name nor a prompt keep their ID as the display fallback.

## Cursor

Cursor Agent JSONL transcripts are imported from `~/.cursor/projects/<workspace>/agent-transcripts/`. Both flat `<id>.jsonl` files and `<id>/<id>.jsonl` directories are supported, including subagents. Messages, thinking, tool inputs, available tool results, and turn completion/error records appear in the timeline and search.

Cursor transcripts often omit timestamps, models, token usage, tool call IDs, and tool outputs. For indexed conversations, available tool results and errors are also imported from Cursor's local SQLite message records, opened read-only. Calls are paired by recorded IDs or compatible tool arguments; results without a safe match remain separate timeline events. Rescan refreshes outcomes even when transcripts have not changed, and unavailable metadata preserves the last imported results. Raw result views include the database path, record key, and saved message. Missing values stay unknown; no cost or duration is inferred from file metadata. Cursor’s recorded workspace path (`workspaceIdentifier.uri.fsPath`) supplies the project directory when the transcript omits `cwd`, enabling path alerts for existing tool calls on rescan. An explicit transcript `cwd` takes precedence. When no recorded path is available, sessions are grouped by the workspace folder name; its lossy encoding is not decoded into a project path. Legacy text transcripts and conversations stored only in Cursor's internal SQLite databases (including CLI chat storage) are not imported.

Docker includes Cursor by default. For an existing local setup, add `$HOME/.cursor` to `OBS_SOURCES` in `backend/.env`, restart the backend, and rescan.

Cursor's saved sidebar names are imported by conversation ID from its local metadata databases, opened in read-only mode. Rescan refreshes renames without reparsing transcripts. Local `~/.cursor` sources automatically use Cursor's standard `User` directory: `~/Library/Application Support/Cursor/User` on macOS, `$XDG_CONFIG_HOME/Cursor/User` (default `~/.config/Cursor/User`) on Linux, and `%APPDATA%/Cursor/User` on Windows. Set `OBS_CURSOR_USER_DATA_DIR` or `cursor_user_data_dir` for another installation. Unavailable metadata preserves imported names; unnamed conversations use their first user message.

For Docker, add a read-only mount of that `User` folder at `/sources/cursor/user-data`, for example on macOS:

```yaml
volumes:
  - "${HOME}/Library/Application Support/Cursor/User:/sources/cursor/user-data:ro"
```

Conversation names and recorded creation dates are imported from the databases; transcript content still comes from JSONL files. Creation dates let Cursor sessions appear in daily charts and date filters. Cursor session duration uses the sum of available recorded `turnDurationMs` values, representing recorded turn time rather than elapsed time between messages. Session lists, duration sorting, and analytics use this value. Last-update times are not treated as completion times; when no turn duration or transcript end time is available, duration stays unknown. Sessions without a recorded creation date remain in the session total but are excluded from daily charts.

Cursor message metadata (`bubbleId:<conversation-id>:<message-id>`, `modelInfo.modelName`) supplies recorded models for session lists and model filters. The current selection (`composerData.modelConfig.modelName`) is shown separately in session details; it is not treated as model history. `default` and `auto` remain unresolved. Rescan refreshes this metadata without reparsing transcripts, and temporarily unavailable databases preserve imported values. Models are not assigned to individual JSONL events because their identities cannot reliably be joined to database messages; token usage and cost remain unknown when absent from the transcript.

## What is stored where

| Location | Contents |
|---|---|
| Mounted transcript folders | Source of truth. Never written. |
| `/data/index.db` | Sessions, events, search. Safe to delete; a rescan rebuilds it. |
| `/data/user.db` | Session notes, custom project names, hidden projects, path allows, eval cases. |

Use the pencil on a project header in Sessions to change its display name. The name applies to every agent sharing that recorded path. Cursor workspaces without a recorded path join a project when their encoded workspace folder matches exactly one known path; unmatched or ambiguous workspaces remain separate. Renames update `sessions.project_name` in `index.db` and are preserved in `user.db` across rescans and full rebuilds. Renaming does not change paths. The trash icon hides the project's agent entries, with Undo available.

Back up the volume, including `user.db`:

```bash
docker run --rm -v observability-system_obs-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/obs-data.tgz -C /data .
```

The volume name is `<compose-project>_obs-data`. `docker volume ls` shows the exact name.
