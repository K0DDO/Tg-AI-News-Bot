from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import news_keyboard
from app.config import get_settings
from app.models import User
from app.services.digest import NewsService, format_daily_header, format_news_card, format_sources_list
from app.services.reactions import ReactionService

router = Router(name="digest")


async def _send_news_list(
    target: Message,
    items: list,
    *,
    offset: int = 0,
    show_more: bool = True,
    numbered: bool = False,
) -> None:
    settings = get_settings()
    limit = settings.digest_default_limit
    for i, news in enumerate(items):
        is_last = i == len(items) - 1
        text = format_news_card(
            news,
            index=(i + 1) if numbered else None,
        )
        await target.answer(
            text,
            reply_markup=news_keyboard(
                news.id,
                show_more=show_more and is_last and not numbered,
                offset=offset + limit,
            ),
            disable_web_page_preview=True,
        )


@router.message(Command("digest"))
async def cmd_digest(message: Message, session: AsyncSession) -> None:
    settings = get_settings()
    items = await NewsService(session).get_top_news(limit=settings.digest_default_limit, offset=0)
    if not items:
        await message.answer("Пока нет новостей. Добавь каналы через /channels и дождись парсинга.")
        return
    await _send_news_list(message, items, offset=0)


@router.message(Command("daily"))
async def cmd_daily(message: Message, session: AsyncSession) -> None:
    settings = get_settings()
    items = await NewsService(session).get_daily_news(limit=settings.daily_digest_limit)
    if not items:
        await message.answer("За последние 24 часа важных новостей пока нет.")
        return
    await message.answer(format_daily_header(len(items)))
    await _send_news_list(message, items, show_more=False, numbered=True)


@router.callback_query(F.data.startswith("digest:more:"))
async def cb_digest_more(callback: CallbackQuery, session: AsyncSession) -> None:
    offset = int(callback.data.split(":")[-1])
    settings = get_settings()
    items = await NewsService(session).get_top_news(
        limit=settings.digest_default_limit,
        offset=offset,
    )
    await callback.answer()
    if not callback.message:
        return
    if not items:
        await callback.message.answer("Больше новостей нет.")
        return
    await _send_news_list(callback.message, items, offset=offset)


@router.callback_query(F.data.startswith("react:"))
async def cb_react(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    _, direction, news_id_s = callback.data.split(":")
    news_id = int(news_id_s)
    reactions = ReactionService(session)
    if direction == "up":
        await reactions.mark_interesting(db_user.id, news_id)
        await callback.answer("Сохранено: интересно")
    else:
        await reactions.mark_not_interesting(db_user.id, news_id)
        await callback.answer("Сохранено: не интересно")


@router.callback_query(F.data.startswith("news:more:"))
async def cb_news_more(callback: CallbackQuery, session: AsyncSession) -> None:
    news_id = int(callback.data.split(":")[-1])
    news = await NewsService(session).get_news(news_id)
    await callback.answer()
    if not news or not callback.message:
        return
    await callback.message.answer(
        format_news_card(news),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("news:src:"))
async def cb_news_sources(callback: CallbackQuery, session: AsyncSession) -> None:
    news_id = int(callback.data.split(":")[-1])
    news = await NewsService(session).get_news(news_id)
    await callback.answer()
    if not news or not callback.message:
        return
    await callback.message.answer(
        format_sources_list(news),
        disable_web_page_preview=True,
    )
