"""Command line entry point: ``windesk fetch | build | serve``."""

from __future__ import annotations

import argparse
import asyncio
import sys

from windesk.config import get_settings
from windesk.logs import configure_logging, get_logger


def _fetch() -> None:
    from windesk.ingest.elexon import ElexonClient  # noqa: PLC0415
    from windesk.ingest.pipeline import fetch_snapshot  # noqa: PLC0415

    s = get_settings()

    async def run() -> None:
        async with ElexonClient(
            s.elexon_base_url, timeout_s=s.http_timeout_s, max_attempts=s.http_max_attempts
        ) as client:
            await fetch_snapshot(
                client, s.seed_dir, s.ingest_start, s.ingest_end, source=s.elexon_base_url
            )

    asyncio.run(run())


def _build() -> None:
    from windesk.store.warehouse import build_warehouse  # noqa: PLC0415

    s = get_settings()
    build_warehouse(s.seed_dir, s.warehouse_path)


def _openapi(out: str) -> None:
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    from windesk.api.app import create_app  # noqa: PLC0415

    spec = create_app().openapi()
    Path(out).write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _serve(host: str, port: int) -> None:
    import uvicorn  # noqa: PLC0415

    s = get_settings()
    uvicorn.run(
        "windesk.api.app:create_app",
        factory=True,
        host=host,
        port=port,
        log_config=None,
        proxy_headers=True,
        reload=s.env == "dev",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="windesk")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("fetch", help="Fetch a fresh raw snapshot from Elexon (network)")
    sub.add_parser("build", help="Build the warehouse from the committed snapshot (offline)")
    openapi = sub.add_parser(
        "openapi", help="Write the OpenAPI spec (for frontend type generation)"
    )
    openapi.add_argument("--out", default="openapi.json")
    serve = sub.add_parser("serve", help="Run the API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    s = get_settings()
    configure_logging(s.log_level, json=s.log_json)
    get_logger(__name__).info("cli.start", command=args.command, env=s.env)

    match args.command:
        case "fetch":
            _fetch()
        case "build":
            _build()
        case "openapi":
            _openapi(args.out)
        case "serve":
            _serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
