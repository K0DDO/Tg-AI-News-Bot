"""Central application settings — local (.env.local) and production (.env.production)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parents[2]


def resolve_env_files() -> tuple[str, ...]:
    """
    Env file precedence:
      1. BRIEFLY_ENV_FILE / ENV_FILE (explicit path)
      2. .env.production when APP_ENV=production
      3. .env.local (local Windows/dev)
      4. .env (legacy fallback)
    OS environment variables always win over file values.
    """
    explicit = (os.getenv("BRIEFLY_ENV_FILE") or os.getenv("ENV_FILE") or "").strip()
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = _ROOT / path
        return (str(path),) if path.exists() else (explicit,)

    app_env = (os.getenv("APP_ENV") or "").strip().lower()
    files: list[str] = []
    prod = _ROOT / ".env.production"
    local = _ROOT / ".env.local"
    legacy = _ROOT / ".env"

    # Later files override earlier ones (pydantic-settings).
    if app_env == "production":
        if prod.exists():
            files.append(str(prod))
        elif legacy.exists():
            files.append(str(legacy))
    elif local.exists():
        if legacy.exists():
            files.append(str(legacy))
        files.append(str(local))
    elif legacy.exists():
        files.append(str(legacy))
    elif prod.exists():
        # Rare: only production file present while developing
        files.append(str(prod))

    # Empty → Docker Compose / OS env only (no secrets baked into the image)
    return tuple(files)


class Settings(BaseSettings):
    """Central application settings loaded from environment / env files."""

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_debug: bool = False
    log_level: str = "INFO"

    postgres_user: str = "briefly"
    postgres_password: str = "briefly"
    postgres_db: str = "briefly"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    # If set, used as-is. Prefer leaving empty and using POSTGRES_* parts
    # so local (localhost) vs Docker (postgres) both work from the same pattern.
    database_url: str | None = None

    bot_token: str = Field(default="", description="Telegram Bot API token")

    # Comma-separated Telegram numeric IDs (never usernames). First ID may seed OWNER.
    admin_telegram_ids: str = ""
    # Optional dedicated OWNER id; if empty, first ADMIN_TELEGRAM_IDS entry is OWNER.
    owner_telegram_id: int = 0

    favorite_retention_days: int = 365 * 5
    unread_queue_max: int = 50

    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_session_name: str = "news_parser"
    telegram_session_dir: str = "./data/sessions"

    # Redis (FSM + short-lived cache). Empty or unreachable → memory fallback.
    redis_url: str = ""

    admin_username: str = "admin"
    admin_password: str = "change-me"
    admin_secret_key: str = "change-me"

    parser_poll_interval_seconds: int = 120
    cluster_similarity_threshold: float = 0.68
    cluster_lookback_hours: int = 48
    digest_default_limit: int = 5
    daily_digest_limit: int = 10
    message_retention_days: int = 31

    embedding_backend: str = "hashing"
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"

    ai_provider: str = "heuristic"
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_timeout_seconds: float = 45.0
    ai_search_synthesis: bool = True

    logs_dir: str = "./data/logs"

    @field_validator("owner_telegram_id", "telegram_api_id", mode="before")
    @classmethod
    def _empty_int_as_zero(cls, v: object) -> object:
        if v is None or (isinstance(v, str) and not v.strip()):
            return 0
        return v

    @field_validator("database_url", mode="before")
    @classmethod
    def _empty_database_url(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def is_production(self) -> bool:
        return (self.app_env or "").lower() == "production"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def async_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_database_url(self) -> str:
        url = self.async_database_url
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")

    def admin_id_set(self) -> set[int]:
        """Stable Telegram numeric IDs only (no usernames)."""
        out: set[int] = set()
        if self.owner_telegram_id:
            out.add(int(self.owner_telegram_id))
        for part in (self.admin_telegram_ids or "").replace(" ", "").split(","):
            if part.isdigit():
                out.add(int(part))
        return out

    def owner_telegram_id_resolved(self) -> int | None:
        if self.owner_telegram_id:
            return int(self.owner_telegram_id)
        ids = sorted(self.admin_id_set())
        return ids[0] if ids else None


@lru_cache
def get_settings() -> Settings:
    files = resolve_env_files()
    return Settings(_env_file=files if files else None)


def clear_settings_cache() -> None:
    get_settings.cache_clear()
