from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_debug: bool = False
    log_level: str = "INFO"

    postgres_user: str = "newsbot"
    postgres_password: str = "newsbot"
    postgres_db: str = "newsbot"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    database_url: str | None = None

    bot_token: str = Field(default="", description="Telegram Bot API token")

    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_session_name: str = "news_parser"
    telegram_session_dir: str = "./data/sessions"

    admin_username: str = "admin"
    admin_password: str = "change-me"
    admin_secret_key: str = "change-me"

    parser_poll_interval_seconds: int = 120
    cluster_similarity_threshold: float = 0.68
    cluster_lookback_hours: int = 48
    digest_default_limit: int = 5
    daily_digest_limit: int = 10
    message_retention_days: int = 31

    # hashing | sentence-transformers | auto
    embedding_backend: str = "hashing"
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"

    # heuristic | groq
    ai_provider: str = "heuristic"
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_timeout_seconds: float = 45.0
    # If true, /search asks Groq to synthesize an answer over semantic hits
    ai_search_synthesis: bool = True

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
        """Sync URL for Alembic migrations."""
        url = self.async_database_url
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


@lru_cache
def get_settings() -> Settings:
    return Settings()
