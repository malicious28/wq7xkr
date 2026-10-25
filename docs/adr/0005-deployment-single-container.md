# ADR 0005: One container, one origin, on Heroku's container stack

- Status: accepted
- Date: 2026-10-25

## Decision

A multi-stage `Dockerfile`:

1. `node:22-slim` builds the React app;
2. `python:3.13-slim` + uv installs locked dependencies and **builds the warehouse from the committed snapshot**;
3. a slim runtime runs `uvicorn` as a non-root user. FastAPI serves `/api/*` and the SPA (with history fallback) from the same origin.

`heroku.yml` deploys that same image. Configuration comes from environment variables (`WINDESK_*`, `PORT`). Logs are JSON with request IDs. `/healthz` reports the `data_version`.

## Why not Vercel

- Vercel would host the static frontend well, but the Python backend would become serverless functions with the warehouse rebuilt or bundled per function. That is a poor fit for the "use Docker" requirement.
- A split deploy means two URLs, CORS, and two release processes.

## Consequences

- Same artefact locally (`docker compose up`), in CI (built and smoke-tested on every push) and in production.
- Heroku Eco dynos sleep after 30 minutes idle, so the first request can take about 10 s. A Basic dyno avoids this for reviews.
- The image is self-contained: it needs no outbound network access.
