"""Channels UX."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import channel_list_keyboard, channels_menu_keyboard
from app.bot.states import ChannelBulkStates
from app.models import User
from app.services.channels import ChannelService
from app.services.channels.import_parse import parse_channel_refs
from app.services.preferences import PreferencesService

router = Router(name="channels")


async def channels_home(message: Message, session: AsyncSession, user: User) -> None:
    lang = await PreferencesService(session).lang(user)
    await message.answer(
        "📂\n@channel1\n@channel2\nhttps://t.me/channel3",
        reply_markup=channels_menu_keyboard(lang),
    )


@router.message(Command("channels"))
async def cmd_channels(message: Message, session: AsyncSession, db_user: User) -> None:
    await channels_home(message, session, db_user)


@router.callback_query(F.data == "ch:bulk")
async def bulk_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ChannelBulkStates.waiting_list)
    await callback.answer()
    if callback.message:
        await callback.message.answer("<code>@a\n@b\nhttps://t.me/c</code>")


@router.message(ChannelBulkStates.waiting_list)
async def bulk_import(message: Message, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    await state.clear()
    refs = parse_channel_refs(message.text or "")
    if not refs:
        await message.answer("—")
        return
    service = ChannelService(session)
    ok, fail = 0, []
    for username in refs:
        try:
            chat = await message.bot.get_chat(f"@{username}")
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
    await message.answer(f"+{ok}" + (f" / fail: {', '.join(fail[:10])}" if fail else ""))
    await _show_list(message, session, db_user)


@router.callback_query(F.data == "ch:list")
async def ch_list(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    await callback.answer()
    if callback.message:
        await _show_list(callback.message, session, db_user)


async def _show_list(message: Message, session: AsyncSession, user: User) -> None:
    pairs = await ChannelService(session).list_user_channels(user.id)
    items = [(ch.id, ch.title, ch.enabled) for ch, _ in pairs]
    await message.answer(f"📋 {len(items)}", reply_markup=channel_list_keyboard(items))


@router.callback_query(F.data.startswith("ch:tog:"))
async def ch_toggle(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    channel_id = int(callback.data.split(":")[2])
    service = ChannelService(session)
    channel = await service.get_channel(channel_id)
    if channel:
        await service.set_channel_enabled(channel_id, not channel.enabled)
    await callback.answer("OK")
    if callback.message:
        await _show_list(callback.message, session, db_user)


@router.callback_query(F.data.startswith("ch:del:"))
async def ch_del(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    channel_id = int(callback.data.split(":")[2])
    await ChannelService(session).remove_user_channel(db_user.id, channel_id)
    await callback.answer("OK")
    if callback.message:
        await _show_list(callback.message, session, db_user)
