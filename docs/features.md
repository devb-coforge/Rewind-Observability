# Features

Cost estimates, OpenTelemetry export, path alerts, and evals.

## Pricing

By default, prices come from OpenRouter's public `https://openrouter.ai/api/v1/models` catalog. No API key is required. The catalog is cached in `openrouter-pricing.json` in the data directory for 24 hours, and refreshed on startup or rescan when stale. Charts read stored estimates without calling OpenRouter. A failed refresh keeps the last successful cache; failures without a cache leave costs unknown and are retried on a later rescan (at most once every five minutes).

Provider prefixes and Claude decimal version names are normalized (`gpt-6.1-sol` → `openai/gpt-6.1-sol`, `claude-sonnet-5-5` → `anthropic/claude-sonnet-5.5`). Unknown models stay unknown. Cache read/write rates and catalog prompt-length pricing tiers are applied where recorded token usage permits. Codex cached input is included in its input count and is charged once. Estimates use current catalog rates, not historical billing rates, and exclude non-token charges such as web search and per-request fees.

Rescans recalculate existing sessions when the pricing table changes, even if transcripts have not changed. Frozen benchmark cases keep their original estimates. Only the public catalog is requested; no transcript content is sent to OpenRouter.

For a manual/offline override, set `OBS_PRICING_FILE` (or `pricing_file` in config) to your own YAML table, such as `pricing.yaml`. That table uses USD per million tokens and longest-prefix matching. It replaces OpenRouter pricing.

## OpenTelemetry

Export is off until `otel.endpoint` is set (or `OBS_OTEL_ENDPOINT`). With an endpoint, ingest sends one trace per session over OTLP/HTTP. Tool calls and their results are one span. Span ids are derived from session and event ids, so a later export updates the same spans.

By default the export is structure and usage only: agent, model, project name, kind, tool name, status, tokens, estimated cost. Prompt text, thinking, tool input, and tool output stay on this machine unless `include_content` is true (`OBS_OTEL_INCLUDE_CONTENT=true`). That flag is what can send transcript text off the machine. A path outside the recorded directory is exported as the boolean `obs.path_outside_cwd`, not as the path. Eval cases are not exported.

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

## Evals

Freeze a whole session, or a sequence range, from the session page. The case copies the prompt, model, token and cost estimates, a tool and path summary, and the final assistant message. Pass and fail are labels you set. The summary compares models on the cases you froze, which is a biased sample of your work. The app does not call a model provider.

Eval cards show the saved session title without prompt previews or tool-path badges. The prompt and final message are available under Show detail. If event models are absent and the session has exactly one recorded model, that model is copied into the case; the current model selection is not used. Multiple recorded models without event attribution leave the case model unknown. Rescan fills missing titles and unambiguous models on existing cases while preserving their prompts, verdicts, notes, and previously saved metadata.
