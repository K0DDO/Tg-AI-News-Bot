"""Channels UX with bulk import."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import (
    BTN_CHANNELS,
    channel_list_keyboard,
    channels_menu_keyboard,
)
from app.bot.states import ChannelBulkStates
from app.models import User
from app.services.channels import ChannelService
from app.services.channels.import_parse import parse_channel_refs

router = Router(name="channels")


async def _show_menu(message: Message) -> None:
    await message.answer(
        "<b>📂 Каналы</b>\n\n"
        "Добавляй пачкой: @username или ссылки t.me\n"
        "Импорт папки Telegram — через список (Bot API не даёт читать чужие папки).",
        reply_markup=channels_menu_keyboard(),
    )


@router.message(F.text == BTN_CHANNELS)
@router.message(Command("channels"))
async def channels_home(message: Message) -> None:
    await _show_menu(message)


@router.callback_query(F.data == "ch:bulk")
async def bulk_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ChannelBulkStates.waiting_list)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "<b>➕ Массовое добавление</b>\n\n"
            "Пришли список в любом виде:\n\n"
            "<code>@channel1\n@channel2\nhttps://t.me/channel3</code>"
        )


@router.message(ChannelBulkStates.waiting_list)
async def bulk_import(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    await state.clear()
    refs = parse_channel_refs(message.text or "")
    if not refs:
        await message.answer("Не нашёл username/ссылок. Попробуй ещё раз.")
        return

    service = ChannelService(session)
    ok, fail = 0, []
    bot = message.bot
    for username in refs:
        try:
            chat = await bot.get_chat(f"@{username}")
            if chat.type not in {"channel", "supergroup"}:
                fail.append(username)
                continue
            await service.add_channel_for_user(
                db_user,
                telegram_id=chat.id,
                title=chat.title or username,
                username=chat.username or username,
            )
            ok += 1
        except Exception:
            fail.append(username)

    text = f"Готово: <b>+{ok}</b> каналов."
    if fail:
        text += "\nНе удалось: " + ", ".join(f"@{u}" for u in fail[:15])
    await message.answer(text)
    await _show_list(message, session, db_user)


@router.callback_query(F.data == "ch:list")
async def ch_list(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    await callback.answer()
    if callback.message:
        await _show_list(callback.message, session, db_user)


async def _show_list(message: Message, session: AsyncSession, user: User) -> None:
    pairs = await ChannelService(session).list_user_channels(user.id)
    if not pairs:
        await message.answer("Каналов пока нет.", reply_markup=channels_menu_keyboard())
        return
    items = [(ch.id, ch.title, ch.enabled) for ch, _link in pairs]
    await message.answer(
        f"<b>📋 Мои каналы</b> · {len(items)}",
        reply_markup=channel_list_keyboard(items),
    )


@router.callback_query(F.data.startswith("ch:tog:"))
async def ch_toggle(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    channel_id = int(callback.data.split(":")[2])
    service = ChannelService(session)
    channel = await service.get_channel(channel_id)
    if channel:
        await service.set_channel_enabled(channel_id, not channel.enabled)
    await callback.answer("Обновлено")
    if callback.message:
        await _show_list(callback.message, session, db_user)


@router.callback_query(F.data.startswith("ch:del:"))
async def ch_del(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    channel_id = int(callback.data.split(":")[2])
    await ChannelService(session).remove_user_channel(db_user.id, channel_id)
    await callback.answer("Удалено")
    if callback.message:
        await _show_list(callback.message, session, db_user)
