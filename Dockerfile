FROM node:20-alpine AS web
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.24 /uv /uvx /bin/
WORKDIR /app
COPY backend/ /app/backend/
COPY pricing.yaml /app/pricing.yaml
COPY config.example.yaml /app/config.example.yaml
COPY --from=web /src/frontend/dist /app/frontend/dist
WORKDIR /app/backend
RUN uv sync --frozen --no-dev
ENV OBS_DATA_DIR=/data \
    OBS_STATIC_DIR=/app/frontend/dist \
    OBS_HOST=0.0.0.0 \
    OBS_PORT=8080 \
    PYTHONUNBUFFERED=1
EXPOSE 8080
ENTRYPOINT ["uv", "run", "--no-dev", "python", "-m", "obs.entrypoint"]
