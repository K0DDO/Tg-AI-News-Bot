"""Channels UX — list edits in place."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.i18n import t
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
        f"<b>📂 {t(lang, 'channels')}</b>\n\n"
        f"{t(lang, 'channels_hint')}\n\n"
        f"<code>@channel1\n@channel2\nhttps://t.me/channel3</code>",
        reply_markup=channels_menu_keyboard(lang),
    )


@router.message(Command("channels"))
async def cmd_channels(message: Message, session: AsyncSession, db_user: User) -> None:
    await channels_home(message, session, db_user)


@router.callback_query(F.data == "ch:bulk")
async def bulk_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await state.set_state(ChannelBulkStates.waiting_list)
    await callback.answer()
    if callback.message:
        text = (
            f"<b>➕ {t(lang, 'ch_add')}</b>\n\n"
            f"{t(lang, 'channels_hint')}\n\n"
            f"<code>@a\n@b\nhttps://t.me/c</code>"
        )
        try:
            await callback.message.edit_text(text)
        except TelegramBadRequest:
            await callback.message.answer(text)


@router.message(ChannelBulkStates.waiting_list)
async def bulk_import(message: Message, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    lang = await PreferencesService(session).lang(db_user)
    await state.clear()
    refs = parse_channel_refs(message.text or "")
    if not refs:
        await message.answer(t(lang, "ch_parse_fail"))
        return
    service = ChannelService(session)
    ok, fail = 0, []
    added_ids: list[int] = []
    for username in refs:
        try:
            chat = await message.bot.get_chat(f"@{username}")
            if chat.type not in {"channel", "supergroup"}:
                fail.append(username)
                continue
            channel = await service.add_channel_for_user(
                db_user,
                telegram_id=chat.id,
                title=chat.title or username,
                username=chat.username or username,
                backfill_days=2,
                create_job=False,
            )
            added_ids.append(channel.id)
            ok += 1
        except Exception:
            fail.append(username)
    job = None
    if added_ids:
        job = await service.create_backfill_job(db_user.id, days=2, channel_ids=added_ids)
        await session.commit()
        if job:
            await session.refresh(job)
    summary = f"✅ +{ok}" + (f"\n❌ {', '.join(fail[:10])}" if fail else "")
    if ok:
        summary += f"\n\n{t(lang, 'backfill_queued_add')}"
    if job:
        from app.bot.keyboards import backfill_progress_keyboard
        from app.bot.ui import format_backfill_progress

        await message.answer(
            format_backfill_progress(lang, job),
            reply_markup=backfill_progress_keyboard(lang, job.id),
        )
    else:
        await message.answer(summary)
    await _show_list(message, session, db_user, edit=False)


@router.callback_query(F.data == "ch:list")
async def ch_list(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    await callback.answer()
    if callback.message:
        await _show_list(callback.message, session, db_user, edit=True)


async def _show_list(
    message: Message,
    session: AsyncSession,
    user: User,
    *,
    edit: bool = False,
) -> None:
    lang = await PreferencesService(session).lang(user)
    pairs = await ChannelService(session).list_user_channels(user.id)
    items = [(ch.id, ch.title, link.is_active) for ch, link in pairs]
    text = f"<b>📋 {t(lang, 'ch_list')}</b>\n\n{t(lang, 'ch_list_hint')}: <b>{len(items)}</b>"
    kb = channel_list_keyboard(items, lang)
    if edit:
        try:
            await message.edit_text(text, reply_markup=kb)
            return
        except TelegramBadRequest:
            pass
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("ch:tog:"))
async def ch_toggle(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    channel_id = int(callback.data.split(":")[2])
    await ChannelService(session).toggle_user_channel(db_user.id, channel_id)
    await callback.answer("OK")
    if callback.message:
        await _show_list(callback.message, session, db_user, edit=True)


@router.callback_query(F.data.startswith("ch:del:"))
async def ch_del(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    channel_id = int(callback.data.split(":")[2])
    await ChannelService(session).remove_user_channel(db_user.id, channel_id)
    await callback.answer("OK")
    if callback.message:
        await _show_list(callback.message, session, db_user, edit=True)
