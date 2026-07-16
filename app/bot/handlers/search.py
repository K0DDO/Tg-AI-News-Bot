"""Knowledge Graph search UX for Briefly."""

from __future__ import annotations

import uuid

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.i18n import t
from app.bot.keyboards import search_result_keyboard
from app.bot.states import SearchStates
from app.bot.ui import format_search_answer, format_search_explain
from app.models import User
from app.services.preferences import PreferencesService
from app.services.search import SearchService
from app.services.translation import ensure_translation

router = Router(name="search")
_QUERY_CACHE: dict[str, dict] = {}


async def ask_search(
    message: Message,
    session: AsyncSession,
    db_user: User,
    *,
    replace_from: Message | None = None,
) -> None:
    from app.bot.ui.nav import show_screen

    lang = await PreferencesService(session).lang(db_user)
    text = (
        f"<b>🔍 {t(lang, 'search')}</b>\n\n"
        f"{t(lang, 'search_ask')}\n\n"
        f"<i>{t(lang, 'search_examples')}</i>"
    )
    target = replace_from or message
    await show_screen(target, session, db_user, text, edit=replace_from is not None)


@router.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    await state.set_state(SearchStates.waiting_query)
    await ask_search(message, session, db_user)


def _store_query(query: str, *, explanations: dict | None = None, events: list | None = None) -> str:
    token = uuid.uuid4().hex[:10]
    _QUERY_CACHE[token] = {
        "query": query,
        "explanations": explanations or {},
        "event_ids": [e.id for e in (events or [])],
    }
    if len(_QUERY_CACHE) > 200:
        for k in list(_QUERY_CACHE.keys())[:50]:
            _QUERY_CACHE.pop(k, None)
    return token


async def _run_search(
    message: Message,
    session: AsyncSession,
    db_user: User,
    query: str,
    *,
    include_external: bool = False,
    deep: bool = False,
    seed_event_ids: list[int] | None = None,
    edit_message: Message | None = None,
) -> None:
    lang = await PreferencesService(session).lang(db_user)
    us = await PreferencesService(session).get_or_create(db_user)
    news_lang = us.news_language or lang
    from app.bot.ui.nav import drop_ui_message, remember_ui_message

    if edit_message is None:
        await drop_ui_message(message.bot, session, db_user)
        wait = await message.answer(
            t(lang, "deep_searching") if deep else t(lang, "searching")
        )
        await remember_ui_message(session, db_user, wait)
    else:
        wait = edit_message
        if deep:
            try:
                await edit_message.edit_text(t(lang, "deep_searching"))
            except TelegramBadRequest:
                pass
    result = await SearchService(session).search_full(
        query,
        limit=10 if deep else 8,
        empty_message=t(lang, "search_empty"),
        user=db_user,
        include_external=include_external or us.include_external_news,
        deep=deep,
        lang=lang,
        seed_event_ids=seed_event_ids,
    )
    await session.commit()
    for n in result.events:
        await ensure_translation(session, n, news_lang)

    text = format_search_answer(
        lang,
        result.answer,
        result.events,
        external_count=0 if include_external else result.external_count,
        related_questions=result.related_questions,
        matched_nodes=result.matched_nodes,
    )
    if deep:
        text = f"🔬 <b>{t(lang, 'deep_search')}</b>\n\n" + text
    token = _store_query(query, explanations=result.explanations, events=result.events)
    kb = search_result_keyboard(
        lang,
        token=token,
        has_external=result.external_count > 0 and not include_external and not us.include_external_news,
        has_explain=bool(result.events and result.explanations),
    )
    try:
        await wait.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        from app.bot.ui.nav import remember_ui_message

        await remember_ui_message(session, db_user, wait)
    except TelegramBadRequest:
        from app.bot.ui.nav import show_screen

        await show_screen(message, session, db_user, text, reply_markup=kb)
    except Exception:
        from app.bot.ui.nav import show_screen

        await show_screen(message, session, db_user, text, reply_markup=kb)


@router.message(SearchStates.waiting_query)
async def run_search(message: Message, session: AsyncSession, state: FSMContext, db_user: User) -> None:
    query = (message.text or "").strip()
    await state.clear()
    if not query or query.startswith("/"):
        return
    await _run_search(message, session, db_user, query)


@router.callback_query(F.data.startswith("search:ext:"))
async def show_external(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    token = callback.data.split(":")[2]
    cached = _QUERY_CACHE.get(token) or {}
    query = cached.get("query") if isinstance(cached, dict) else cached
    await callback.answer()
    if not query or not callback.message:
        return
    await _run_search(
        callback.message,
        session,
        db_user,
        str(query),
        include_external=True,
        seed_event_ids=list(cached.get("event_ids") or []) if isinstance(cached, dict) else None,
        edit_message=callback.message,
    )


@router.callback_query(F.data.startswith("search:deep:"))
async def deep_search(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    token = callback.data.split(":")[2]
    cached = _QUERY_CACHE.get(token) or {}
    query = cached.get("query") if isinstance(cached, dict) else None
    seed_ids = list(cached.get("event_ids") or []) if isinstance(cached, dict) else []
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer()
    if not callback.message:
        return
    if not query:
        await callback.message.answer(t(lang, "search_empty"))
        return
    await _run_search(
        callback.message,
        session,
        db_user,
        str(query),
        deep=True,
        seed_event_ids=seed_ids or None,
        edit_message=callback.message,
    )


@router.callback_query(F.data.startswith("search:why:"))
async def why_found(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    from app.services.digest import NewsService

    token = callback.data.split(":")[2]
    cached = _QUERY_CACHE.get(token) or {}
    lang = await PreferencesService(session).lang(db_user)
    explanations = cached.get("explanations") or {}
    event_ids = cached.get("event_ids") or []
    events = []
    for eid in event_ids:
        ev = await NewsService(session).get_event(int(eid))
        if ev:
            events.append(ev)
    await callback.answer()
    if not callback.message:
        return
    text = format_search_explain(lang, {int(k): v for k, v in explanations.items()}, events)
    await callback.message.answer(text)
