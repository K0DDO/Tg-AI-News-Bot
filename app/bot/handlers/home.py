"""Home, language picker, onboarding."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.i18n import btn_feed, btn_search, btn_settings, btn_trends, t
from app.bot.keyboards import home_keyboard, language_keyboard, main_menu, onboarding_keyboard
from app.bot.ui import format_home, onboarding_steps
from app.models import Event, User
from app.models import Message as DbMessage
from app.services.preferences import PreferencesService

router = Router(name="home")
BANNER_PATH = Path(__file__).resolve().parents[1] / "assets" / "welcome.png"


async def _lang(session: AsyncSession, user: User) -> str:
    return await PreferencesService(session).lang(user)


async def _today_stats(session: AsyncSession):
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    messages = await session.scalar(
        select(func.count()).select_from(DbMessage).where(DbMessage.created_at >= since)
    )
    news_count = await session.scalar(
        select(func.count()).select_from(Event).where(Event.created_at >= since)
    )
    avg = await session.scalar(
        select(func.avg(Event.importance_score)).where(Event.created_at >= since)
    )
    last = await session.scalar(select(func.max(Event.updated_at)))
    return int(messages or 0), int(news_count or 0), float(avg or 0), last


async def send_home(message: Message, session: AsyncSession, user: User) -> None:
    prefs = PreferencesService(session)
    settings = await prefs.get_or_create(user)
    lang = settings.language or "ru"
    if not settings.language_chosen:
        await message.answer(
            f"<b>{t('en', 'brand')}</b>\n\n{t('ru', 'choose_language')} / {t('en', 'choose_language')}",
            reply_markup=language_keyboard(),
        )
        return

    msgs, news_n, avg, last = await _today_stats(session)
    text = format_home(lang, messages=msgs, news=news_n, avg_importance=avg, last_update=last)
    await message.answer(t(lang, "menu_hint"), reply_markup=main_menu(lang))
    if not settings.welcome_seen and BANNER_PATH.exists():
        await message.answer_photo(
            FSInputFile(BANNER_PATH),
            caption=text,
            reply_markup=home_keyboard(lang),
        )
        await prefs.mark_welcome_seen(user)
    else:
        await message.answer(text, reply_markup=home_keyboard(lang))
        if not settings.welcome_seen:
            await prefs.mark_welcome_seen(user)


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, db_user: User) -> None:
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


@router.callback_query(F.data.startswith("lang:"))
async def set_lang(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    code = callback.data.split(":")[1]
    await PreferencesService(session).set_language(db_user, code)
    await callback.answer()
    if callback.message:
        await send_home(callback.message, session, db_user)


@router.callback_query(F.data.startswith("onb:"))
async def onboarding(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await _lang(session, db_user)
    step = int(callback.data.split(":")[1])
    steps = onboarding_steps(lang)
    await callback.answer()
    if step < 0 or step >= len(steps):
        return
    title, body = steps[step]
    if callback.message:
        await callback.message.answer(
            f"<b>{title}</b>\n\n{body}",
            reply_markup=onboarding_keyboard(lang, step, len(steps)),
        )


# Route reply keyboard by matching any language button labels
@router.message(F.text.func(lambda s: bool(s) and any(s == btn_feed(l) for l in ("ru", "en", "de", "es"))))
async def reply_feed(message: Message, session: AsyncSession, db_user: User) -> None:
    from app.bot.handlers.news import open_feed

    await open_feed(message, session, db_user)


@router.message(F.text.func(lambda s: bool(s) and any(s == btn_search(l) for l in ("ru", "en", "de", "es"))))
async def reply_search(message: Message, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    from app.bot.handlers.search import ask_search
    from app.bot.states import SearchStates

    await state.set_state(SearchStates.waiting_query)
    await ask_search(message, session, db_user)


@router.message(F.text.func(lambda s: bool(s) and any(s == btn_settings(l) for l in ("ru", "en", "de", "es"))))
async def reply_settings(message: Message, session: AsyncSession, db_user: User) -> None:
    from app.bot.handlers.settings import open_settings

    await open_settings(message, session, db_user)


@router.message(F.text.func(lambda s: bool(s) and any(s == btn_trends(l) for l in ("ru", "en", "de", "es"))))
async def reply_trends(message: Message, session: AsyncSession, db_user: User) -> None:
    from app.bot.handlers.trends import show_trends_msg

    await show_trends_msg(message, session, db_user)
