from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def news_keyboard(news_id: int, *, show_more: bool = False, offset: int = 0) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="❤️ Интересно", callback_data=f"react:up:{news_id}"),
            InlineKeyboardButton(text="👎 Не интересно", callback_data=f"react:down:{news_id}"),
        ],
        [
            InlineKeyboardButton(text="📚 Подробнее", callback_data=f"news:more:{news_id}"),
            InlineKeyboardButton(text="📡 Источники", callback_data=f"news:src:{news_id}"),
        ],
    ]
    if show_more:
        rows.append(
            [InlineKeyboardButton(text="Показать больше", callback_data=f"digest:more:{offset}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def channels_keyboard(
    items: list[tuple[int, str, bool, bool]],
) -> InlineKeyboardMarkup:
    """items: (channel_id, title, channel_enabled, user_active)."""
    rows: list[list[InlineKeyboardButton]] = []
    for channel_id, title, enabled, active in items:
        status = "✅" if enabled and active else "⏸"
        short = title[:28] + ("…" if len(title) > 28 else "")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {short}",
                    callback_data=f"ch:info:{channel_id}",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="Вкл парсинг" if not enabled else "Выкл парсинг",
                    callback_data=f"ch:toggle:{channel_id}",
                ),
                InlineKeyboardButton(
                    text="Удалить у меня",
                    callback_data=f"ch:rm:{channel_id}",
                ),
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ Добавить канал", callback_data="ch:add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
