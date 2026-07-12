"""Home screen, onboarding, main reply navigation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import (
    BTN_CHANNELS,
    BTN_NEWS,
    BTN_SEARCH,
    BTN_SETTINGS,
    BTN_TRENDS,
    home_keyboard,
    main_menu,
    onboarding_keyboard,
)
from app.bot.ui import ONBOARDING_STEPS, format_home
from app.models import Message as DbMessage
from app.models import News, User
from app.services.preferences import PreferencesService

router = Router(name="home")

BANNER_PATH = Path(__file__).resolve().parents[1] / "assets" / "welcome.png"


async def _today_stats(session: AsyncSession) -> tuple[int, int, float, datetime | None]:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    messages = await session.scalar(
        select(func.count()).select_from(DbMessage).where(DbMessage.created_at >= since)
    )
    news_count = await session.scalar(
        select(func.count()).select_from(News).where(News.created_at >= since)
    )
    avg = await session.scalar(
        select(func.avg(News.importance_score)).where(News.created_at >= since)
    )
    last = await session.scalar(select(func.max(News.updated_at)))
    return int(messages or 0), int(news_count or 0), float(avg or 0), last


async def send_home(message: Message, session: AsyncSession, user: User) -> None:
    prefs = PreferencesService(session)
    settings = await prefs.get_or_create(user)
    msgs, news_n, avg, last = await _today_stats(session)
    text = format_home(
        messages=msgs,
        news=news_n,
        avg_importance=avg,
        last_update=last,
    )
    if not settings.welcome_seen and BANNER_PATH.exists():
        await message.answer_photo(
            FSInputFile(BANNER_PATH),
            caption=text,
            reply_markup=home_keyboard(),
        )
        await prefs.mark_welcome_seen(user)
    else:
        await message.answer(text, reply_markup=home_keyboard())
        if not settings.welcome_seen:
            await prefs.mark_welcome_seen(user)


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, db_user: User) -> None:
    await message.answer("Главное меню всегда под рукой ↓", reply_markup=main_menu())
    await send_home(message, session, db_user)


@router.message(Command("menu"))
@router.callback_query(F.data == "nav:home")
async def go_home(event: Message | CallbackQuery, session: AsyncSession, db_user: User) -> None:
    if isinstance(event, CallbackQuery):
        await event.answer()
        if event.message:
            await send_home(event.message, session, db_user)
        return
    await send_home(event, session, db_user)


@router.callback_query(F.data.startswith("onb:"))
async def onboarding(callback: CallbackQuery) -> None:
    step = int(callback.data.split(":")[1])
    await callback.answer()
    if step < 0 or step >= len(ONBOARDING_STEPS):
        return
    title, body = ONBOARDING_STEPS[step]
    text = f"<b>{title}</b>\n\n{body}"
    if callback.message:
        await callback.message.answer(
            text,
            reply_markup=onboarding_keyboard(step, len(ONBOARDING_STEPS)),
        )


# Reply keyboard stubs are handled in dedicated routers via F.text filters
