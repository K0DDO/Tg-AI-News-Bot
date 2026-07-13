"""Inline keyboards for Briefly — emoji + short labels."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.i18n import LANG_LABELS, SUPPORTED_LANGS, t


def home_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"📖 {t(lang, 'how_to')}", callback_data="onb:0")],
            [
                InlineKeyboardButton(text=f"📰 {t(lang, 'feed')}", callback_data="nav:news"),
                InlineKeyboardButton(text=f"🔥 {t(lang, 'trends')}", callback_data="nav:trends"),
            ],
        ]
    )


def language_keyboard() -> InlineKeyboardMarkup:
    rows = []
    row: list[InlineKeyboardButton] = []
    for code in SUPPORTED_LANGS:
        row.append(InlineKeyboardButton(text=LANG_LABELS[code], callback_data=f"lang:{code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def feed_keyboard(lang: str, *, offset: int, page_ids: list[int], has_more: bool) -> InlineKeyboardMarkup:
    if not page_ids:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"🏠 {t(lang, 'back_home')}", callback_data="nav:home")]
            ]
        )
    ids_s = ",".join(str(i) for i in page_ids)
    rows = [
        [InlineKeyboardButton(text=f"📖 {t(lang, 'details')}", callback_data=f"feed:open:{offset}:0:{ids_s}")]
    ]
    if has_more:
        rows.append(
            [InlineKeyboardButton(text=f"➡ {t(lang, 'next_news')}", callback_data=f"feed:next:{offset}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def detail_keyboard(
    lang: str,
    *,
    offset: int,
    index: int,
    total: int,
    news_id: int,
    ids_s: str,
) -> InlineKeyboardMarkup:
    prev_i = max(0, index - 1)
    next_i = min(total - 1, index + 1)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"◀️ {t(lang, 'prev')}",
                    callback_data=f"feed:open:{offset}:{prev_i}:{ids_s}",
                ),
                InlineKeyboardButton(text=f"{index + 1} / {total}", callback_data="noop"),
                InlineKeyboardButton(
                    text=f"{t(lang, 'next')} ▶️",
                    callback_data=f"feed:open:{offset}:{next_i}:{ids_s}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"❤️ {t(lang, 'interesting')}",
                    callback_data=f"feed:up:{news_id}:{offset}:{index}:{ids_s}",
                ),
                InlineKeyboardButton(
                    text=f"👎 {t(lang, 'not_interesting')}",
                    callback_data=f"feed:down:{news_id}:{offset}:{index}:{ids_s}",
                ),
            ],
            [
                InlineKeyboardButton(text=f"⭐ {t(lang, 'save')}", callback_data=f"feed:fav:{news_id}"),
                InlineKeyboardButton(text=f"📡 {t(lang, 'sources')}", callback_data=f"feed:src:{news_id}"),
            ],
            [
                InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data=f"feed:back:{offset}"),
            ],
        ]
    )


def history_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(lang, "hist_today"), callback_data="hist:d:1"),
                InlineKeyboardButton(text=t(lang, "hist_week"), callback_data="hist:d:7"),
                InlineKeyboardButton(text=t(lang, "hist_all"), callback_data="hist:d:0"),
            ],
            [InlineKeyboardButton(text=f"🔍 {t(lang, 'search')}", callback_data="hist:search")],
        ]
    )


def sources_keyboard(pairs: list[tuple[str, str]], lang: str) -> InlineKeyboardMarkup:
    rows = []
    for i, (label, url) in enumerate(pairs, start=1):
        short = label[:28] + ("…" if len(label) > 28 else "")
        rows.append([InlineKeyboardButton(text=f"🔗 {i}. {short}", url=url)])
    rows.append([InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="feed:srcback")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def onboarding_keyboard(lang: str, step: int, total: int) -> InlineKeyboardMarkup:
    if step >= total - 1:
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=f"🏠 {t(lang, 'back_home')}", callback_data="nav:home")]]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=f"➡ {t(lang, 'next')}", callback_data=f"onb:{step + 1}")]]
    )


def settings_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"📂 {t(lang, 'channels')}", callback_data="set:channels"),
                InlineKeyboardButton(text=f"⭐ {t(lang, 'favorites')}", callback_data="set:favorites"),
            ],
            [InlineKeyboardButton(text=f"📚 {t(lang, 'history')}", callback_data="set:history")],
            [InlineKeyboardButton(text=f"🌐 {t(lang, 'language')}", callback_data="set:lang")],
            [
                InlineKeyboardButton(text=f"🕒 {t(lang, 'set_interval')}", callback_data="set:interval"),
                InlineKeyboardButton(text=f"⭐ {t(lang, 'set_min')}", callback_data="set:min"),
            ],
            [InlineKeyboardButton(text=f"📂 {t(lang, 'set_cats')}", callback_data="set:cats")],
            [InlineKeyboardButton(text=f"🔕 {t(lang, 'set_ignore')}", callback_data="set:ignore")],
            [InlineKeyboardButton(text=f"📊 {t(lang, 'set_reset')}", callback_data="set:reset")],
            [InlineKeyboardButton(text=f"📖 {t(lang, 'how_to')}", callback_data="onb:0")],
            [InlineKeyboardButton(text=f"🔒 {t(lang, 'privacy')}", callback_data="set:privacy")],
        ]
    )


def interval_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="30m", callback_data="set:iv:30"),
                InlineKeyboardButton(text="1h", callback_data="set:iv:60"),
                InlineKeyboardButton(text="6h", callback_data="set:iv:360"),
                InlineKeyboardButton(text="1d", callback_data="set:iv:1440"),
            ],
            [InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="set:back")],
        ]
    )


def min_importance_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="0+", callback_data="set:mi:0"),
                InlineKeyboardButton(text="3+", callback_data="set:mi:3"),
                InlineKeyboardButton(text="5+", callback_data="set:mi:5"),
                InlineKeyboardButton(text="7+", callback_data="set:mi:7"),
            ],
            [InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="set:back")],
        ]
    )


def categories_keyboard(lang: str, enabled: list[str] | None) -> InlineKeyboardMarkup:
    from app.services.preferences import DEFAULT_CATEGORIES

    enabled = enabled or []
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
    rows.append([InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="set:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def channels_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"➕ {t(lang, 'ch_add')}", callback_data="ch:bulk")],
            [InlineKeyboardButton(text=f"📋 {t(lang, 'ch_list')}", callback_data="ch:list")],
        ]
    )


def channel_list_keyboard(items: list[tuple[int, str, bool]], lang: str = "ru") -> InlineKeyboardMarkup:
    rows = []
    for channel_id, title, enabled in items:
        status = "✅" if enabled else "⏸"
        short = title[:22] + ("…" if len(title) > 22 else "")
        rows.append(
            [
                InlineKeyboardButton(text=f"{status} {short}", callback_data=f"ch:tog:{channel_id}"),
                InlineKeyboardButton(text=f"🗑 {t(lang, 'delete')}", callback_data=f"ch:del:{channel_id}"),
            ]
        )
    rows.append([InlineKeyboardButton(text=f"➕ {t(lang, 'ch_add')}", callback_data="ch:bulk")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
