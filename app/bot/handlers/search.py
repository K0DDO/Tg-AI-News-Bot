"""Strict search UX for Briefly."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.i18n import t
from app.bot.states import SearchStates
from app.bot.ui import format_search_answer
from app.models import User
from app.services.preferences import PreferencesService
from app.services.search import SearchService
from app.services.translation import ensure_translation

router = Router(name="search")


async def ask_search(message: Message, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await message.answer(
        f"<b>🔍 {t(lang, 'search')}</b>\n\n"
        f"{t(lang, 'search_ask')}\n\n"
        f"<i>{t(lang, 'search_examples')}</i>"
    )


@router.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    await state.set_state(SearchStates.waiting_query)
    await ask_search(message, session, db_user)


@router.message(SearchStates.waiting_query)
async def run_search(message: Message, session: AsyncSession, state: FSMContext, db_user: User) -> None:
    query = (message.text or "").strip()
    await state.clear()
    lang = await PreferencesService(session).lang(db_user)
    if not query or query.startswith("/"):
        return

    wait = await message.answer(t(lang, "searching"))
    answer, _hits, used_news = await SearchService(session).search_with_answer(
        query,
        limit=8,
        empty_message=t(lang, "search_empty"),
        user=db_user,
    )
    await session.commit()
    for n in used_news:
        await ensure_translation(session, n, lang)

    text = format_search_answer(lang, answer, used_news)
    try:
        await wait.edit_text(text, disable_web_page_preview=True)
    except Exception:
        await message.answer(text, disable_web_page_preview=True)
