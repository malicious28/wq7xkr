"""FastAPI application factory.

One process serves the JSON API under ``/api`` and, in production, the built
React app at ``/`` (single origin: no CORS, one deploy).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from windesk import __version__
from windesk.api.routes.analytics import router as analytics_router
from windesk.config import Settings, get_settings
from windesk.logs import configure_logging, get_logger
from windesk.services.analytics import Analytics
from windesk.store.repository import load_warehouse, serving_dir

log = get_logger(__name__)

# Cheap hardening for a public, read-only app: no MIME sniffing, no framing,
# no referrer leakage, and no access to device features the app never uses.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def _load(settings: Settings) -> Analytics:
    if not (serving_dir(settings.warehouse_path) / "meta.parquet").exists():
        # Dev convenience only: the image is built with the warehouse in place, and
        # DuckDB (needed to build) is not installed at runtime.
        from windesk.store.warehouse import build_warehouse  # noqa: PLC0415

        log.warning("warehouse.missing_building", path=str(settings.warehouse_path))
        build_warehouse(settings.seed_dir, settings.warehouse_path)
    return Analytics(load_warehouse(settings.warehouse_path), settings)


def create_app(settings: Settings | None = None, analytics: Analytics | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.analytics = analytics or _load(settings)
        if analytics is None:  # injected instances (tests) manage their own state
            started = time.perf_counter()
            app.state.analytics.prewarm()
            log.info("analytics.prewarmed", ms=round((time.perf_counter() - started) * 1000))
        log.info("app.ready", data_version=app.state.analytics.data.data_version, env=settings.env)
        yield

    app = FastAPI(
        title="Wind Forecast Desk API",
        version=__version__,
        summary="Point-in-time GB wind forecasts and their measured accuracy.",
        lifespan=lifespan,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    if settings.env == "dev":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers.update(SECURITY_HEADERS)
        if request.url.path.startswith("/api"):
            if response.status_code == 200:  # never let a browser cache an error
                response.headers["Cache-Control"] = "public, max-age=300"
            log.info(
                "http.request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                ms=round(elapsed_ms, 1),
                request_id=request_id,
            )
        return response

    @app.get("/healthz", tags=["ops"])
    def healthz(request: Request) -> dict[str, str]:
        a: Analytics = request.app.state.analytics
        return {"status": "ok", "version": __version__, "data_version": a.data.data_version}

    app.include_router(analytics_router)

    if settings.static_dir is not None:
        _mount_spa(app, settings.static_dir)
    return app


def _mount_spa(app: FastAPI, static_dir: Path) -> None:
    """Serve the built SPA; unknown non-API paths fall back to index.html."""
    index = static_dir / "index.html"
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):  # unknown API path: JSON 404, not the SPA
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (static_dir / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(static_dir.resolve()):
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
