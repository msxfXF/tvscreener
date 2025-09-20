"""Configuration handling for the monitoring service."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the monitoring service."""

    interval_seconds: int = Field(
        600,
        ge=60,
        description="Interval in seconds between two data fetch cycles.",
    )
    range_start: int = Field(
        0,
        ge=0,
        description="Start index for the TradingView screener range.",
    )
    range_end: int = Field(
        150,
        gt=0,
        description="End index (exclusive) for the TradingView screener range.",
    )
    db_path: str = Field(
        "/app/data/monitor.db",
        description="Path to the SQLite database used to persist snapshots.",
    )
    log_level: str = Field(
        "INFO",
        description="Logging level for the monitoring service.",
    )
    max_retries: int = Field(
        3,
        ge=0,
        description="Maximum number of retries for failed data fetch attempts.",
    )
    retry_backoff_seconds: int = Field(
        30,
        ge=0,
        description="Base backoff in seconds between retry attempts.",
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def _validate_range(cls, values: "Settings") -> "Settings":  # type: ignore[override]
        if values.range_end <= values.range_start:
            raise ValueError("range_end must be greater than range_start")
        return values

    @property
    def database_path(self) -> Path:
        """Return the expanded database path ensuring the parent directory exists."""

        path = Path(self.db_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def as_range(self) -> Tuple[int, int]:
        """Return the configured TradingView range as a tuple."""

        return self.range_start, self.range_end

    def log_level_upper(self) -> str:
        """Return the logging level in upper case for logging configuration."""

        return self.log_level.upper()


__all__ = ["Settings"]
