from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import news_keyboard
from app.bot.states import SearchStates
from app.services.digest import format_news_card
from app.services.digest.service import NewsService
from app.services.search import SemanticSearch

router = Router(name="search")


@router.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext) -> None:
    await state.set_state(SearchStates.waiting_query)
    await message.answer(
        "Задай вопрос по смыслу, например:\n"
        "• Что нового было про NVIDIA?\n"
        "• Какие нейросети появились для блогеров?"
    )


@router.message(SearchStates.waiting_query)
async def search_query(message: Message, session: AsyncSession, state: FSMContext) -> None:
    query = (message.text or "").strip()
    await state.clear()
    if not query:
        await message.answer("Пустой запрос.")
        return

    await message.answer("Ищу…")
    search = SemanticSearch(session)
    answer, hits = await search.search_with_answer(query, limit=6)
    await session.commit()

    await message.answer(answer)
    if not hits:
        return

    news_service = NewsService(session)
    for hit in hits[:5]:
        news = await news_service.get_news(hit.news_id)
        if not news:
            continue
        await message.answer(
            format_news_card(news),
            reply_markup=news_keyboard(news.id),
            disable_web_page_preview=True,
        )
