"""Topic trends."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.ui import format_trends
from app.models import User
from app.services.preferences import PreferencesService
from app.services.trends import TrendsService

router = Router(name="trends")


@router.message(Command("trends"))
@router.callback_query(F.data == "nav:trends")
async def trends_handler(event: Message | CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    rows = await TrendsService(session).top_topics(limit=8)
    text = format_trends(lang, rows)
    if isinstance(event, CallbackQuery):
        await event.answer()
        if event.message:
            await event.message.answer(text)
        return
    await event.answer(text)


async def show_trends_msg(message: Message, session: AsyncSession, db_user: User) -> None:
    await trends_handler(message, session, db_user)
