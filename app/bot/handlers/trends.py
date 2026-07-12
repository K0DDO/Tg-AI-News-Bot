"""Trends screen."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import BTN_TRENDS
from app.bot.ui import format_trends
from app.services.trends import TrendsService

router = Router(name="trends")


@router.message(F.text == BTN_TRENDS)
@router.message(Command("trends"))
@router.callback_query(F.data == "nav:trends")
async def show_trends(event: Message | CallbackQuery, session: AsyncSession) -> None:
    topics = await TrendsService(session).top_topics(limit=8)
    text = format_trends(topics)
    if isinstance(event, CallbackQuery):
        await event.answer()
        if event.message:
            await event.message.answer(text)
        return
    await event.answer(text)
