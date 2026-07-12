"""Persistent reply keyboard — localized."""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from app.bot.i18n import btn_channels, btn_favorites, btn_feed, btn_history, btn_search, btn_settings, btn_trends, t


def main_menu(lang: str = "ru") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=btn_feed(lang)), KeyboardButton(text=btn_search(lang))],
            [KeyboardButton(text=btn_channels(lang)), KeyboardButton(text=btn_settings(lang))],
            [KeyboardButton(text=btn_trends(lang)), KeyboardButton(text=btn_favorites(lang))],
            [KeyboardButton(text=btn_history(lang))],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder=t(lang, "pick_section"),
    )
