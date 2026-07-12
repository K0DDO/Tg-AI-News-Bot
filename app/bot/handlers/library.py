"""Favorites and history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.i18n import t
from app.bot.keyboards import history_keyboard
from app.bot.states import HistoryStates
from app.bot.ui import format_feed
from app.models import User
from app.services.preferences import FeedService, PreferencesService
from app.services.translation import ensure_translation

router = Router(name="library")


async def _render_history(
    target: Message,
    session: AsyncSession,
    user: User,
    *,
    days: int | None = None,
    query: str | None = None,
) -> None:
    lang = await PreferencesService(session).lang(user)
    since = None
    if days and days > 0:
        since = datetime.now(timezone.utc) - timedelta(days=days)
    items = await FeedService(session).list_history(user, since=since, query=query)
    for n in items:
        await ensure_translation(session, n, lang)
    if not items:
        text = t(lang, "empty_history")
    else:
        text = format_feed(lang, items[:15], title_key="history", empty_key="empty_history")
    await target.answer(text, reply_markup=history_keyboard(lang), disable_web_page_preview=True)


async def show_favorites(message: Message, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    items = await FeedService(session).list_favorites(db_user)
    for n in items:
        await ensure_translation(session, n, lang)
    if not items:
        await message.answer(t(lang, "empty_favorites"))
        return
    await message.answer(
        format_feed(lang, items[:10], title_key="favorites", empty_key="empty_favorites"),
        disable_web_page_preview=True,
    )


async def show_history(message: Message, session: AsyncSession, db_user: User) -> None:
    await _render_history(message, session, db_user)


@router.message(Command("favorites", "saved"))
async def cmd_fav(message: Message, session: AsyncSession, db_user: User) -> None:
    await show_favorites(message, session, db_user)


@router.message(Command("history"))
async def cmd_hist(message: Message, session: AsyncSession, db_user: User) -> None:
    await show_history(message, session, db_user)


@router.callback_query(F.data.startswith("hist:d:"))
async def hist_filter(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    days = int(callback.data.split(":")[2])
    await callback.answer()
    if callback.message:
        await _render_history(callback.message, session, db_user, days=None if days == 0 else days)


@router.callback_query(F.data == "hist:search")
async def hist_search_ask(callback: CallbackQuery, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await state.set_state(HistoryStates.waiting_query)
    await callback.answer()
    if callback.message:
        await callback.message.answer(t(lang, "hist_search_ask"))


@router.message(HistoryStates.waiting_query)
async def hist_search_run(message: Message, session: AsyncSession, state: FSMContext, db_user: User) -> None:
    query = (message.text or "").strip()
    await state.clear()
    if not query or query.startswith("/"):
        return
    await _render_history(message, session, db_user, query=query)
