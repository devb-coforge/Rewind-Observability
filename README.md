# Obs

A single-user web app that indexes local Claude Code and Codex CLI transcripts. It is a transcript viewer, a usage tracker, an OpenTelemetry export, path-boundary alerts, and a private benchmark. The transcript files stay read-only. Notes, hidden projects, path allows, and benchmark cases live in a separate database on the app volume.

Usage and cost are estimates for understanding activity. They are not billing numbers. Missing usage stays unknown.

## Run with Docker

```bash
docker compose up --build
```

Open http://127.0.0.1:8080. The port is bound to localhost only.

Compose mounts:

- `~/.claude` at `/sources/claude` (read-only)
- `~/.codex` at `/sources/codex` (read-only)
- a named volume `obs-data` at `/data`

Set `PUID` and `PGID` if they are not `502` and `20`. The process drops to that user before it writes the database.

To index another folder, add a read-only volume and include the container path in `OBS_SOURCES`:

```yaml
volumes:
  - /path/on/the/host:/sources/extra:ro
environment:
  OBS_SOURCES: /sources/claude,/sources/codex,/sources/extra
```

Each root can name its agent in `config.yaml` (`claude_code` or `codex`) or leave detection to the adapters. Copy `config.example.yaml` and set `OBS_CONFIG` to that file if you prefer a file over the environment variable.

A rescan reads appended bytes. **Full rebuild** on the Sources page reparses every file. Rebuilding the index does not delete notes, hidden-project preferences, path allows, or benchmark cases.

## What is stored where

| Location | Contents |
|---|---|
| Mounted transcript folders | Source of truth. Never written. |
| `/data/index.db` | Sessions, events, search. Safe to delete; a rescan rebuilds it. |
| `/data/user.db` | Session notes, hidden projects, path allows, benchmark cases. |

Back up the volume, including `user.db`:

```bash
docker run --rm -v observability-system_obs-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/obs-data.tgz -C /data .
```

The volume name is `<compose-project>_obs-data`. `docker volume ls` shows the exact name.

## Pricing

`pricing.yaml` is USD per million tokens. A model matches the longest key it equals or continues with `-`. Models with no entry show as unknown cost. Point `OBS_PRICING_FILE` at your own table to override it.

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
OBS_SOURCES="$HOME/.claude,$HOME/.codex" \
OBS_DATA_DIR=../data \
uv run uvicorn obs.main:app --factory --host 127.0.0.1 --port 8080
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

The dev server proxies `/api` to port 8080. Open http://127.0.0.1:5173.

Regenerate the OpenAPI types while the API is running:

```bash
npm run gen:api
```

## Tests

```bash
cd backend && uv run pytest
cd frontend && npm test
```
