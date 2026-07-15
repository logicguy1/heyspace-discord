"""Typed application configuration loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration, validated on load.

    Values are read from environment variables (case-insensitive) and, for local
    development, from a `.env` file in the project root.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Discord
    discord_token: str = Field(..., description="Bot token from the Discord developer portal")
    guild_id: int = Field(..., description="The single guild this bot serves")

    # Database — must be an async driver URL, e.g. postgresql+asyncpg://...
    database_url: str = Field(..., description="Async SQLAlchemy database URL")

    # Logging
    log_level: str = Field("INFO", description="Root log level")


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings singleton."""
    return Settings()  # type: ignore[call-arg]
