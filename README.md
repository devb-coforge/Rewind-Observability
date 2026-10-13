# Rewind Observability

A full stack web app that indexes local agent transcripts (Claude Code, Codex, Cursor). It has a transcript viewer, a usage tracker, an OpenTelemetry export, path-boundary alerts, and ability to build private evals.

## Quick start

```bash
docker compose up --build
```

Open http://127.0.0.1:8080. The port is bound to localhost only. Transcript folders are mounted read-only; nothing is written to them.

## Documentation

| Topic | Doc |
|---|---|
| Docker, source folders, Cursor import, storage and backups | [docs/setup.md](docs/setup.md) |
| Pricing, OpenTelemetry, path alerts, evals | [docs/features.md](docs/features.md) |
| Local development and tests | [docs/development.md](docs/development.md) |

## License

See [LICENSE](LICENSE).
