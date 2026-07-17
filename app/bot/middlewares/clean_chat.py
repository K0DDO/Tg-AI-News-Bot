"""Delete the user's reply-keyboard presses so the chat stays clean.

Never deletes the bot's own messages / inline keyboards.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, TelegramObject

# Short pause before deleting — feels smoother than an instant wipe.
_DELETE_DELAY_SEC = 0.55


@lru_cache(maxsize=1)
def _reply_action_texts() -> frozenset[str]:
    """Exact texts of reply-keyboard buttons (user messages only)."""
    from app.bot.i18n import (
        SUPPORTED_LANGS,
        btn_channels,
        btn_favorites,
        btn_feed,
        btn_history,
        btn_search,
        btn_settings,
        btn_trends,
    )

    texts: set[str] = set()
    for lang in SUPPORTED_LANGS:
        texts.update(
            {
                btn_feed(lang),
                btn_search(lang),
                btn_settings(lang),
                btn_trends(lang),
                btn_channels(lang),
                btn_favorites(lang),
                btn_history(lang),
            }
        )
    # Admin reply keyboard (RU-only)
    texts.update(
        {
            "📊 Статистика",
            "📝 Логи",
            "🕸 Граф",
            "🤖 AI",
            "👥 Пользователи",
            "⚙️ Система",
            "🔐 Вайтлист",
            "🔑 Сменить пароль",
            "🚪 Выйти",
            "❌ Отмена",
            "🧪 Диагностика",
            "🔙 Админ-меню",
        }
    )
    return frozenset(texts)


def _is_user_reply_button(message: Message) -> bool:
    """True only for the user's own reply-keyboard press — never a bot message."""
    user = message.from_user
    if user is None or user.is_bot:
        return False
    # Bot UI screens are messages from the bot; ignore anything that isn't plain text
    # from a human matching a known reply button label.
    if message.reply_markup is not None:
        return False
    text = (message.text or "").strip()
    return bool(text) and text in _reply_action_texts()


async def _safe_delete_user_message(message: Message | None) -> None:
    if message is None:
        return
    # Extra safety: never delete a message authored by the bot.
    if message.from_user is not None and message.from_user.is_bot:
        return
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    except Exception:
        pass


async def _delete_later(message: Message | None, delay: float = _DELETE_DELAY_SEC) -> None:
    if message is None:
        return
    try:
        await asyncio.sleep(delay)
        await _safe_delete_user_message(message)
    except Exception:
        pass


class CleanChatMiddleware(BaseMiddleware):
    """
    After handling, soft-delete ONLY the user's reply-keyboard press
    (e.g. «📰 Лента», «⚙️ Настройки»).

    Bot messages and inline keyboards are never touched.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        result = await handler(event, data)

        if data.get("keep_user_message"):
            return result

        # Only Message events from the user pressing a reply button.
        # CallbackQuery events attach to the bot's message — do not delete those.
        if isinstance(event, Message) and _is_user_reply_button(event):
            asyncio.create_task(_delete_later(event))

        return result
