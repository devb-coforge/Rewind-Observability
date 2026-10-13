# Local development and tests

Backend (Python 3.12+, [uv](https://docs.astral.sh/uv/)):

```bash
cd backend
uv sync --extra dev
cp .env.example .env   # edit paths and port if needed
uv run obs
```

`backend/.env` is loaded automatically for local development. Defaults are `127.0.0.1:8080` (`OBS_HOST`, `OBS_PORT`). Docker excludes local `.env` files and sets `OBS_HOST=0.0.0.0` and `OBS_PORT=8080` to match the published port. Open the Docker app at http://127.0.0.1:8080; `0.0.0.0` is the server's listening address.

Frontend:

```bash
cd frontend
npm install
cp .env.example .env   # match OBS_PORT to the backend
npm run dev
```

The dev server proxies `/api` using `OBS_HOST` and `OBS_PORT` from `frontend/.env`. Open http://127.0.0.1:5173.

## Tests

```bash
cd backend && uv run pytest tests/
cd backend && uv run pytest tests/ --cov=obs --cov-report=term-missing
cd frontend && npm test
```

Backend coverage needs the `dev` extra (`uv sync --extra dev`). The second command prints per-file line coverage and a total percentage for the `obs` package.

## Backend organization

The backend lives in `backend/src/obs`:

- `api/endpoints/` groups routes by feature. `api/routes.py` assembles them under `/api`; request models live in `api/schemas.py`.
- `adapters/` contains transcript adapters, their registry, and the `Adapter` protocol in `interface.py`. Every adapter implements discovery, parsing, and `read_metadata()`.
- `ingest/` coordinates indexing and metadata refresh through that common adapter interface.
- `db/` groups persistence operations by responsibility: files, events, sessions, projects, preferences, and boundaries. `Store` in `db/repo.py` owns the connections, schema setup, and transaction scope, and delegates to those modules. Repository functions reuse its connections; callers wrap writes in `store.transaction()`.
- `db/serialization.py` converts parsed events into database rows and stored rows into response dictionaries.
- `analytics/` contains queries, pricing, usage decoding, duration calculations, and session summary recomputation.
- `shared/` contains reusable file discovery, source detection, JSONL, and transcript parsing helpers.
