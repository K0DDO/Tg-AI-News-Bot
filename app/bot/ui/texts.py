"""Briefly UI formatters — work with Brief / Event presentation."""

from __future__ import annotations

from datetime import datetime, timezone

from app.bot.i18n import t
from app.models import Event
from app.services.events.brief import Brief, BriefBuilderService
from app.utils.relative_dates import resolve_relative_dates

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
_builder = BriefBuilderService()


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


def to_brief(event: Event, lang: str) -> Brief:
    return _builder.build(event, lang=lang)


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


def format_feed(
    lang: str,
    items: list[Event] | list[Brief],
    *,
    title_key: str = "feed_title",
    empty_key: str = "no_more_news",
) -> str:
    if not items:
        return f"🎉 {t(lang, empty_key)}"
    briefs: list[Brief] = []
    for item in items:
        if isinstance(item, Brief):
            briefs.append(item)
        else:
            briefs.append(to_brief(item, lang))
    lines = [f"<b>📰 {t(lang, title_key)}</b>", ""]
    for i, brief in enumerate(briefs, start=1):
        badge = f"  📈 {t(lang, 'updated_badge')}" if brief.updated else ""
        lines.append(f"{circled(i)} <b>{escape(brief.title)}</b>{badge}")
        lines.append(f"⭐ {brief.importance_score:.1f}/10    📂 {escape(brief.category)}    📡 {brief.sources_count}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_news_detail(lang: str, news: Event | Brief, *, index: int, total: int) -> str:
    brief = news if isinstance(news, Brief) else to_brief(news, lang)
    lines = [
        f"<b>{index} / {total}</b>",
        "",
        f"<b>{escape(brief.title)}</b>",
        "",
        escape(brief.summary),
        "",
        f"⭐ <b>{brief.importance_score:.1f}/10</b>",
        f"📂 {escape(brief.category)}",
        f"📡 {brief.sources_count}",
        f"📰 {brief.posts_count}",
    ]
    if brief.topic:
        lines.append(f"🏷 {escape(brief.topic)}")
    if brief.updated:
        lines.append("")
        lines.append(f"📈 {t(lang, 'updated_badge')}: {brief.sources_count} {t(lang, 'sources_n')}")
    return "\n".join(lines)


def format_why(lang: str, news: Event | Brief) -> str:
    brief = news if isinstance(news, Brief) else to_brief(news, lang)
    why = brief.why_important or ""
    parts = [p.strip() for p in why.replace("•", ";").split(";") if p.strip()]
    if not parts:
        parts = [f"{brief.sources_count} {t(lang, 'sources_n')}"]
    lines = [f"⭐ <b>{brief.importance_score:.1f}</b>", "", f"<b>{t(lang, 'why')}</b>", ""]
    for p in parts:
        lines.append(f"• {escape(p)}")
    return "\n".join(lines)


def format_timeline(lang: str, news: Event | Brief) -> str:
    brief = news if isinstance(news, Brief) else to_brief(news, lang)
    lines = [f"🕒 <b>{t(lang, 'timeline')}</b>", f"<i>{escape(brief.title)}</i>", ""]
    if not brief.timeline:
        lines.append("—")
        return "\n".join(lines)
    for entry in brief.timeline[-12:]:
        at = str(entry.get("at") or "")[:16].replace("T", " ")
        text = escape(str(entry.get("text") or entry.get("kind") or ""))
        sources = entry.get("sources")
        lines.append(f"<b>{at}</b>")
        lines.append(text)
        if sources is not None:
            lines.append(f"📡 {sources}")
        lines.append("────────")
    return "\n".join(lines).rstrip("─\n")


def format_sources_screen(lang: str, news: Event | Brief) -> str:
    brief = news if isinstance(news, Brief) else to_brief(news, lang)
    lines = [f"📡 <b>{t(lang, 'sources')}</b>", f"<i>{escape(brief.title)}</i>", ""]
    if not brief.sources:
        lines.append("—")
        return "\n".join(lines)
    for i, src in enumerate(brief.sources, start=1):
        title = escape(src.channel_title or "Channel")
        uname = f" @{src.channel_username}" if src.channel_username else ""
        date = src.published_at.strftime("%d.%m.%Y") if src.published_at else ""
        lines.append(f"{circled(i)} 📰 {title}{uname}")
        if date:
            lines.append(f"   🕒 {date}")
    return "\n".join(lines)


def format_search_answer(lang: str, answer: str, news_items: list[Event]) -> str:
    if not news_items:
        empty = (answer or "").strip() or t(lang, "search_empty")
        return (
            f"🔍 <b>{t(lang, 'search')}</b>\n\n"
            f"❌ <b>{t(lang, 'search_not_found')}</b>\n\n"
            f"{escape(empty)}"
        )
    ref = news_items[0].created_at if news_items else None
    answer_resolved = resolve_relative_dates(answer, ref)
    lines = [f"<b>🤖 {t(lang, 'search_answer')}</b>", "", escape(answer_resolved), ""]
    lines.append(f"<b>{t(lang, 'sources')}</b>")
    lines.append("")
    for i, event in enumerate(news_items[:5], start=1):
        brief = to_brief(event, lang)
        src = brief.sources[0] if brief.sources else None
        channel = escape(src.channel_title if src else (brief.topic or "—"))
        date = ""
        if src and src.published_at:
            date = src.published_at.strftime("%d.%m.%Y")
        url = src.url if src else ""
        lines.append(f"{circled(i)} <b>{escape(brief.title)}</b>")
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
        title = row.get("title") or row.get("topic") or ""
        lines.append(f"🔥 <b>{escape(title)}</b>")
        lines.append(
            f"📡 {row['sources']} {t(lang, 'sources_n')} · "
            f"📰 {row.get('posts_count', row.get('news_count', 0))} {t(lang, 'related_news')}"
        )
        if growth:
            lines.append(f"📈 +{growth} {t(lang, 'today_growth')}")
        lines.append("────────")
        lines.append("")
    return "\n".join(lines).rstrip("─ \n")


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
