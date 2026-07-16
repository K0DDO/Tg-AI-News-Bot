"""Attach DB session + user for the lifetime of the handler."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.database import get_session_factory
from app.services.channels import ChannelService
from app.services.whitelist import WhitelistService

_DENIED = (
    "Бот работает в режиме вайтлиста.\n"
    "Доступ выдаёт администратор — напишите ему ваш Telegram ID."
)
_BANNED = "Ваш аккаунт заблокирован администратором."


class DbUserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        session_factory = get_session_factory()
        async with session_factory() as session:
            if user is not None:
                wl = WhitelistService(session)
                if not await wl.can_use_bot(user.id):
                    if isinstance(event, Message):
                        await event.answer(_DENIED)
                    elif isinstance(event, CallbackQuery):
                        await event.answer(_DENIED, show_alert=True)
                    return None

                db_user = await ChannelService(session).get_or_create_user(
                    telegram_id=user.id,
                    username=user.username,
                )
                await session.commit()
                data["db_user"] = db_user
                if getattr(db_user, "is_banned", False):
                    if isinstance(event, Message):
                        await event.answer(_BANNED)
                    elif isinstance(event, CallbackQuery):
                        await event.answer(_BANNED, show_alert=True)
                    return None
            data["session"] = session
            return await handler(event, data)
