"""Briefly UI formatters."""

from __future__ import annotations

from datetime import datetime, timezone

from app.bot.i18n import t
from app.models import News

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"


def escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def circled(n: int) -> str:
    if 1 <= n <= 10:
        return CIRCLED[n - 1]
    return f"{n}."


def format_home(lang: str, *, messages: int, news: int, avg_importance: float, last_update: datetime | None) -> str:
    if last_update is None:
        updated = "—"
    else:
        if last_update.tzinfo is None:
            last_update = last_update.replace(tzinfo=timezone.utc)
        updated = last_update.astimezone().strftime("%d.%m %H:%M")
    return (
        f"<b>📰 {t(lang, 'brand')}</b>\n\n"
        f"{t(lang, 'welcome')}\n\n"
        f"<b>{t(lang, 'today_stats')}</b>\n"
        f"📨 {t(lang, 'messages')}: <b>{messages}</b>\n"
        f"📰 {t(lang, 'news_count')}: <b>{news}</b>\n"
        f"⭐ {t(lang, 'avg_score')}: <b>{avg_importance:.1f}</b>\n"
        f"🕒 {t(lang, 'updated')}: <b>{updated}</b>"
    )


def format_feed(lang: str, items: list[News], *, title_key: str = "feed_title", empty_key: str = "no_more_news") -> str:
    if not items:
        return f"🎉 {t(lang, empty_key)}"
    lines = [f"<b>📰 {t(lang, title_key)}</b>", ""]
    for i, news in enumerate(items, start=1):
        sources = news.sources_count or len(news.sources or [])
        score = float(news.importance_score)
        cat = escape(news.category or "Other")
        badge = ""
        if sources >= 2 and news.updated_at and news.created_at and news.updated_at > news.created_at:
            badge = f"  📈 {t(lang, 'updated_badge')}"
        lines.append(f"{circled(i)} <b>{escape(news.localized_title(lang))}</b>{badge}")
        lines.append(f"⭐ {score:.1f}/10    📂 {cat}    📡 {sources}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_news_detail(lang: str, news: News, *, index: int, total: int) -> str:
    sources = news.sources_count or len(news.sources or [])
    score = float(news.importance_score)
    cat = escape(news.category or "Other")
    topic = escape(news.topic) if news.topic else None
    lines = [
        f"<b>{index} / {total}</b>",
        "",
        f"<b>{escape(news.localized_title(lang))}</b>",
        "",
        escape(news.localized_summary(lang)),
        "",
        f"⭐ <b>{score:.1f}/10</b>",
        f"📂 {cat}",
        f"📡 {sources}",
    ]
    if topic:
        lines.append(f"🏷 {topic}")
    if sources >= 2:
        lines.append("")
        lines.append(f"📈 {t(lang, 'updated_badge')}: {sources} {t(lang, 'sources_n')}")
    return "\n".join(lines)


def format_why(lang: str, news: News) -> str:
    score = float(news.importance_score)
    sources = news.sources_count or len(news.sources or [])
    why = news.why_important or ""
    parts = [p.strip() for p in why.replace("•", ";").split(";") if p.strip()]
    if not parts:
        parts = [
            f"{sources} sources" if lang != "ru" else f"{sources} источников",
        ]
    lines = [f"⭐ <b>{score:.1f}</b>", "", f"<b>{t(lang, 'why')}</b>", ""]
    for p in parts:
        lines.append(f"• {escape(p)}")
    return "\n".join(lines)


def format_sources_screen(lang: str, news: News) -> str:
    lines = [f"📡 <b>{t(lang, 'sources')}</b>", f"<i>{escape(news.localized_title(lang))}</i>", ""]
    if not news.sources:
        lines.append("—")
        return "\n".join(lines)
    for i, src in enumerate(news.sources, start=1):
        title = escape(src.channel_title or "Channel")
        uname = f" @{src.channel_username}" if src.channel_username else ""
        date = src.created_at.strftime("%d.%m.%Y") if src.created_at else ""
        lines.append(f"{circled(i)} 📰 {title}{uname}")
        if date:
            lines.append(f"   🕒 {date}")
    return "\n".join(lines)


def format_search_answer(lang: str, answer: str, news_items: list[News]) -> str:
    lines = [f"<b>🤖 {t(lang, 'search_answer')}</b>", "", escape(answer), ""]
    if news_items:
        lines.append(f"<b>{t(lang, 'sources')}</b>")
        lines.append("")
        for i, news in enumerate(news_items[:5], start=1):
            src = (news.sources or [None])[0]
            channel = escape(src.channel_title if src else (news.topic or "—"))
            date = ""
            if src and src.created_at:
                date = src.created_at.strftime("%d.%m.%Y")
            elif news.created_at:
                date = news.created_at.strftime("%d.%m.%Y")
            url = src.source_url if src else ""
            lines.append(f"{circled(i)} <b>{escape(news.localized_title(lang))}</b>")
            lines.append(f"   📰 {channel}" + (f" · {date}" if date else ""))
            if url:
                lines.append(f'   🔗 <a href="{escape(url)}">link</a>')
            lines.append("")
    return "\n".join(lines).rstrip()


def format_trends(lang: str, rows: list[dict]) -> str:
    if not rows:
        return f"<b>🔥 {t(lang, 'trends')}</b>\n\n—"
    lines = [f"<b>🔥 {t(lang, 'trends')}</b>", ""]
    for row in rows:
        growth = row.get("growth_today") or 0
        lines.append(f"🔥 <b>{escape(row['topic'])}</b>")
        lines.append(
            f"📡 {row['sources']} {t(lang, 'sources_n')} · "
            f"📰 {row['news_count']} {t(lang, 'related_news')}"
        )
        if growth:
            lines.append(f"↑ +{growth} {t(lang, 'today_growth')}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_settings(lang: str, settings) -> str:
    cats = settings.enabled_categories or []
    cats_s = ", ".join(cats) if cats else "—"
    interval = settings.update_interval_minutes
    if interval < 60:
        iv = f"{interval}m"
    elif interval < 1440:
        iv = f"{interval // 60}h"
    else:
        iv = f"{interval // 1440}d"
    return (
        f"<b>⚙ {t(lang, 'settings')}</b>\n\n"
        f"🌐 {t(lang, 'language')}: <b>{settings.language}</b>\n"
        f"🕒 {iv}\n"
        f"⭐ {settings.min_importance:.1f}+\n"
        f"📂 {escape(cats_s)}\n"
        f"🔕 {escape(settings.ignored_topics or '—')}"
    )


def format_privacy(lang: str) -> str:
    if lang == "en":
        return (
            "<b>🔒 Privacy</b>\n\n"
            "We store: Telegram ID, channels, reactions, reading history, settings.\n"
            "Used only to personalize your feed. Not sold to third parties.\n"
            "Reset reactions in Settings; full deletion on request."
        )
    return (
        "<b>🔒 Политика конфиденциальности</b>\n\n"
        "Храним: Telegram ID, каналы, реакции, историю просмотров, настройки.\n"
        "Только для персональной ленты. Не продаём третьим лицам.\n"
        "Сброс реакций — в настройках; полное удаление — по запросу."
    )


def onboarding_steps(lang: str) -> list[tuple[str, str]]:
    return [
        (t(lang, "onb_1_t"), t(lang, "onb_1_b")),
        (t(lang, "onb_2_t"), t(lang, "onb_2_b")),
        (t(lang, "onb_3_t"), t(lang, "onb_3_b")),
        (t(lang, "onb_4_t"), t(lang, "onb_4_b")),
        (t(lang, "onb_done_t"), t(lang, "onb_done_b")),
    ]
