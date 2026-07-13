"""Settings for Briefly."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.i18n import t
from app.bot.keyboards import (
    backfill_period_keyboard,
    backfill_progress_keyboard,
    categories_keyboard,
    interval_keyboard,
    language_keyboard,
    min_importance_keyboard,
    page_size_keyboard,
    settings_keyboard,
)
from app.bot.states import IgnoreTopicsStates
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
            f"📂 {t(lang, 'set_cats')}",
            reply_markup=categories_keyboard(lang, settings.enabled_categories),
        )

@router.callback_query(F.data.startswith("set:cat:"))
async def toggle_cat(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    cat = callback.data.split(":")[2]
    settings = await PreferencesService(session).toggle_category(db_user, cat)
    lang = settings.language or "ru"
    await callback.answer()
    if callback.message:
        await callback.message.edit_reply_markup(
            reply_markup=categories_keyboard(lang, settings.enabled_categories)
        )


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
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"🗣 {t(lang, 'set_news_lang')}",
            reply_markup=language_keyboard(prefix="newslang"),
        )


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
    await PreferencesService(session).toggle_bool(db_user, field)
    await callback.answer("OK")
    if callback.message:
        await open_settings(callback.message, session, db_user, edit=True)


@router.callback_query(F.data.startswith("newslang:"))
async def set_news_lang(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    code = callback.data.split(":")[1]
    await PreferencesService(session).set_news_language(db_user, code)
    await callback.answer("OK")
    if callback.message:
        await open_settings(callback.message, session, db_user, edit=True)
