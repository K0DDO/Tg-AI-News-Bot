"""Topic trends — scoped to the user's channels."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.i18n import t
from app.bot.keyboards import add_channels_keyboard
from app.bot.ui import format_trends
from app.models import User, UserChannel
from app.services.preferences import FeedService, PreferencesService
from app.services.trends import TrendsService

router = Router(name="trends")


async def _active_channel_count(session: AsyncSession, user_id: int) -> int:
    n = await session.scalar(
        select(func.count()).select_from(UserChannel).where(
            UserChannel.user_id == user_id,
            UserChannel.is_active.is_(True),
        )
    )
    return int(n or 0)


@router.message(Command("trends"))
@router.callback_query(F.data == "nav:trends")
async def trends_handler(event: Message | CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    if await _active_channel_count(session, db_user.id) == 0:
        text = f"📂 {t(lang, 'no_channels_trends')}"
        kb = add_channels_keyboard(lang)
        if isinstance(event, CallbackQuery):
            await event.answer()
            if event.message:
                await event.message.answer(text, reply_markup=kb)
            return
        await event.answer(text, reply_markup=kb)
        return

    event_ids = await FeedService(session).event_ids_for_user(db_user)
    rows = await TrendsService(session).top_topics(limit=8, event_ids=event_ids)
    text = format_trends(lang, rows)
    if isinstance(event, CallbackQuery):
        await event.answer()
        if event.message:
            await event.message.answer(text)
        return
    await event.answer(text)


async def show_trends_msg(message: Message, session: AsyncSession, db_user: User) -> None:
    await trends_handler(message, session, db_user)
