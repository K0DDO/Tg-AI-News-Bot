"""Replace Telegram screens in place (edit / delete+send). One active UI message."""

from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services.preferences import PreferencesService


async def drop_ui_message(
    bot: Bot,
    session: AsyncSession,
    user: User,
    *,
    also_message_id: int | None = None,
    chat_id: int | None = None,
) -> None:
    """Delete the previous interactive screen (and optional extra message id)."""
    prefs = PreferencesService(session)
    stored_chat, msg_id = await prefs.get_ui_message(user)
    target_chat = chat_id or stored_chat
    ids: list[int] = []
    if msg_id:
        ids.append(int(msg_id))
    if also_message_id and also_message_id not in ids:
        ids.append(int(also_message_id))
    if target_chat is not None:
        for mid in ids:
            try:
                await bot.delete_message(chat_id=int(target_chat), message_id=int(mid))
            except TelegramBadRequest:
                pass
            except Exception:
                pass
    if ids or stored_chat or msg_id:
        await prefs.clear_ui_message(user)


async def remember_ui_message(
    session: AsyncSession,
    user: User,
    message: Message,
) -> None:
    await PreferencesService(session).save_ui_message(
        user, message.chat.id, message.message_id
    )


async def push_reply_keyboard(message: Message, reply_markup: ReplyKeyboardMarkup) -> None:
    """
    Apply a reply keyboard without leaving a permanent message in the chat.
    Telegram keeps the keyboard after the carrier message is deleted.
    """
    carrier = await message.answer("\u200b", reply_markup=reply_markup)
    try:
        await carrier.delete()
    except TelegramBadRequest:
        pass


async def show_screen(
    target: Message,
    session: AsyncSession,
    user: User,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    edit: bool = False,
) -> Message:
    """
    Show one interactive screen.
    - edit=True: update this message in place when possible
    - otherwise: delete the previous UI message, then send a new one
    """
    if edit and getattr(target, "message_id", None):
        try:
            await target.edit_text(
                text, reply_markup=reply_markup, disable_web_page_preview=True
            )
            await remember_ui_message(session, user, target)
            return target
        except TelegramBadRequest:
            pass

    bot = target.bot
    # If we're replacing the same message that is already the UI pointer, skip double-delete
    await drop_ui_message(bot, session, user)

    # Callback source message may still be on screen (not yet tracked / different id)
    if getattr(target, "from_user", None) and getattr(target.from_user, "is_bot", False):
        try:
            await target.delete()
        except TelegramBadRequest:
            try:
                await target.edit_reply_markup(reply_markup=None)
            except TelegramBadRequest:
                pass

    sent = await target.answer(
        text, reply_markup=reply_markup, disable_web_page_preview=True
    )
    await remember_ui_message(session, user, sent)
    return sent


async def replace_screen(
    callback: CallbackQuery,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    session: AsyncSession | None = None,
    user: User | None = None,
) -> Message | None:
    """
    Replace the message that owned the button with new content.
    Prefer edit; if impossible (photo/caption limits/stale), delete and send fresh.
    Always answers the callback so the spinner stops.
    """
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass

    msg = callback.message
    if msg is None:
        return None

    # Prefer edit for text messages
    if not getattr(msg, "photo", None) and not getattr(msg, "video", None) and not getattr(msg, "document", None):
        try:
            await msg.edit_text(text, reply_markup=reply_markup, disable_web_page_preview=True)
            if session is not None and user is not None:
                await remember_ui_message(session, user, msg)
            return msg
        except TelegramBadRequest:
            pass

    # Photo / media: try caption if short enough
    if getattr(msg, "photo", None) and len(text) <= 1024:
        try:
            await msg.edit_caption(caption=text, reply_markup=reply_markup)
            if session is not None and user is not None:
                await remember_ui_message(session, user, msg)
            return msg
        except TelegramBadRequest:
            pass

    # Fallback: remove old UI and send a new message
    try:
        await msg.delete()
    except TelegramBadRequest:
        try:
            await msg.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass

    sent = await msg.answer(text, reply_markup=reply_markup, disable_web_page_preview=True)
    if session is not None and user is not None:
        await remember_ui_message(session, user, sent)
    return sent
