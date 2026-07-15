"""Settings for Briefly."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.i18n import t
from app.bot.keyboards import (
    backfill_period_keyboard,
    backfill_progress_keyboard,
    categories_keyboard,
    digest_time_keyboard,
    dnd_keyboard,
    interval_keyboard,
    language_keyboard,
    min_importance_keyboard,
    page_size_keyboard,
    settings_feed_keyboard,
    settings_info_keyboard,
    settings_keyboard,
    settings_lang_keyboard,
    settings_personal_keyboard,
    settings_sources_keyboard,
    theme_weight_pick_keyboard,
    theme_weights_keyboard,
    timezone_keyboard,
)
from app.bot.states import IgnoreTopicsStates, TimezoneStates
from app.bot.ui import format_backfill_progress, format_privacy, format_settings
from app.models import User
from app.services.preferences import PreferencesService

router = Router(name="settings")


async def open_settings(
    message: Message,
    session: AsyncSession,
    user: User,
    *,
    edit: bool = False,
) -> None:
    from aiogram.exceptions import TelegramBadRequest

    prefs = PreferencesService(session)
    settings = await prefs.get_or_create(user)
    lang = settings.language or "ru"
    text = format_settings(lang, settings)
    kb = settings_keyboard(lang)
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb)
            return
        except TelegramBadRequest:
            pass
    await message.answer(text, reply_markup=kb)


@router.message(Command("settings"))
async def cmd_settings(message: Message, session: AsyncSession, db_user: User) -> None:
    await open_settings(message, session, db_user)


@router.callback_query(F.data == "set:back")
async def set_back(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    await callback.answer()
    if callback.message:
        await open_settings(callback.message, session, db_user, edit=True)


@router.callback_query(F.data == "set:lang")
async def set_lang_menu(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(f"🌐 {t(lang, 'language')}", reply_markup=language_keyboard())


@router.callback_query(F.data == "set:interval")
async def set_interval_menu(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"🕒 {t(lang, 'set_interval')}",
            reply_markup=interval_keyboard(lang),
        )


@router.callback_query(F.data.startswith("set:iv:"))
async def set_interval(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    minutes = int(callback.data.split(":")[2])
    await PreferencesService(session).set_interval(db_user, minutes)
    await callback.answer("OK")
    if callback.message:
        await open_settings(callback.message, session, db_user, edit=True)


@router.callback_query(F.data == "set:min")
async def set_min_menu(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"⭐ {t(lang, 'set_min')}",
            reply_markup=min_importance_keyboard(lang),
        )


@router.callback_query(F.data.startswith("set:mi:"))
async def set_min(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    value = float(callback.data.split(":")[2])
    await PreferencesService(session).set_min_importance(db_user, value)
    await callback.answer("OK")
    if callback.message:
        await open_settings(callback.message, session, db_user, edit=True)


@router.callback_query(F.data == "set:cats")
async def set_cats(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    prefs = PreferencesService(session)
    settings = await prefs.get_or_create(db_user)
    lang = settings.language or "ru"
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"📂 {t(lang, 'set_themes')}",
            reply_markup=categories_keyboard(lang, settings.enabled_categories),
        )

@router.callback_query(F.data.startswith("set:cat:"))
async def toggle_cat(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    cat = callback.data.split(":")[2]
    settings = await PreferencesService(session).toggle_category(db_user, cat)
    lang = settings.language or "ru"
    await callback.answer()
    if callback.message:
        kb = categories_keyboard(lang, settings.enabled_categories)
        try:
            await callback.message.edit_reply_markup(reply_markup=kb)
        except TelegramBadRequest:
            try:
                await callback.message.edit_text(
                    f"📂 {t(lang, 'set_cats')}",
                    reply_markup=kb,
                )
            except TelegramBadRequest:
                pass


@router.callback_query(F.data == "set:ignore")
async def set_ignore(callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    await state.set_state(IgnoreTopicsStates.waiting_topics)
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer()
    if callback.message:
        await callback.message.answer("🔕\n<code>crypto, sports</code>" if lang != "ru" else "🔕\n<code>крипто, спорт</code>")


@router.message(IgnoreTopicsStates.waiting_topics)
async def save_ignore(message: Message, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await PreferencesService(session).set_ignored_topics(db_user, message.text or "")
    await open_settings(message, session, db_user)


@router.callback_query(F.data == "set:reset")
async def reset_reactions(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    await PreferencesService(session).reset_reactions(db_user)
    await callback.answer("OK", show_alert=True)


@router.callback_query(F.data == "set:privacy")
async def privacy(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer()
    if callback.message:
        await callback.message.answer(format_privacy(lang))


@router.callback_query(F.data == "set:channels")
async def set_channels(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    from app.bot.handlers.channels import channels_home

    await callback.answer()
    if callback.message:
        await channels_home(callback.message, session, db_user)


@router.callback_query(F.data == "set:backfill")
async def set_backfill_menu(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"📥 <b>{t(lang, 'load_news')}</b>\n\n{t(lang, 'load_news_hint')}",
            reply_markup=backfill_period_keyboard(lang),
        )


@router.callback_query(F.data.startswith("set:bf:"))
async def set_backfill_run(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    from app.services.channels import ChannelService

    days = int(callback.data.split(":")[2])
    days = max(1, min(days, 7))
    lang = await PreferencesService(session).lang(db_user)
    job = await ChannelService(session).request_backfill_for_user(db_user.id, days=days)
    if not job:
        await callback.answer(t(lang, "backfill_no_channels"), show_alert=True)
        return
    await callback.answer("OK")
    if callback.message:
        await callback.message.edit_text(
            format_backfill_progress(lang, job),
            reply_markup=backfill_progress_keyboard(lang, job.id),
        )


@router.callback_query(F.data.startswith("set:bfprog:"))
async def set_backfill_progress(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    from aiogram.exceptions import TelegramBadRequest

    from app.services.channels import ChannelService

    job_id = int(callback.data.split(":")[2])
    lang = await PreferencesService(session).lang(db_user)
    job = await ChannelService(session).get_backfill_job(job_id)
    if not job or job.user_id != db_user.id:
        await callback.answer(t(lang, "bf_not_found"), show_alert=True)
        return
    await callback.answer(f"{job.percent}%")
    if callback.message:
        try:
            await callback.message.edit_text(
                format_backfill_progress(lang, job),
                reply_markup=backfill_progress_keyboard(lang, job.id),
            )
        except TelegramBadRequest:
            pass


@router.callback_query(F.data == "set:favorites")
async def set_favorites(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    from app.bot.handlers.library import show_favorites

    await callback.answer()
    if callback.message:
        await show_favorites(callback.message, session, db_user)


@router.callback_query(F.data == "set:history")
async def set_history(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    from app.bot.handlers.library import show_history

    await callback.answer()
    if callback.message:
        await show_history(callback.message, session, db_user)


@router.callback_query(F.data == "set:newslang")
async def set_news_lang_menu(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer(t(lang, "news_lang_wip"), show_alert=True)


@router.callback_query(F.data == "set:pagesize")
async def set_page_size_menu(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"📄 {t(lang, 'set_page_size')}",
            reply_markup=page_size_keyboard(lang),
        )


@router.callback_query(F.data.startswith("set:ps:"))
async def set_page_size(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    size = int(callback.data.split(":")[2])
    await PreferencesService(session).set_feed_page_size(db_user, size)
    await callback.answer("OK")
    if callback.message:
        await open_settings(callback.message, session, db_user, edit=True)


@router.callback_query(F.data.startswith("set:tog:"))
async def set_toggle(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    field = callback.data.split(":")[2]
    prefs = PreferencesService(session)
    settings = await prefs.toggle_bool(db_user, field)
    await callback.answer("OK")
    if not callback.message:
        return
    if field == "dnd_enabled":
        lang = settings.language or "ru"
        try:
            await callback.message.edit_reply_markup(reply_markup=dnd_keyboard(lang, settings))
        except TelegramBadRequest:
            await callback.message.edit_text(
                f"🌙 {t(lang, 'set_dnd')}",
                reply_markup=dnd_keyboard(lang, settings),
            )
        return
    await open_settings(callback.message, session, db_user, edit=True)


@router.callback_query(F.data.startswith("newslang:"))
async def set_news_lang(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    code = callback.data.split(":")[1]
    await PreferencesService(session).set_news_language(db_user, code)
    await callback.answer("OK")
    if callback.message:
        await open_settings(callback.message, session, db_user, edit=True)


@router.callback_query(F.data == "set:feed")
async def set_feed_sec(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"📰 {t(lang, 'set_sec_feed')}",
            reply_markup=settings_feed_keyboard(lang),
        )


@router.callback_query(F.data == "set:sources")
async def set_sources_sec(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"📡 {t(lang, 'set_sec_sources')}",
            reply_markup=settings_sources_keyboard(lang),
        )


@router.callback_query(F.data == "set:langmenu")
async def set_lang_sec(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"🌎 {t(lang, 'set_sec_lang')}",
            reply_markup=settings_lang_keyboard(lang),
        )


@router.callback_query(F.data == "set:personal")
async def set_personal_sec(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"🎯 {t(lang, 'set_sec_personal')}",
            reply_markup=settings_personal_keyboard(lang),
        )


@router.callback_query(F.data == "set:info")
async def set_info_sec(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"ℹ️ {t(lang, 'set_sec_info')}",
            reply_markup=settings_info_keyboard(lang),
        )


@router.callback_query(F.data == "set:digests")
async def set_digests_menu(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"🔔 {t(lang, 'set_digests')}",
            reply_markup=interval_keyboard(lang),
        )


@router.callback_query(F.data.startswith("set:dm:"))
async def set_digest_mode_cb(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    mode = callback.data.split(":")[2]
    prefs = PreferencesService(session)
    await prefs.set_digest_mode(db_user, mode)
    lang = await prefs.lang(db_user)
    await callback.answer("OK")
    if mode == "daily" and callback.message:
        await callback.message.edit_text(
            f"🔔 {t(lang, 'digest_pick_time')}",
            reply_markup=digest_time_keyboard(lang),
        )
        return
    if callback.message:
        await open_settings(callback.message, session, db_user, edit=True)


@router.callback_query(F.data.startswith("set:dtime:"))
async def set_digest_time_cb(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    parts = callback.data.split(":")
    hhmm = f"{parts[2]}:{parts[3]}" if len(parts) >= 4 else parts[2]
    await PreferencesService(session).set_digest_time(db_user, hhmm)
    await callback.answer("OK")
    if callback.message:
        await open_settings(callback.message, session, db_user, edit=True)


@router.callback_query(F.data == "set:dnd")
async def set_dnd_menu(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    prefs = PreferencesService(session)
    settings = await prefs.get_or_create(db_user)
    lang = settings.language or "ru"
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"🌙 {t(lang, 'set_dnd')}",
            reply_markup=dnd_keyboard(lang, settings),
        )


@router.callback_query(F.data.in_({"set:dnd:weekday", "set:dnd:weekend"}))
async def set_dnd_presets(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    prefs = PreferencesService(session)
    kind = callback.data.split(":")[2]
    settings = await prefs.get_or_create(db_user)
    if kind == "weekday":
        presets = [("23:00", "08:00"), ("22:00", "07:00"), ("00:00", "08:00")]
        cur = (settings.dnd_weekday_start, settings.dnd_weekday_end)
        nxt = presets[(presets.index(cur) + 1) % len(presets)] if cur in presets else presets[0]
        await prefs.set_dnd(db_user, weekday_start=nxt[0], weekday_end=nxt[1])
    else:
        presets = [("00:00", "10:00"), ("00:00", "11:00"), ("01:00", "10:00")]
        cur = (settings.dnd_weekend_start, settings.dnd_weekend_end)
        nxt = presets[(presets.index(cur) + 1) % len(presets)] if cur in presets else presets[0]
        await prefs.set_dnd(db_user, weekend_start=nxt[0], weekend_end=nxt[1])
    settings = await prefs.get_or_create(db_user)
    lang = settings.language or "ru"
    await callback.answer("OK")
    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=dnd_keyboard(lang, settings))
        except TelegramBadRequest:
            await callback.message.edit_text(
                f"🌙 {t(lang, 'set_dnd')}",
                reply_markup=dnd_keyboard(lang, settings),
            )


@router.callback_query(F.data == "set:tz")
async def set_tz_menu(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"🌍 {t(lang, 'set_tz')}",
            reply_markup=timezone_keyboard(lang),
        )


@router.callback_query(F.data.startswith("set:tzset:"))
async def set_tz_value(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    tz = callback.data.split(":", 2)[2]
    await PreferencesService(session).set_timezone(db_user, tz)
    await callback.answer("OK")
    if callback.message:
        await open_settings(callback.message, session, db_user, edit=True)


@router.callback_query(F.data == "set:tzcustom")
async def set_tz_custom(callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    await state.set_state(TimezoneStates.waiting_tz)
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer()
    if callback.message:
        await callback.message.answer(t(lang, "tz_custom_hint"))


@router.message(TimezoneStates.waiting_tz)
async def save_tz_custom(message: Message, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    await state.clear()
    raw = (message.text or "").strip()
    await PreferencesService(session).set_timezone(db_user, raw or "Europe/Moscow")
    await open_settings(message, session, db_user)


@router.callback_query(F.data == "set:theme_weights")
async def set_theme_weights_menu(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    prefs = PreferencesService(session)
    settings = await prefs.get_or_create(db_user)
    lang = settings.language or "ru"
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"⭐ {t(lang, 'set_theme_weights')}",
            reply_markup=theme_weights_keyboard(lang, settings.theme_weights),
        )


@router.callback_query(F.data.startswith("set:twset:"))
async def set_theme_weight_save(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    parts = callback.data.split(":")
    theme, stars = parts[2], int(parts[3])
    prefs = PreferencesService(session)
    settings = await prefs.set_theme_weight(db_user, theme, stars)
    lang = settings.language or "ru"
    await callback.answer("OK")
    if callback.message:
        await callback.message.edit_text(
            f"⭐ {t(lang, 'set_theme_weights')}",
            reply_markup=theme_weights_keyboard(lang, settings.theme_weights),
        )


@router.callback_query(F.data.startswith("set:tw:"))
async def set_theme_weight_pick(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    theme = callback.data.split(":")[2]
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"⭐ {theme}",
            reply_markup=theme_weight_pick_keyboard(lang, theme),
        )


@router.callback_query(F.data == "set:about")
async def set_about(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer()
    if callback.message:
        await callback.message.answer(t(lang, "about_text"))
