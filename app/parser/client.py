"""Telethon client wrapper — Stage 4."""

from pathlib import Path

from telethon import TelegramClient

from app.config import get_settings


def create_telegram_client() -> TelegramClient:
    settings = get_settings()
    session_dir = Path(settings.telegram_session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = session_dir / settings.telegram_session_name
    return TelegramClient(
        str(session_path),
        settings.telegram_api_id,
        settings.telegram_api_hash,
    )
