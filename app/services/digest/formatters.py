"""Format digest cards for Telegram."""

from __future__ import annotations

from app.models import News


def format_news_card(news: News, *, source_count: int | None = None, index: int | None = None) -> str:
    sources = source_count if source_count is not None else len(news.sources or [])
    score = float(news.importance_score)
    category = news.category or "Other"
    prefix = f"{index}. " if index is not None else ""
    return (
        f"{prefix}🔥 <b>{_escape(news.title)}</b>\n\n"
        f"<b>Кратко:</b>\n{_escape(news.summary)}\n\n"
        f"⭐ Важность: {score:.1f}/10\n"
        f"📂 {_escape(category)}\n"
        f"📡 Источники: {sources}"
    )


def format_daily_header(count: int) -> str:
    return f"🗓 <b>Лента дня</b>\nТоп-{count} по важности за последние 24 часа:"


def format_sources_list(news: News) -> str:
    lines = [f"📡 <b>Источники:</b> {_escape(news.title)}", ""]
    for i, src in enumerate(news.sources or [], start=1):
        title = src.channel_title or "Источник"
        lines.append(f'{i}. <a href="{_escape(src.source_url)}">{_escape(title)}</a>')
    if len(lines) == 2:
        lines.append("Нет сохранённых источников.")
    return "\n".join(lines)


def _escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
