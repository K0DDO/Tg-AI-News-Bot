"""Feed + detail carousel for Briefly."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.i18n import t
from app.bot.keyboards import add_channels_keyboard, detail_keyboard, feed_keyboard, sources_keyboard
from app.bot.ui import format_feed, format_news_detail, format_sources_screen
from app.models import User
from app.services.digest import NewsService
from app.services.events import BriefBuilderService
from app.services.preferences import FeedService, PreferencesService
from app.services.reactions import ReactionService
from app.services.translation import ensure_translation

router = Router(name="news")
_briefs = BriefBuilderService()


async def _lang(session: AsyncSession, user: User) -> str:
    return await PreferencesService(session).lang(user)


async def _event(session: AsyncSession, event_id: int):
    return await NewsService(session).get_event(event_id)


async def _related_events(session: AsyncSession, news, *, limit: int = 4):
    """Prefer cached related_event_ids; fall back to KG only if empty."""
    cached = list(getattr(news, "related_event_ids", None) or [])[:limit]
    if cached:
        from sqlalchemy import select

        from app.models import Event

        result = await session.execute(
            select(Event)
            .where(Event.id.in_(cached), Event.status == "active")
            .order_by(Event.importance_score.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    try:
        from app.services.knowledge import KnowledgeGraphService

        return await KnowledgeGraphService(session).related_events(news, limit=limit)
    except Exception:
        return []


async def open_feed(
    target: Message,
    session: AsyncSession,
    user: User,
    *,
    offset: int = 0,
    edit: bool = False,
) -> None:
    lang = await _lang(session, user)
    prefs = PreferencesService(session)
    us = await prefs.get_or_create(user)
    news_lang = us.news_language or lang
    items, total = await FeedService(session).get_feed(user, offset=offset)
    for n in items:
        await ensure_translation(session, n, news_lang)
    if not items and offset == 0:
        from sqlalchemy import func, select

        from app.models import UserChannel

        n_ch = await session.scalar(
            select(func.count()).select_from(UserChannel).where(
                UserChannel.user_id == user.id,
                UserChannel.is_active.is_(True),
            )
        )
        if not n_ch:
            text = f"📂 {t(lang, 'no_channels_feed')}"
            kb = add_channels_keyboard(lang)
            if edit and getattr(target, "message_id", None):
                try:
                    await target.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
                    return
                except TelegramBadRequest:
                    pass
            await target.answer(text, reply_markup=kb, disable_web_page_preview=True)
            return
        text = t(lang, "no_more_news")
    elif not items:
        text = t(lang, "no_more_news")
    else:
        text = format_feed(lang, items)
    ids = [n.id for n in items]
    has_more = offset + len(items) < total and bool(items)
    kb = feed_keyboard(lang, offset=offset, page_ids=ids, has_more=has_more)

    # Inline navigation (next/back/refresh): edit in place
    if edit and getattr(target, "message_id", None):
        try:
            await target.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
            await prefs.save_digest_message(user, target.chat.id, target.message_id)
            return
        except TelegramBadRequest:
            pass

    # Always send a NEW message when opening feed from menu/command.
    # Editing an old digest far up the chat looks like "nothing happened".
    sent = await target.answer(text, reply_markup=kb, disable_web_page_preview=True)
    await prefs.save_digest_message(user, sent.chat.id, sent.message_id)


@router.message(Command("digest", "daily", "news", "feed"))
@router.callback_query(F.data == "nav:news")
async def cmd_feed(event: Message | CallbackQuery, session: AsyncSession, db_user: User) -> None:
    if isinstance(event, CallbackQuery):
        await event.answer()
        if event.message:
            await open_feed(event.message, session, db_user, offset=0)
        return
    await open_feed(event, session, db_user, offset=0)


@router.callback_query(F.data == "feed:refresh")
async def feed_refresh(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    await callback.answer()
    if callback.message:
        await open_feed(callback.message, session, db_user, offset=0, edit=True)


@router.callback_query(F.data.startswith("feed:next:"))
async def feed_next(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    offset = int(callback.data.split(":")[2])
    prefs = PreferencesService(session)
    us = await prefs.get_or_create(db_user)
    limit = int(us.feed_page_size or 5)
    offset += limit
    await callback.answer()
    if callback.message:
        await open_feed(callback.message, session, db_user, offset=offset, edit=True)


@router.callback_query(F.data.startswith("feed:back:"))
async def feed_back(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    await callback.answer()
    if callback.message:
        await open_feed(callback.message, session, db_user, offset=0, edit=True)


@router.callback_query(F.data.startswith("feed:open:"))
async def feed_open(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    """Подробнее: open event and mark it read immediately."""
    parts = callback.data.split(":")
    offset, index, ids_s = int(parts[2]), int(parts[3]), parts[4] if len(parts) > 4 else ""
    ids = [int(x) for x in ids_s.split(",") if x]
    await callback.answer()
    if not ids or not callback.message:
        return
    index = max(0, min(index, len(ids) - 1))
    await _show_detail(
        callback.message,
        session,
        db_user,
        offset=offset,
        index=index,
        ids=ids,
        mark_current_read=True,
        mark_prev_id=None,
    )


@router.callback_query(F.data.startswith("feed:nav:"))
async def feed_nav(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    """Carousel next/prev: mark leaving event read; show current without marking."""
    parts = callback.data.split(":")
    # feed:nav:offset:new_index:from_index:ids
    offset, index, from_i = int(parts[2]), int(parts[3]), int(parts[4])
    ids_s = parts[5] if len(parts) > 5 else ""
    ids = [int(x) for x in ids_s.split(",") if x]
    await callback.answer()
    if not ids or not callback.message:
        return
    index = max(0, min(index, len(ids) - 1))
    from_i = max(0, min(from_i, len(ids) - 1))
    prev_id = ids[from_i] if from_i != index else None
    await _show_detail(
        callback.message,
        session,
        db_user,
        offset=offset,
        index=index,
        ids=ids,
        mark_current_read=False,
        mark_prev_id=prev_id,
    )


async def _show_detail(
    message: Message,
    session: AsyncSession,
    user: User,
    *,
    offset: int,
    index: int,
    ids: list[int],
    mark_current_read: bool,
    mark_prev_id: int | None,
) -> None:
    prefs = PreferencesService(session)
    lang = await prefs.lang(user)
    us = await prefs.get_or_create(user)
    news_lang = us.news_language or lang
    feed = FeedService(session)
    if mark_prev_id is not None:
        prev = await _event(session, mark_prev_id)
        if prev:
            await feed.mark_read(user, prev)
    news = await _event(session, ids[index])
    if not news:
        return
    await ensure_translation(session, news, news_lang)
    if mark_current_read:
        await feed.mark_read(user, news)
    brief = _briefs.build(news, lang=news_lang, show_summary=us.show_summary)
    related = await _related_events(session, news, limit=4)
    ids_s = ",".join(str(i) for i in ids)
    await message.edit_text(
        format_news_detail(
            lang,
            brief,
            index=index + 1,
            total=len(ids),
            show_summary=us.show_summary,
            related=related,
        ),
        reply_markup=detail_keyboard(
            lang, offset=offset, index=index, total=len(ids), news_id=news.id, ids_s=ids_s
        ),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("feed:up:"))
async def feed_up(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    news_id = int(callback.data.split(":")[2])
    await ReactionService(session).mark_interesting(db_user.id, news_id)
    news = await _event(session, news_id)
    if news:
        await FeedService(session).mark_liked(db_user, news)
    lang = await _lang(session, db_user)
    await callback.answer(t(lang, "interesting"))


@router.callback_query(F.data.startswith("feed:down:"))
async def feed_down(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    parts = callback.data.split(":")
    news_id, offset, index = int(parts[2]), int(parts[3]), int(parts[4])
    ids_s = parts[5] if len(parts) > 5 else ""
    ids = [int(x) for x in ids_s.split(",") if x]
    await ReactionService(session).mark_not_interesting(db_user.id, news_id)
    news = await _event(session, news_id)
    if news:
        await FeedService(session).dislike(db_user, news)
    lang = await _lang(session, db_user)
    await callback.answer(t(lang, "not_interesting"))
    if not callback.message:
        return
    remaining = [i for i in ids if i != news_id]
    if not remaining:
        await open_feed(callback.message, session, db_user, offset=0, edit=True)
        return
    new_index = min(index, len(remaining) - 1)
    ids_s2 = ",".join(str(i) for i in remaining)
    prefs = PreferencesService(session)
    us = await prefs.get_or_create(db_user)
    news_lang = us.news_language or lang
    n2 = await _event(session, remaining[new_index])
    if not n2:
        return
    await ensure_translation(session, n2, news_lang)
    # Do not mark the next card as read — user only disliked the previous one.
    brief = _briefs.build(n2, lang=news_lang, show_summary=us.show_summary)
    await callback.message.edit_text(
        format_news_detail(
            lang, brief, index=new_index + 1, total=len(remaining), show_summary=us.show_summary
        ),
        reply_markup=detail_keyboard(
            lang, offset=offset, index=new_index, total=len(remaining), news_id=n2.id, ids_s=ids_s2
        ),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("feed:fav:"))
async def feed_fav(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    news_id = int(callback.data.split(":")[2])
    news = await _event(session, news_id)
    lang = await _lang(session, db_user)
    if not news:
        await callback.answer()
        return
    saved = await FeedService(session).toggle_favorite(db_user, news)
    await callback.answer(t(lang, "saved") if saved else t(lang, "save"))


@router.callback_query(F.data.startswith("feed:src:"))
async def feed_sources(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    news_id = int(callback.data.split(":")[2])
    news = await _event(session, news_id)
    lang = await _lang(session, db_user)
    await callback.answer()
    if not news or not callback.message:
        return
    brief = _briefs.build(news, lang=lang)
    pairs = [(s.channel_title or "Source", s.url) for s in brief.sources if s.url]
    await callback.message.answer(
        format_sources_screen(lang, brief),
        reply_markup=sources_keyboard(pairs, lang),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "feed:srcback")
async def feed_src_back(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.message:
        return
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()
