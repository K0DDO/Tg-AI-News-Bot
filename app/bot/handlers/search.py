"""Perplexity-style semantic search UX."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import BTN_SEARCH, detail_keyboard
from app.bot.states import SearchStates
from app.bot.ui import format_news_detail, format_search_answer
from app.models import User
from app.services.digest import NewsService
from app.services.search import SemanticSearch

router = Router(name="search")


@router.message(F.text == BTN_SEARCH)
@router.message(Command("search"))
async def ask_search(message: Message, state: FSMContext) -> None:
    await state.set_state(SearchStates.waiting_query)
    await message.answer(
        "<b>🔍 Поиск</b>\n\n"
        "Что хотите найти?\n\n"
        "<i>Например:</i>\n"
        "• новости про iPhone 17 Pro\n"
        "• что нового по NVIDIA\n"
        "• лучшие нейросети для блогеров"
    )


@router.message(SearchStates.waiting_query)
async def run_search(message: Message, session: AsyncSession, state: FSMContext) -> None:
    query = (message.text or "").strip()
    await state.clear()
    if not query or query.startswith("/"):
        await message.answer("Введите текстовый запрос.")
        return

    wait = await message.answer("Ищу…")
    answer, hits = await SemanticSearch(session).search_with_answer(query, limit=6)
    await session.commit()

    try:
        await wait.edit_text(format_search_answer(answer, hits), disable_web_page_preview=True)
    except Exception:
        await message.answer(format_search_answer(answer, hits), disable_web_page_preview=True)

    if not hits:
        return

    # compact open first source as optional detail buttons via separate short list
    news_service = NewsService(session)
    ids = [h.news_id for h in hits[:5]]
    ids_s = ",".join(str(i) for i in ids)
    first = await news_service.get_news(ids[0])
    if first:
        await message.answer(
            format_news_detail(first, index=1, total=len(ids)),
            reply_markup=detail_keyboard(
                offset=0,
                index=0,
                total=len(ids),
                news_id=first.id,
                ids_s=ids_s,
            ),
            disable_web_page_preview=True,
        )
