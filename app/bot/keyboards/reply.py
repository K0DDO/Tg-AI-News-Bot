"""Persistent reply keyboard — compact Briefly app menu."""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from app.bot.i18n import btn_feed, btn_search, btn_settings, btn_trends, t


def main_menu(lang: str = "ru") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=btn_feed(lang)), KeyboardButton(text=btn_search(lang))],
            [KeyboardButton(text=btn_trends(lang)), KeyboardButton(text=btn_settings(lang))],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder=t(lang, "pick_section"),
    )
