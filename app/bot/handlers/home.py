"""Home, branded onboarding, main menu routing."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.brand import send_banner
from app.bot.i18n import (
    LANG_LABELS,
    btn_feed,
    btn_search,
    btn_settings,
    btn_trends,
    t,
)
from app.bot.keyboards import (
    home_keyboard,
    how_to_keyboard,
    language_keyboard,
    main_menu,
    onboarding_channels_keyboard,
    onboarding_done_keyboard,
    onboarding_start_keyboard,
    onboarding_tour_keyboard,
    onboarding_while_keyboard,
    privacy_keyboard,
)
from app.bot.states import ChannelBulkStates
from app.bot.ui import format_home, format_how_to_use, format_privacy
from app.bot.ui.nav import replace_screen
from app.models import Event, User
from app.services.preferences import PreferencesService

router = Router(name="home")

_TOUR_KEYS = (
    ("ob_tour1_t", "ob_tour1_b"),
    ("ob_tour2_t", "ob_tour2_b"),
    ("ob_tour3_t", "ob_tour3_b"),
    ("ob_tour4_t", "ob_tour4_b"),
    ("ob_tour5_t", "ob_tour5_b"),
    ("ob_tour_done_t", "ob_tour_done_b"),
)


async def _lang(session: AsyncSession, user: User) -> str:
    return await PreferencesService(session).lang(user)


def _welcome_caption(lang: str) -> str:
    return (
        f"<b>🍓 {t(lang, 'ob_welcome_title')}</b>\n\n"
        f"{t(lang, 'ob_welcome_sub')}\n\n"
        f"<b>Briefly:</b>\n"
        f"📰 {t(lang, 'ob_feat_collect')}\n"
        f"🔥 {t(lang, 'ob_feat_merge')}\n"
        f"⭐ {t(lang, 'ob_feat_important')}\n"
        f"🔎 {t(lang, 'ob_feat_search')}\n\n"
        f"{t(lang, 'ob_welcome_cta')}"
    )


def _privacy_caption(lang: str) -> str:
    return (
        f"<b>🔒 {t(lang, 'ob_privacy_title')}</b>\n\n"
        f"{t(lang, 'ob_privacy_agree')}\n\n"
        f"• {t(lang, 'ob_privacy_policy')}\n"
        f"• {t(lang, 'ob_privacy_data')}\n\n"
        f"{t(lang, 'ob_privacy_store')}\n"
        f"👤 Telegram ID\n"
        f"⚙️ {t(lang, 'settings')}\n"
        f"📡 {t(lang, 'ob_privacy_sources')}\n"
        f"⭐ {t(lang, 'ob_privacy_reactions')}\n\n"
        f"{t(lang, 'ob_privacy_not')}\n"
        f"❌ {t(lang, 'ob_privacy_no_pass')}\n"
        f"❌ {t(lang, 'ob_privacy_no_dm')}"
    )


def _channels_caption(lang: str) -> str:
    return (
        f"<b>📡 {t(lang, 'ob_channels_title')}</b>\n\n"
        f"{t(lang, 'ob_channels_body')}\n\n"
        f"{t(lang, 'ob_channels_examples')}\n"
        f"<code>@appleinsider</code>\n"
        f"<code>@technology</code>\n"
        f"<code>@news</code>"
    )


def _while_caption(lang: str) -> str:
    return (
        f"<b>✨ {t(lang, 'ob_while_title')}</b>\n\n"
        f"{t(lang, 'ob_while_body')}\n\n"
        f"🔥 {t(lang, 'ob_while_themes')}\n"
        f"🌙 {t(lang, 'set_dnd')}\n"
        f"📰 {t(lang, 'ob_while_digest')}\n\n"
        f"{t(lang, 'ob_while_tour_hint')}"
    )


def _done_caption(lang: str) -> str:
    return (
        f"<b>🍓 {t(lang, 'ob_done_title')}</b>\n\n"
        f"{t(lang, 'ob_done_sub')}\n\n"
        f"{t(lang, 'ob_done_will')}\n"
        f"📰 {t(lang, 'ob_feat_collect')}\n"
        f"🔥 {t(lang, 'ob_feat_merge')}\n"
        f"⭐ {t(lang, 'ob_feat_important')}\n\n"
        f"{t(lang, 'ob_done_soon')}"
    )


def _lang_pick_text(lang: str) -> str:
    return f"<b>🌍 {t(lang, 'choose_language')}</b>"


async def send_welcome_onboarding(message: Message, lang: str = "ru") -> None:
    await send_banner(
        message,
        _welcome_caption(lang),
        reply_markup=onboarding_start_keyboard(lang),
        occasion="start",
    )


async def send_home(message: Message, session: AsyncSession, user: User) -> None:
    prefs = PreferencesService(session)
    settings = await prefs.get_or_create(user)
    lang = settings.language or "ru"

    # Incomplete onboarding → branded start
    if not settings.welcome_seen:
        await send_welcome_onboarding(message, lang if settings.language_chosen else "ru")
        return

    stats = await prefs.user_stats(user)
    from app.health import last_ingest_at
    from app.models import Message as TgMessage

    last = last_ingest_at()
    if last is None:
        # Fallback after restart: latest parsed Telegram post / event touch
        last = await session.scalar(select(func.max(TgMessage.created_at)))
        if last is None:
            last = await session.scalar(select(func.max(Event.updated_at)))
    text = format_home(
        lang,
        last_update=last,
        tz_name=settings.timezone or "Europe/Moscow",
        read=stats["read"],
        saved=stats["saved"],
        liked=stats["liked"],
    )
    await message.answer(t(lang, "menu_hint"), reply_markup=main_menu(lang))
    await message.answer(text, reply_markup=home_keyboard(lang))


async def show_while_preparing(message: Message, lang: str) -> None:
    await message.answer(
        _while_caption(lang),
        reply_markup=onboarding_while_keyboard(lang),
    )


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


@router.callback_query(F.data == "ob:begin")
async def ob_begin(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await _lang(session, db_user)
    await replace_screen(
        callback,
        _lang_pick_text(lang),
        reply_markup=language_keyboard(prefix="oblang"),
    )


@router.callback_query(F.data.startswith("oblang:"))
async def set_ob_lang(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    code = (callback.data or "").split(":", 1)[1]
    if code not in LANG_LABELS:
        await callback.answer("?", show_alert=True)
        return
    prefs = PreferencesService(session)
    await prefs.set_language(db_user, code)
    label = LANG_LABELS.get(code, code)
    text = (
        f"✅ {t(code, 'ob_lang_picked', name=label)}\n\n"
        f"{_privacy_caption(code)}"
    )
    await replace_screen(callback, text, reply_markup=privacy_keyboard(code))


@router.callback_query(F.data == "ob:privacy_full")
async def ob_privacy_full(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await _lang(session, db_user)
    await replace_screen(
        callback,
        format_privacy(lang),
        reply_markup=privacy_keyboard(lang),
    )


@router.callback_query(F.data == "ob:privacy_ok")
async def ob_privacy_ok(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await _lang(session, db_user)
    await replace_screen(
        callback,
        _channels_caption(lang),
        reply_markup=onboarding_channels_keyboard(lang),
    )


@router.callback_query(F.data == "ob:add_ch")
async def ob_add_channels(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    lang = await _lang(session, db_user)
    await state.set_state(ChannelBulkStates.waiting_list)
    await state.update_data(onboarding=True)
    await replace_screen(
        callback,
        f"<b>📡 {t(lang, 'ch_add')}</b>\n\n"
        f"{t(lang, 'channels_hint')}\n\n"
        f"<code>@appleinsider\n@technology\nhttps://t.me/news</code>",
    )


@router.callback_query(F.data == "ob:skip_ch")
async def ob_skip_channels(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await _lang(session, db_user)
    await replace_screen(
        callback,
        _while_caption(lang),
        reply_markup=onboarding_while_keyboard(lang),
    )


@router.callback_query(F.data == "ob:configure")
async def ob_configure(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    from app.bot.keyboards import settings_keyboard
    from app.bot.ui import format_settings

    prefs = PreferencesService(session)
    settings = await prefs.get_or_create(db_user)
    lang = settings.language or "ru"
    await replace_screen(
        callback,
        format_settings(lang, settings),
        reply_markup=settings_keyboard(lang),
    )


@router.callback_query(F.data.startswith("ob:tour:"))
async def ob_tour(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await _lang(session, db_user)
    step = int((callback.data or "").split(":")[2])
    if step < 0 or step >= len(_TOUR_KEYS):
        await callback.answer()
        return
    title_k, body_k = _TOUR_KEYS[step]
    await replace_screen(
        callback,
        f"<b>{t(lang, title_k)}</b>\n\n{t(lang, body_k)}",
        reply_markup=onboarding_tour_keyboard(lang, step, len(_TOUR_KEYS)),
    )


@router.callback_query(F.data == "ob:finish")
@router.callback_query(F.data == "ob:skip")
async def ob_finish(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    from aiogram.exceptions import TelegramBadRequest

    prefs = PreferencesService(session)
    await prefs.mark_welcome_seen(db_user)
    await prefs.mark_tutorial_seen(db_user)
    lang = await prefs.lang(db_user)
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass
    msg = callback.message
    if not msg:
        return
    try:
        await msg.delete()
    except TelegramBadRequest:
        try:
            await msg.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass
    await msg.answer(t(lang, "menu_hint"), reply_markup=main_menu(lang))
    await send_banner(
        msg,
        _done_caption(lang),
        reply_markup=onboarding_done_keyboard(lang),
        occasion="done",
    )


@router.callback_query(F.data == "nav:howto")
@router.callback_query(F.data.startswith("onb:"))
async def how_to_use(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    """How to use — with banner cover (replaces old auto-tour)."""
    from aiogram.exceptions import TelegramBadRequest

    lang = await _lang(session, db_user)
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass
    msg = callback.message
    if not msg:
        return
    try:
        await msg.delete()
    except TelegramBadRequest:
        pass
    await send_banner(
        msg,
        format_how_to_use(lang),
        reply_markup=how_to_keyboard(lang),
        occasion="howto",
    )


@router.callback_query(F.data == "nav:settings")
async def nav_settings(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    from app.bot.keyboards import settings_keyboard
    from app.bot.ui import format_settings

    prefs = PreferencesService(session)
    settings = await prefs.get_or_create(db_user)
    lang = settings.language or "ru"
    await replace_screen(
        callback,
        format_settings(lang, settings),
        reply_markup=settings_keyboard(lang),
    )


@router.callback_query(F.data == "nav:search")
async def nav_search(
    callback: CallbackQuery, session: AsyncSession, db_user: User, state: FSMContext
) -> None:
    from app.bot.handlers.search import ask_search
    from app.bot.states import SearchStates

    await state.set_state(SearchStates.waiting_query)
    await callback.answer()
    if callback.message:
        await ask_search(callback.message, session, db_user)


# Reply keyboard routing
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
