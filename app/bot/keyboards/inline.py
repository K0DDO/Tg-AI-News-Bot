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


def language_keyboard(*, prefix: str = "lang") -> InlineKeyboardMarkup:
    rows = []
    row: list[InlineKeyboardButton] = []
    for code in SUPPORTED_LANGS:
        row.append(InlineKeyboardButton(text=LANG_LABELS[code], callback_data=f"{prefix}:{code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def add_channels_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"➕ {t(lang, 'ch_add')}", callback_data="ch:bulk")],
            [InlineKeyboardButton(text=f"📂 {t(lang, 'channels')}", callback_data="set:channels")],
        ]
    )


def feed_keyboard(lang: str, *, offset: int, page_ids: list[int], has_more: bool) -> InlineKeyboardMarkup:
    if not page_ids:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"📥 {t(lang, 'load_news')}", callback_data="set:backfill")],
                [InlineKeyboardButton(text=f"🏠 {t(lang, 'back_home')}", callback_data="nav:home")],
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
    rows.append([InlineKeyboardButton(text=f"📥 {t(lang, 'load_news')}", callback_data="set:backfill")])
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


def history_keyboard(lang: str, items: list[tuple[int, str]] | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text=t(lang, "hist_today"), callback_data="hist:d:1"),
            InlineKeyboardButton(text=t(lang, "hist_week"), callback_data="hist:d:7"),
            InlineKeyboardButton(text=t(lang, "hist_all"), callback_data="hist:d:0"),
        ],
        [InlineKeyboardButton(text=f"🔍 {t(lang, 'search')}", callback_data="hist:search")],
    ]
    for event_id, title in (items or [])[:8]:
        short = (title[:24] + "…") if len(title) > 24 else title
        rows.append(
            [
                InlineKeyboardButton(text=f"📖 {short}", callback_data=f"hist:open:{event_id}"),
                InlineKeyboardButton(text=f"⭐", callback_data=f"hist:fav:{event_id}"),
                InlineKeyboardButton(text=f"🗑", callback_data=f"hist:del:{event_id}"),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def search_external_keyboard(lang: str, query_token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🌍 {t(lang, 'show_external')}",
                    callback_data=f"search:ext:{query_token}",
                )
            ]
        ]
    )


def search_result_keyboard(
    lang: str,
    *,
    token: str,
    has_external: bool = False,
    has_explain: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_explain:
        rows.append(
            [InlineKeyboardButton(text=f"❔ {t(lang, 'why_found')}", callback_data=f"search:why:{token}")]
        )
    rows.append(
        [InlineKeyboardButton(text=f"🔬 {t(lang, 'deep_search')}", callback_data=f"search:deep:{token}")]
    )
    if has_external:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🌍 {t(lang, 'show_external')}",
                    callback_data=f"search:ext:{token}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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


def backfill_period_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(lang, "bf_1d"), callback_data="set:bf:1"),
                InlineKeyboardButton(text=t(lang, "bf_2d"), callback_data="set:bf:2"),
            ],
            [
                InlineKeyboardButton(text=t(lang, "bf_7d"), callback_data="set:bf:7"),
                InlineKeyboardButton(text=t(lang, "bf_14d"), callback_data="set:bf:14"),
            ],
            [InlineKeyboardButton(text=t(lang, "bf_30d"), callback_data="set:bf:30")],
            [InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="set:back")],
        ]
    )


def backfill_progress_keyboard(lang: str, job_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🔄 {t(lang, 'bf_refresh')}",
                    callback_data=f"set:bfprog:{job_id}",
                )
            ],
            [InlineKeyboardButton(text=f"📰 {t(lang, 'feed')}", callback_data="nav:news")],
            [InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="set:back")],
        ]
    )


def settings_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"📂 {t(lang, 'channels')}", callback_data="set:channels"),
                InlineKeyboardButton(text=f"⭐ {t(lang, 'favorites')}", callback_data="set:favorites"),
            ],
            [InlineKeyboardButton(text=f"📚 {t(lang, 'history')}", callback_data="set:history")],
            [InlineKeyboardButton(text=f"📥 {t(lang, 'load_news')}", callback_data="set:backfill")],
            [InlineKeyboardButton(text=f"🌐 {t(lang, 'language')}", callback_data="set:lang")],
            [InlineKeyboardButton(text=f"🗣 {t(lang, 'set_news_lang')}", callback_data="set:newslang")],
            [InlineKeyboardButton(text=f"📄 {t(lang, 'set_page_size')}", callback_data="set:pagesize")],
            [
                InlineKeyboardButton(text=f"🔔 {t(lang, 'notifications')}", callback_data="set:tog:notifications_enabled"),
                InlineKeyboardButton(text=f"🌍 {t(lang, 'include_external')}", callback_data="set:tog:include_external_news"),
            ],
            [InlineKeyboardButton(text=f"📝 {t(lang, 'show_summary')}", callback_data="set:tog:show_summary")],
            [
                InlineKeyboardButton(text=f"🕒 {t(lang, 'set_interval')}", callback_data="set:interval"),
                InlineKeyboardButton(text=f"⭐ {t(lang, 'set_min')}", callback_data="set:min"),
            ],
            [InlineKeyboardButton(text=f"📂 {t(lang, 'set_cats')}", callback_data="set:cats")],
            [InlineKeyboardButton(text=f"🔕 {t(lang, 'set_ignore')}", callback_data="set:ignore")],
            [InlineKeyboardButton(text=f"📊 {t(lang, 'set_reset')}", callback_data="set:reset")],
            [InlineKeyboardButton(text=f"📖 {t(lang, 'tutorial')}", callback_data="onb:0")],
            [InlineKeyboardButton(text=f"🔒 {t(lang, 'privacy')}", callback_data="set:privacy")],
        ]
    )


def page_size_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="3", callback_data="set:ps:3"),
                InlineKeyboardButton(text="5", callback_data="set:ps:5"),
                InlineKeyboardButton(text="8", callback_data="set:ps:8"),
                InlineKeyboardButton(text="10", callback_data="set:ps:10"),
            ],
            [InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="set:back")],
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
