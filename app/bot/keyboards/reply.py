"""Persistent reply keyboard — primary navigation."""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_NEWS = "📰 Новости"
BTN_SEARCH = "🔍 Поиск"
BTN_CHANNELS = "📂 Каналы"
BTN_SETTINGS = "⚙ Настройки"
BTN_TRENDS = "🔥 В тренде"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_NEWS), KeyboardButton(text=BTN_SEARCH)],
            [KeyboardButton(text=BTN_CHANNELS), KeyboardButton(text=BTN_SETTINGS)],
            [KeyboardButton(text=BTN_TRENDS)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите раздел…",
    )
