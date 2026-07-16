"""Favorites and history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import ceil

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.i18n import t
from app.bot.keyboards import detail_keyboard, history_keyboard
from app.bot.states import HistoryStates
from app.bot.ui import format_feed, format_history_list, format_news_detail
from app.models import User
from app.services.digest import NewsService
from app.services.events import BriefBuilderService
from app.services.preferences import FeedService, PreferencesService
from app.services.translation import ensure_translation

router = Router(name="library")
_briefs = BriefBuilderService()
_PAGE = 10


async def _render_history(
    target: Message,
    session: AsyncSession,
    user: User,
    *,
    days: int = 0,
    page: int = 0,
    query: str | None = None,
    edit: bool = False,
) -> None:
    lang = await PreferencesService(session).lang(user)
    since = None
    if days and days > 0:
        since = datetime.now(timezone.utc) - timedelta(days=days)
    offset = max(0, page) * _PAGE
    rows, total = await FeedService(session).list_history(
        user, limit=_PAGE, offset=offset, since=since, query=query
    )
    for event, _st in rows:
        await ensure_translation(session, event, lang)
    total_pages = max(1, ceil(total / _PAGE) if total else 1)
    page = max(0, min(page, total_pages - 1))
    text = format_history_list(lang, rows, total=total, page=page, page_size=_PAGE)
    kb_items = [(e.id, e.title or f"#{e.id}") for e, _ in rows]
    q_token = (query or "").replace(":", " ")[:40] or "-"
    kb = history_keyboard(
        lang,
        kb_items,
        days=days,
        page=page,
        total_pages=total_pages,
        query_token=q_token,
    )
    if edit:
        try:
            await target.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
            return
        except Exception:
            pass
    await target.answer(text, reply_markup=kb, disable_web_page_preview=True)


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
    parts = callback.data.split(":")
    # hist:d:days:page[:query]
    days = int(parts[2]) if len(parts) > 2 else 0
    page = int(parts[3]) if len(parts) > 3 else 0
    query = parts[4] if len(parts) > 4 and parts[4] != "-" else None
    await callback.answer()
    if callback.message:
        await _render_history(
            callback.message,
            session,
            db_user,
            days=days,
            page=page,
            query=query,
            edit=True,
        )


@router.callback_query(F.data == "hist:search")
async def hist_search_ask(
    callback: CallbackQuery, session: AsyncSession, db_user: User, state: FSMContext
) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await state.set_state(HistoryStates.waiting_query)
    await callback.answer()
    if callback.message:
        await callback.message.answer(t(lang, "hist_search_ask"))


@router.message(HistoryStates.waiting_query)
async def hist_search_run(
    message: Message, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    query = (message.text or "").strip()
    await state.clear()
    if not query or query.startswith("/"):
        return
    await _render_history(message, session, db_user, query=query)


@router.callback_query(F.data.startswith("hist:open:"))
async def hist_open(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    event_id = int(callback.data.split(":")[2])
    lang = await PreferencesService(session).lang(db_user)
    us = await PreferencesService(session).get_or_create(db_user)
    news = await NewsService(session).get_event(event_id)
    await callback.answer()
    if not news or not callback.message:
        return
    # Ensure it stays in history (already read)
    await FeedService(session).mark_read(db_user, news)
    await ensure_translation(session, news, us.news_language or lang)
    brief = _briefs.build(news, lang=us.news_language or lang, show_summary=us.show_summary)
    await callback.message.answer(
        format_news_detail(lang, brief, index=1, total=1, show_summary=us.show_summary),
        reply_markup=detail_keyboard(
            lang, offset=0, index=0, total=1, news_id=news.id, ids_s=str(news.id)
        ),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("hist:fav:"))
async def hist_fav(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    event_id = int(callback.data.split(":")[2])
    news = await NewsService(session).get_event(event_id)
    lang = await PreferencesService(session).lang(db_user)
    if not news:
        await callback.answer()
        return
    saved = await FeedService(session).toggle_favorite(db_user, news)
    await callback.answer(t(lang, "saved") if saved else t(lang, "save"))


@router.callback_query(F.data.startswith("hist:del:"))
async def hist_del(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    event_id = int(callback.data.split(":")[2])
    news = await NewsService(session).get_event(event_id)
    lang = await PreferencesService(session).lang(db_user)
    if news:
        await FeedService(session).remove_from_history(db_user, news)
    await callback.answer(t(lang, "hist_remove"))
    if callback.message:
        await _render_history(callback.message, session, db_user, edit=True)
