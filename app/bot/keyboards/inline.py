"""Inline keyboards for Briefly — emoji + short labels."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.i18n import LANG_LABELS, SUPPORTED_LANGS, t


def language_keyboard(*, prefix: str = "lang") -> InlineKeyboardMarkup:
    flags = {
        "ru": "🇷🇺 Русский",
        "en": "🇬🇧 English",
        "de": "🇩🇪 Deutsch",
        "es": "🇪🇸 Español",
    }
    rows = []
    for code in SUPPORTED_LANGS:
        rows.append(
            [InlineKeyboardButton(text=flags.get(code, LANG_LABELS[code]), callback_data=f"{prefix}:{code}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def onboarding_start_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🍓 {t(lang, 'ob_start_btn')}", callback_data="ob:begin")]
        ]
    )


def privacy_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"✅ {t(lang, 'ob_privacy_ok')}", callback_data="ob:privacy_ok")],
            [
                InlineKeyboardButton(
                    text=f"📜 {t(lang, 'privacy')}",
                    callback_data="ob:privacy_full",
                )
            ],
        ]
    )


def onboarding_channels_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"📡 {t(lang, 'ob_add_channels')}", callback_data="ob:add_ch")],
            [InlineKeyboardButton(text=f"⏭ {t(lang, 'ob_later')}", callback_data="ob:skip_ch")],
        ]
    )


def onboarding_while_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"⚙️ {t(lang, 'ob_configure')}", callback_data="ob:configure")],
            [InlineKeyboardButton(text=f"📖 {t(lang, 'ob_tour')}", callback_data="ob:tour:0")],
            [InlineKeyboardButton(text=f"⏭ {t(lang, 'ob_skip')}", callback_data="ob:finish")],
        ]
    )


def onboarding_tour_keyboard(lang: str, step: int, total: int) -> InlineKeyboardMarkup:
    if step >= total - 1:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"🍓 {t(lang, 'ob_tour_done_btn')}", callback_data="ob:finish")]
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"➡️ {t(lang, 'next')}", callback_data=f"ob:tour:{step + 1}")]
        ]
    )


def onboarding_done_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"📰 {t(lang, 'feed')}", callback_data="nav:news"),
                InlineKeyboardButton(text=f"⚙️ {t(lang, 'settings')}", callback_data="nav:settings"),
            ]
        ]
    )


def empty_feed_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🔎 {t(lang, 'search')}", callback_data="nav:search")],
            [InlineKeyboardButton(text=f"📡 {t(lang, 'ob_add_channels')}", callback_data="ch:bulk")],
            [InlineKeyboardButton(text=f"🔥 {t(lang, 'trends')}", callback_data="nav:trends")],
        ]
    )


def how_to_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🏠 {t(lang, 'back_home')}", callback_data="nav:home")],
        ]
    )


def home_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"📖 {t(lang, 'how_to_use')}", callback_data="nav:howto")],
            [
                InlineKeyboardButton(text=f"📰 {t(lang, 'feed')}", callback_data="nav:news"),
                InlineKeyboardButton(text=f"🔥 {t(lang, 'trends')}", callback_data="nav:trends"),
            ],
        ]
    )


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
            [
                InlineKeyboardButton(
                    text=f"➡ {t(lang, 'next_news')}",
                    callback_data=f"feed:next:{offset}:{ids_s}",
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"➡ {t(lang, 'finish_block')}",
                    callback_data=f"feed:done:{offset}:{ids_s}",
                )
            ]
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
                    callback_data=f"feed:nav:{offset}:{prev_i}:{index}:{ids_s}",
                ),
                InlineKeyboardButton(text=f"{index + 1} / {total}", callback_data="noop"),
                InlineKeyboardButton(
                    text=f"{t(lang, 'next')} ▶️",
                    callback_data=f"feed:nav:{offset}:{next_i}:{index}:{ids_s}",
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


def history_keyboard(
    lang: str,
    items: list[tuple[int, str]] | None = None,
    *,
    days: int = 0,
    page: int = 0,
    total_pages: int = 1,
    query_token: str = "",
) -> InlineKeyboardMarkup:
    """items: (event_id, short_title). days=0 means All."""
    q = query_token or "-"
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text=t(lang, "hist_today"), callback_data=f"hist:d:1:0"),
            InlineKeyboardButton(text=t(lang, "hist_week"), callback_data=f"hist:d:7:0"),
            InlineKeyboardButton(text=t(lang, "hist_all"), callback_data=f"hist:d:0:0"),
        ],
        [InlineKeyboardButton(text=f"🔍 {t(lang, 'search')}", callback_data="hist:search")],
    ]
    for event_id, title in items or []:
        short = (title[:42] + "…") if len(title) > 42 else title
        rows.append(
            [
                InlineKeyboardButton(text=f"📰 {short}", callback_data=f"hist:open:{event_id}"),
                InlineKeyboardButton(text="⭐", callback_data=f"hist:fav:{event_id}"),
                InlineKeyboardButton(text="🗑", callback_data=f"hist:del:{event_id}"),
            ]
        )
    if total_pages > 1:
        prev_p = max(0, page - 1)
        next_p = min(total_pages - 1, page + 1)
        rows.append(
            [
                InlineKeyboardButton(
                    text="⬅️",
                    callback_data=f"hist:d:{days}:{prev_p}:{q}",
                ),
                InlineKeyboardButton(
                    text=f"{page + 1}/{total_pages}",
                    callback_data="noop",
                ),
                InlineKeyboardButton(
                    text="➡️",
                    callback_data=f"hist:d:{days}:{next_p}:{q}",
                ),
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
                InlineKeyboardButton(text=t(lang, "bf_today"), callback_data="set:bf:1"),
                InlineKeyboardButton(text=t(lang, "bf_2d"), callback_data="set:bf:2"),
            ],
            [
                InlineKeyboardButton(text=t(lang, "bf_3d"), callback_data="set:bf:3"),
                InlineKeyboardButton(text=t(lang, "bf_7d"), callback_data="set:bf:7"),
            ],
            [InlineKeyboardButton(text=f"⬅️ {t(lang, 'back')}", callback_data="set:feed")],
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
            [InlineKeyboardButton(text=f"📰 {t(lang, 'set_sec_feed')}", callback_data="set:feed")],
            [InlineKeyboardButton(text=f"📡 {t(lang, 'set_sec_sources')}", callback_data="set:sources")],
            [InlineKeyboardButton(text=f"🌎 {t(lang, 'set_sec_lang')}", callback_data="set:langmenu")],
            [InlineKeyboardButton(text=f"🎯 {t(lang, 'set_sec_personal')}", callback_data="set:personal")],
            [InlineKeyboardButton(text=f"📚 {t(lang, 'history')}", callback_data="set:history")],
            [InlineKeyboardButton(text=f"ℹ️ {t(lang, 'set_sec_info')}", callback_data="set:info")],
        ]
    )


def settings_feed_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"📄 {t(lang, 'set_page_size')}", callback_data="set:pagesize")],
            [InlineKeyboardButton(text=f"🔔 {t(lang, 'set_digests')}", callback_data="set:digests")],
            [InlineKeyboardButton(text=f"🌙 {t(lang, 'set_dnd')}", callback_data="set:dnd")],
            [InlineKeyboardButton(text=f"🌍 {t(lang, 'set_tz')}", callback_data="set:tz")],
            [InlineKeyboardButton(text=f"📥 {t(lang, 'load_news')}", callback_data="set:backfill")],
            [InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="set:back")],
        ]
    )


def settings_sources_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"📂 {t(lang, 'channels')}", callback_data="set:channels")],
            [InlineKeyboardButton(text=f"⭐ {t(lang, 'favorites')}", callback_data="set:favorites")],
            [InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="set:back")],
        ]
    )


def settings_lang_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🌐 {t(lang, 'language')}", callback_data="set:lang")],
            [
                InlineKeyboardButton(
                    text=f"🛠 {t(lang, 'set_news_lang')} 🛠",
                    callback_data="set:newslang",
                )
            ],
            [InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="set:back")],
        ]
    )


def settings_personal_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"📂 {t(lang, 'set_themes')}", callback_data="set:cats")],
            [InlineKeyboardButton(text=f"⭐ {t(lang, 'set_theme_weights')}", callback_data="set:theme_weights")],
            [InlineKeyboardButton(text=f"⭐ {t(lang, 'set_min')}", callback_data="set:min")],
            [InlineKeyboardButton(text=f"📊 {t(lang, 'set_reset')}", callback_data="set:reset")],
            [InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="set:back")],
        ]
    )


def settings_info_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"📖 {t(lang, 'how_to_use')}", callback_data="nav:howto")],
            [InlineKeyboardButton(text=f"🔒 {t(lang, 'privacy')}", callback_data="set:privacy")],
            [InlineKeyboardButton(text=f"ℹ️ {t(lang, 'about')}", callback_data="set:about")],
            [InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="set:back")],
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
            [InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="set:feed")],
        ]
    )


def interval_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Digest cadence (renamed from interval)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "digest_off"), callback_data="set:dm:off")],
            [
                InlineKeyboardButton(text=t(lang, "digest_1h"), callback_data="set:dm:1h"),
                InlineKeyboardButton(text=t(lang, "digest_3h"), callback_data="set:dm:3h"),
            ],
            [
                InlineKeyboardButton(text=t(lang, "digest_6h"), callback_data="set:dm:6h"),
                InlineKeyboardButton(text=t(lang, "digest_daily"), callback_data="set:dm:daily"),
            ],
            [InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="set:feed")],
        ]
    )


def digest_time_keyboard(lang: str) -> InlineKeyboardMarkup:
    times = ["07:00", "08:00", "09:00", "10:00", "12:00", "18:00", "21:00"]
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for tm in times:
        row.append(InlineKeyboardButton(text=tm, callback_data=f"set:dtime:{tm}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="set:digests")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def dnd_keyboard(lang: str, settings) -> InlineKeyboardMarkup:
    on = t(lang, "on") if settings.dnd_enabled else t(lang, "off")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🌙 {t(lang, 'set_dnd')}: {on}",
                    callback_data="set:tog:dnd_enabled",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"Будни {t(lang, 'dnd_pick_start')}: {settings.dnd_weekday_start}",
                    callback_data="set:dndpick:wd:start",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"Будни {t(lang, 'dnd_pick_end')}: {settings.dnd_weekday_end}",
                    callback_data="set:dndpick:wd:end",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"Вых. {t(lang, 'dnd_pick_start')}: {settings.dnd_weekend_start}",
                    callback_data="set:dndpick:we:start",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"Вых. {t(lang, 'dnd_pick_end')}: {settings.dnd_weekend_end}",
                    callback_data="set:dndpick:we:end",
                )
            ],
            [InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="set:feed")],
        ]
    )


def dnd_time_pick_keyboard(lang: str, *, kind: str, which: str) -> InlineKeyboardMarkup:
    """kind=wd|we, which=start|end — grid of common times."""
    times = [
        "00:00", "01:00", "06:00", "07:00", "08:00", "08:30",
        "09:00", "10:00", "22:00", "22:30", "23:00", "23:30",
    ]
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for tm in times:
        row.append(
            InlineKeyboardButton(text=tm, callback_data=f"set:dndt:{kind}:{which}:{tm}")
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="set:dnd")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def timezone_keyboard(lang: str) -> InlineKeyboardMarkup:
    from app.services.time_prefs import POPULAR_TIMEZONES

    rows: list[list[InlineKeyboardButton]] = []
    for tz in POPULAR_TIMEZONES:
        rows.append([InlineKeyboardButton(text=tz, callback_data=f"set:tzset:{tz}")])
    rows.append([InlineKeyboardButton(text=f"✏️ {t(lang, 'tz_custom')}", callback_data="set:tzcustom")])
    rows.append([InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="set:feed")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def min_importance_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="0+", callback_data="set:mi:0"),
                InlineKeyboardButton(text="3+", callback_data="set:mi:3"),
                InlineKeyboardButton(text="5+", callback_data="set:mi:5"),
                InlineKeyboardButton(text="7+", callback_data="set:mi:7"),
            ],
            [InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="set:personal")],
        ]
    )


def categories_keyboard(lang: str, enabled: list[str] | None) -> InlineKeyboardMarkup:
    from app.services.categories import DEFAULT_CATEGORIES, THEME_LAYOUT_LONG, THEMES, theme_display

    enabled_set = set(enabled or [])
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for key in DEFAULT_CATEGORIES:
        mark = "✓" if key in enabled_set else "□"
        label = theme_display(key)
        btn = InlineKeyboardButton(text=f"{mark} {label}", callback_data=f"set:cat:{key}")
        if key in THEME_LAYOUT_LONG:
            if row:
                rows.append(row)
                row = []
            rows.append([btn])
        else:
            row.append(btn)
            if len(row) == 2:
                rows.append(row)
                row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="set:personal")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def theme_weights_keyboard(
    lang: str,
    weights: dict[str, int] | None,
    enabled: list[str] | None = None,
) -> InlineKeyboardMarkup:
    from app.services.categories import DEFAULT_CATEGORIES, theme_display

    weights = weights or {}
    keys = [k for k in (enabled or DEFAULT_CATEGORIES) if k in DEFAULT_CATEGORIES]
    if not keys:
        keys = list(DEFAULT_CATEGORIES)
    rows: list[list[InlineKeyboardButton]] = []
    for key in keys:
        stars = max(1, min(5, int(weights.get(key, 3))))
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{theme_display(key)} · {stars}⭐",
                    callback_data=f"set:tw:{key}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=f"🔙 {t(lang, 'back')}", callback_data="set:personal")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def theme_weight_pick_keyboard(lang: str, theme: str) -> InlineKeyboardMarkup:
    from app.services.categories import theme_display

    rows = [
        [
            InlineKeyboardButton(text=f"{n}⭐", callback_data=f"set:twset:{theme}:{n}")
            for n in range(1, 6)
        ]
    ]
    rows.append(
        [InlineKeyboardButton(text=f"🔙 {theme_display(theme)}", callback_data="set:theme_weights")]
    )
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
