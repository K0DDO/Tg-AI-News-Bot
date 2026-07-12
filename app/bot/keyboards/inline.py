"""Inline keyboards for feed, detail, settings, onboarding."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📖 Как пользоваться", callback_data="onb:0")],
            [
                InlineKeyboardButton(text="📰 Новости", callback_data="nav:news"),
                InlineKeyboardButton(text="🔥 Тренды", callback_data="nav:trends"),
            ],
        ]
    )


def feed_keyboard(*, offset: int, page_ids: list[int], has_more: bool) -> InlineKeyboardMarkup:
    ids_s = ",".join(str(i) for i in page_ids) if page_ids else ""
    rows = [
        [
            InlineKeyboardButton(text="📖 Подробнее", callback_data=f"feed:open:{offset}:0:{ids_s}"),
        ]
    ]
    if has_more:
        rows.append(
            [InlineKeyboardButton(text="➡ Следующие новости", callback_data=f"feed:next:{offset}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def detail_keyboard(*, offset: int, index: int, total: int, news_id: int, ids_s: str) -> InlineKeyboardMarkup:
    prev_i = max(0, index - 1)
    next_i = min(total - 1, index + 1)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="◀️", callback_data=f"feed:open:{offset}:{prev_i}:{ids_s}"),
                InlineKeyboardButton(text=f"{index + 1} / {total}", callback_data="noop"),
                InlineKeyboardButton(text="▶️", callback_data=f"feed:open:{offset}:{next_i}:{ids_s}"),
            ],
            [
                InlineKeyboardButton(text="❤️ Интересно", callback_data=f"feed:up:{news_id}:{offset}:{index}:{ids_s}"),
                InlineKeyboardButton(text="👎 Не интересно", callback_data=f"feed:down:{news_id}:{offset}:{index}:{ids_s}"),
                InlineKeyboardButton(text="🔙 Назад", callback_data=f"feed:back:{offset}"),
            ],
            [
                InlineKeyboardButton(text="📡 Источники", callback_data=f"feed:src:{news_id}"),
            ],
        ]
    )


def sources_keyboard(pairs: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """pairs: (label, url)"""
    rows = []
    for i, (label, url) in enumerate(pairs, start=1):
        short = label[:28] + ("…" if len(label) > 28 else "")
        rows.append([InlineKeyboardButton(text=f"🔗 {i}. {short}", url=url)])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="feed:srcback")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def onboarding_keyboard(step: int, total: int) -> InlineKeyboardMarkup:
    if step >= total - 1:
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="✨ В меню", callback_data="nav:home")]]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Далее →", callback_data=f"onb:{step + 1}")]]
    )


def settings_keyboard(settings) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🕒 Частота обновления", callback_data="set:interval")],
            [InlineKeyboardButton(text="⭐ Мин. важность", callback_data="set:min")],
            [InlineKeyboardButton(text="📂 Категории", callback_data="set:cats")],
            [InlineKeyboardButton(text="🔕 Игнорируемые темы", callback_data="set:ignore")],
            [InlineKeyboardButton(text="📊 Сбросить реакции", callback_data="set:reset")],
            [InlineKeyboardButton(text="📖 Как пользоваться", callback_data="onb:0")],
            [InlineKeyboardButton(text="🔒 Конфиденциальность", callback_data="set:privacy")],
        ]
    )


def interval_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="30 мин", callback_data="set:iv:30"),
                InlineKeyboardButton(text="1 час", callback_data="set:iv:60"),
            ],
            [
                InlineKeyboardButton(text="6 часов", callback_data="set:iv:360"),
                InlineKeyboardButton(text="1 день", callback_data="set:iv:1440"),
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="set:back")],
        ]
    )


def min_importance_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="0+", callback_data="set:mi:0"),
                InlineKeyboardButton(text="3+", callback_data="set:mi:3"),
                InlineKeyboardButton(text="5+", callback_data="set:mi:5"),
                InlineKeyboardButton(text="7+", callback_data="set:mi:7"),
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="set:back")],
        ]
    )


def categories_keyboard(enabled: list[str] | None) -> InlineKeyboardMarkup:
    enabled = enabled or []
    from app.services.preferences import DEFAULT_CATEGORIES

    rows = []
    row: list[InlineKeyboardButton] = []
    for cat in DEFAULT_CATEGORIES:
        mark = "✅" if cat in enabled else "⬜️"
        row.append(InlineKeyboardButton(text=f"{mark} {cat}", callback_data=f"set:cat:{cat}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="set:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def channels_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить списком", callback_data="ch:bulk")],
            [InlineKeyboardButton(text="📋 Мои каналы", callback_data="ch:list")],
        ]
    )


def channel_list_keyboard(items: list[tuple[int, str, bool]]) -> InlineKeyboardMarkup:
    rows = []
    for channel_id, title, enabled in items:
        status = "✅" if enabled else "⏸"
        short = title[:24] + ("…" if len(title) > 24 else "")
        rows.append(
            [
                InlineKeyboardButton(text=f"{status} {short}", callback_data=f"ch:tog:{channel_id}"),
                InlineKeyboardButton(text="🗑", callback_data=f"ch:del:{channel_id}"),
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ Добавить", callback_data="ch:bulk")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
