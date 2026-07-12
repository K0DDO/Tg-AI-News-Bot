"""Single-message news feed + detail carousel."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import (
    BTN_NEWS,
    detail_keyboard,
    feed_keyboard,
    sources_keyboard,
)
from app.bot.ui import format_feed, format_news_detail, format_sources_screen
from app.config import get_settings
from app.models import User
from app.services.digest import NewsService
from app.services.preferences import FeedService, PreferencesService
from app.services.reactions import ReactionService

router = Router(name="news")


async def _render_feed(
    target: Message,
    session: AsyncSession,
    user: User,
    *,
    offset: int = 0,
    edit: bool = False,
) -> None:
    settings = get_settings()
    limit = settings.digest_default_limit
    feed = FeedService(session)
    items = await feed.get_feed(user, limit=limit, offset=offset)
    text = format_feed(items, offset=offset)
    ids = [n.id for n in items]
    has_more = len(items) == limit
    kb = feed_keyboard(offset=offset, page_ids=ids, has_more=has_more and bool(items))

    prefs = PreferencesService(session)
    if edit and target.message_id:
        try:
            await target.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
            await prefs.save_digest_message(user, target.chat.id, target.message_id)
            return
        except TelegramBadRequest:
            pass

    # try edit stored digest message
    us = await prefs.get_or_create(user)
    if us.digest_chat_id and us.digest_message_id and target.bot:
        try:
            await target.bot.edit_message_text(
                chat_id=us.digest_chat_id,
                message_id=us.digest_message_id,
                text=text,
                reply_markup=kb,
                disable_web_page_preview=True,
            )
            return
        except TelegramBadRequest:
            pass

    sent = await target.answer(text, reply_markup=kb, disable_web_page_preview=True)
    await prefs.save_digest_message(user, sent.chat.id, sent.message_id)


@router.message(F.text == BTN_NEWS)
@router.message(Command("digest", "daily", "news"))
@router.callback_query(F.data == "nav:news")
async def open_news(event: Message | CallbackQuery, session: AsyncSession, db_user: User) -> None:
    if isinstance(event, CallbackQuery):
        await event.answer()
        msg = event.message
        if not msg:
            return
        await _render_feed(msg, session, db_user, offset=0)
        return
    await _render_feed(event, session, db_user, offset=0)


@router.callback_query(F.data.startswith("feed:next:"))
async def feed_next(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    offset = int(callback.data.split(":")[2])
    settings = get_settings()
    offset += settings.digest_default_limit
    await callback.answer()
    if not callback.message:
        return
    items = await FeedService(session).get_feed(db_user, limit=settings.digest_default_limit, offset=offset)
    if not items:
        await callback.message.edit_text("На данный момент это все новые новости 🎉")
        return
    await _render_feed(callback.message, session, db_user, offset=offset, edit=True)


@router.callback_query(F.data.startswith("feed:back:"))
async def feed_back(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    offset = int(callback.data.split(":")[2])
    await callback.answer()
    if callback.message:
        await _render_feed(callback.message, session, db_user, offset=offset, edit=True)


@router.callback_query(F.data.startswith("feed:open:"))
async def feed_open(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    # feed:open:{offset}:{index}:{ids}
    parts = callback.data.split(":")
    offset = int(parts[2])
    index = int(parts[3])
    ids_s = parts[4] if len(parts) > 4 else ""
    ids = [int(x) for x in ids_s.split(",") if x]
    await callback.answer()
    if not ids or not callback.message:
        return
    index = max(0, min(index, len(ids) - 1))
    news = await NewsService(session).get_news(ids[index])
    if not news:
        return
    await FeedService(session).mark_read(db_user, news)
    text = format_news_detail(news, index=index + 1, total=len(ids))
    await callback.message.edit_text(
        text,
        reply_markup=detail_keyboard(
            offset=offset,
            index=index,
            total=len(ids),
            news_id=news.id,
            ids_s=ids_s,
        ),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("feed:up:"))
async def feed_up(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    # feed:up:{news_id}:{offset}:{index}:{ids}
    parts = callback.data.split(":")
    news_id = int(parts[2])
    await ReactionService(session).mark_interesting(db_user.id, news_id)
    news = await NewsService(session).get_news(news_id)
    if news:
        await FeedService(session).mark_read(db_user, news)
    await callback.answer("Сохранено ❤️")


@router.callback_query(F.data.startswith("feed:down:"))
async def feed_down(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    parts = callback.data.split(":")
    news_id = int(parts[2])
    offset = int(parts[3])
    index = int(parts[4])
    ids_s = parts[5] if len(parts) > 5 else ""
    ids = [int(x) for x in ids_s.split(",") if x]
    await ReactionService(session).mark_not_interesting(db_user.id, news_id)
    news = await NewsService(session).get_news(news_id)
    if news:
        await FeedService(session).dislike(db_user, news)
    await callback.answer("Скрыто 👎")
    # jump to next or back to feed
    if not callback.message:
        return
    remaining = [i for i in ids if i != news_id]
    if not remaining:
        await _render_feed(callback.message, session, db_user, offset=offset, edit=True)
        return
    new_index = min(index, len(remaining) - 1)
    ids_s2 = ",".join(str(i) for i in remaining)
    n2 = await NewsService(session).get_news(remaining[new_index])
    if not n2:
        return
    await FeedService(session).mark_read(db_user, n2)
    await callback.message.edit_text(
        format_news_detail(n2, index=new_index + 1, total=len(remaining)),
        reply_markup=detail_keyboard(
            offset=offset,
            index=new_index,
            total=len(remaining),
            news_id=n2.id,
            ids_s=ids_s2,
        ),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("feed:src:"))
async def feed_sources(callback: CallbackQuery, session: AsyncSession) -> None:
    news_id = int(callback.data.split(":")[2])
    news = await NewsService(session).get_news(news_id)
    await callback.answer()
    if not news or not callback.message:
        return
    pairs = []
    for src in news.sources or []:
        label = src.channel_title or "Источник"
        pairs.append((label, src.source_url))
    await callback.message.answer(
        format_sources_screen(news),
        reply_markup=sources_keyboard(pairs),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "feed:srcback")
@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()
