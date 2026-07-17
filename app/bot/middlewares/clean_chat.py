"""Delete reply-keyboard action presses so the chat stays clean."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message, TelegramObject


@lru_cache(maxsize=1)
def _reply_action_texts() -> frozenset[str]:
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
    # Admin reply keyboard (Russian labels — admin UI is RU-only)
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


async def _safe_delete_message(message: Message | None) -> None:
    if message is None:
        return
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    except Exception:
        pass


class CleanChatMiddleware(BaseMiddleware):
    """
    After a handler finishes:
    - reply-keyboard presses → delete the user's button message
    - inline callbacks → delete the pressed message if UI moved elsewhere
      or if the handler set data['drop_callback_message']=True
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

        if isinstance(event, Message):
            text = (event.text or "").strip()
            if text and text in _reply_action_texts():
                await _safe_delete_message(event)
            return result

        if isinstance(event, CallbackQuery) and event.message is not None:
            if data.get("drop_callback_message"):
                await _safe_delete_message(event.message)
                return result

            session = data.get("session")
            db_user = data.get("db_user")
            if session is not None and db_user is not None:
                try:
                    from app.services.preferences import PreferencesService

                    _, ui_msg_id = await PreferencesService(session).get_ui_message(db_user)
                    pressed_id = int(event.message.message_id)
                    if ui_msg_id and int(ui_msg_id) != pressed_id:
                        await _safe_delete_message(event.message)
                except Exception:
                    pass
        return result
