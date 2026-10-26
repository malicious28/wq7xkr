"""Runtime settings, read from environment variables (prefix ``WINDESK_``).

Every tunable lives here so that nothing environment-specific is hard-coded
elsewhere. Defaults reproduce the deployed demo exactly.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WINDESK_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"
    log_json: bool = False

    elexon_base_url: str = "https://data.elexon.co.uk/bmrs/api/v1"
    http_timeout_s: float = 60.0
    http_max_attempts: int = 5

    seed_dir: Path = _BACKEND_ROOT / "data" / "seed"
    warehouse_path: Path = _BACKEND_ROOT / "data" / "warehouse.duckdb"
    static_dir: Path | None = Field(
        default=None, description="Built frontend to serve at '/'. Unset in dev (Vite serves it)."
    )

    # Ingest window. Decisions in January 2026 cover delivery 2 Jan - 1 Feb; December is
    # fetched too so that trailing statistics on 1 Jan use only genuinely past data.
    ingest_start: date = date(2025, 12, 1)
    ingest_end: date = date(2026, 2, 1)

    # Analysis scope (inclusive, UK local dates of the *decision* day).
    decision_start: date = date(2026, 1, 1)
    decision_end: date = date(2026, 1, 31)

    # Live mode ('Try now'): days from this date onward are fetched from Elexon on demand.
    live_start: date = date(2026, 10, 1)
    live_enabled: bool = True

    # Trailing window used for out-of-sample error bands and bias correction.
    trailing_days: int = 28
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
