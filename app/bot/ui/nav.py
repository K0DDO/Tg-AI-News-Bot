"""Replace Telegram screens in place (edit / delete+send)."""

from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message


async def replace_screen(
    callback: CallbackQuery,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
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
            return msg
        except TelegramBadRequest:
            pass

    # Photo / media: try caption if short enough
    if getattr(msg, "photo", None) and len(text) <= 1024:
        try:
            await msg.edit_caption(caption=text, reply_markup=reply_markup)
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

    return await msg.answer(text, reply_markup=reply_markup, disable_web_page_preview=True)
