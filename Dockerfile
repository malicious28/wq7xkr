# syntax=docker/dockerfile:1.7
#
# One image, one process, one origin: FastAPI serves the JSON API under /api
# and the built React app at /. The warehouse is built from the committed raw
# snapshot at image build time, so the container needs no network access to
# Elexon and every deploy of the same commit shows identical numbers.

# --- 1. frontend build --------------------------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Sourcemaps stay in local builds for debugging; the image does not ship them.
RUN npm run build && find dist -name '*.map' -delete

# --- 2. backend dependencies + warehouse ---------------------------------------------------
# DuckDB (the `build` group) validates the warehouse here and is then removed, so the
# runtime venv holds only what the API imports.
FROM python:3.13-slim AS backend
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first, in their own layer, so code changes don't reinstall them.
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-default-groups --group build --no-install-project
COPY backend/src ./src
COPY backend/data/seed ./data/seed
RUN uv sync --frozen --no-default-groups --group build \
 && .venv/bin/windesk build \
 && uv sync --frozen --no-default-groups \
 && rm -f data/warehouse.duckdb

# --- 3. runtime -----------------------------------------------------------------------------
FROM python:3.13-slim AS runtime
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=backend --chown=app:app /app /app
COPY --from=frontend --chown=app:app /app/frontend/dist /app/static

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    WINDESK_ENV=prod \
    WINDESK_LOG_JSON=true \
    WINDESK_STATIC_DIR=/app/static \
    PORT=8000

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz', timeout=2)"

# Heroku injects $PORT; proxy headers are trusted because the router terminates TLS.
CMD ["sh", "-c", "exec uvicorn windesk.api.app:create_app --factory --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --no-access-log"]
