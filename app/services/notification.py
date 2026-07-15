"""Telegram notifications via aiogram Bot."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import Message

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, bot: Bot | None = None) -> None:
        self._bot = bot

    async def notify_user(self, telegram_id: int, text: str) -> Message | None:
        """Send plain/HTML text to a Telegram user. Returns Message or None."""
        return await self.send_html(telegram_id, text)

    async def send_html(self, chat_id: int, text: str) -> Message | None:
        if self._bot is None:
            logger.info("notify chat_id=%s (no bot): %s", chat_id, (text or "")[:120])
            return None
        try:
            return await self._bot.send_message(chat_id, text, parse_mode="HTML")
        except Exception:
            logger.exception("failed to notify chat_id=%s", chat_id)
            return None
