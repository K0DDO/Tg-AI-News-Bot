"""Settings for Briefly."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.i18n import t
from app.bot.keyboards import (
    categories_keyboard,
    interval_keyboard,
    language_keyboard,
    min_importance_keyboard,
    settings_keyboard,
)
from app.bot.states import IgnoreTopicsStates
from app.bot.ui import format_privacy, format_settings
from app.models import User
from app.services.preferences import PreferencesService

router = Router(name="settings")


async def open_settings(message: Message, session: AsyncSession, user: User) -> None:
    prefs = PreferencesService(session)
    settings = await prefs.get_or_create(user)
    lang = settings.language or "ru"
    await message.answer(format_settings(lang, settings), reply_markup=settings_keyboard(lang))


@router.message(Command("settings"))
async def cmd_settings(message: Message, session: AsyncSession, db_user: User) -> None:
    await open_settings(message, session, db_user)


@router.callback_query(F.data == "set:back")
async def set_back(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    await callback.answer()
    if callback.message:
        await open_settings(callback.message, session, db_user)


@router.callback_query(F.data == "set:lang")
async def set_lang_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("🌐", reply_markup=language_keyboard())


@router.callback_query(F.data == "set:interval")
async def set_interval_menu(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("🕒", reply_markup=interval_keyboard(lang))


@router.callback_query(F.data.startswith("set:iv:"))
async def set_interval(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    minutes = int(callback.data.split(":")[2])
    await PreferencesService(session).set_interval(db_user, minutes)
    await callback.answer("OK")
    if callback.message:
        await open_settings(callback.message, session, db_user)


@router.callback_query(F.data == "set:min")
async def set_min_menu(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("⭐", reply_markup=min_importance_keyboard(lang))


@router.callback_query(F.data.startswith("set:mi:"))
async def set_min(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    value = float(callback.data.split(":")[2])
    await PreferencesService(session).set_min_importance(db_user, value)
    await callback.answer("OK")
    if callback.message:
        await open_settings(callback.message, session, db_user)


@router.callback_query(F.data == "set:cats")
async def set_cats(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    prefs = PreferencesService(session)
    settings = await prefs.get_or_create(db_user)
    lang = settings.language or "ru"
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "📂",
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
