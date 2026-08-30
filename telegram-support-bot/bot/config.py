"""Environment-driven configuration. Secrets must never be hardcoded."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from bot.exceptions import ConfigurationError

# Project root (parent of the `bot` package).
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and optional `.env`."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    bot_token: str = Field(..., min_length=20, description="Telegram bot token")
    group_chat_id: int
    admin_ids: list[int]
    bot_username: str = "oz_support_bot"
    morning_time_utc: str = "03:00"

    database_url: str = "sqlite:///support.db"

    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    ai_model: str = "deepseek-chat"
    ai_question_max_length: int = 500

    log_level: str = "INFO"
    log_file: str = "logs/bot.log"
    log_max_bytes: int = 5_242_880
    log_backup_count: int = 5

    commands_file: Path = BASE_DIR / "commands.yaml"

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, value: Any) -> list[int]:
        if isinstance(value, int):
            return [value]
        if isinstance(value, str):
            parts = [item.strip() for item in value.split(",") if item.strip()]
            return [int(item) for item in parts]
        return value

    @field_validator("deepseek_api_key", mode="before")
    @classmethod
    def _empty_key_to_none(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _reject_placeholder_token(self) -> Settings:
        token = self.bot_token.strip()
        if token.lower() in {"changeme", "your_token_here"}:
            raise ConfigurationError("BOT_TOKEN is a placeholder; set a real token.")
        return self

    @property
    def sqlalchemy_url(self) -> str:
        """Return DATABASE_URL with relative SQLite paths resolved against the project root."""
        url = self.database_url
        if not url.startswith("sqlite:///"):
            return url
        rest = url[len("sqlite:///"):]
        # Unix absolute (sqlite:////tmp/db) or Windows drive (sqlite:///C:/...).
        is_absolute = rest.startswith("/") or (len(rest) > 1 and rest[1] == ":")
        if is_absolute:
            return url
        resolved = (BASE_DIR / rest).resolve().as_posix()
        return f"sqlite:///{resolved}"

    @property
    def log_path(self) -> Path:
        path = Path(self.log_file)
        if not path.is_absolute():
            path = BASE_DIR / path
        return path

    def is_admin(self, user_id: int | None) -> bool:
        """Return True if the Telegram user may run admin commands."""
        return user_id is not None and user_id in self.admin_ids


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once. Raises ValidationError if required fields are missing."""
    return Settings()
