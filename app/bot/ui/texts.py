"""Bot UI copy and formatters — single visual language."""

from __future__ import annotations

from datetime import datetime, timezone

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


def format_home(
    *,
    messages: int,
    news: int,
    avg_importance: float,
    last_update: datetime | None,
) -> str:
    if last_update is None:
        updated = "—"
    else:
        if last_update.tzinfo is None:
            last_update = last_update.replace(tzinfo=timezone.utc)
        updated = last_update.astimezone().strftime("%d.%m %H:%M")
    return (
        "<b>📰 AI News Assistant</b>\n\n"
        "Добро пожаловать!\n\n"
        "<b>Сегодня обработано</b>\n"
        f"📨 Сообщений: <b>{messages}</b>\n"
        f"📰 Новостей: <b>{news}</b>\n"
        f"⭐ Средняя важность: <b>{avg_importance:.1f}</b>\n"
        f"🕒 Обновление: <b>{updated}</b>"
    )


def format_feed(items: list[News], *, offset: int = 0) -> str:
    if not items:
        return "На данный момент это все новые новости 🎉"
    lines = ["<b>📰 Лента новостей</b>", ""]
    for i, news in enumerate(items, start=1):
        idx = circled(i)
        sources = len(news.sources or [])
        score = float(news.importance_score)
        cat = escape(news.category or "Other")
        lines.append(f"{idx} <b>{escape(news.title)}</b>")
        lines.append(f"⭐ {score:.1f}/10    📂 {cat}    📡 {sources}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_news_detail(news: News, *, index: int, total: int) -> str:
    sources = len(news.sources or [])
    score = float(news.importance_score)
    cat = escape(news.category or "Other")
    return (
        f"<b>{index} / {total}</b>\n\n"
        f"<b>{escape(news.title)}</b>\n\n"
        f"{escape(news.summary)}\n\n"
        f"⭐ <b>{score:.1f}/10</b>\n"
        f"📂 {cat}\n"
        f"📡 {sources} источн."
    )


def format_sources_screen(news: News) -> str:
    lines = [f"📡 <b>Источники</b>", f"<i>{escape(news.title)}</i>", ""]
    if not news.sources:
        lines.append("Источников пока нет.")
        return "\n".join(lines)
    for i, src in enumerate(news.sources, start=1):
        title = escape(src.channel_title or "Канал")
        lines.append(f"{circled(i)} 📰 {title}")
    return "\n".join(lines)


def format_search_answer(answer: str, hits: list) -> str:
    lines = ["<b>🤖 AI ответ</b>", "", escape(answer), "", "<b>Источники</b>", ""]
    for i, hit in enumerate(hits[:5], start=1):
        lines.append(f"{circled(i)} {escape(hit.title)}")
    return "\n".join(lines)


def format_trends(topics: list[tuple[str, int]]) -> str:
    if not topics:
        return "<b>🔥 В тренде</b>\n\nПока недостаточно данных."
    lines = ["<b>🔥 В тренде</b>", ""]
    for i, (topic, count) in enumerate(topics, start=1):
        lines.append(f"{i}. <b>{escape(topic)}</b>")
        lines.append(f"   📡 {count} источников")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_settings(settings) -> str:
    cats = settings.enabled_categories or []
    cats_s = ", ".join(cats) if cats else "все"
    interval = settings.update_interval_minutes
    if interval < 60:
        iv = f"{interval} мин"
    elif interval < 1440:
        iv = f"{interval // 60} ч"
    else:
        iv = f"{interval // 1440} д"
    ignored = settings.ignored_topics or "—"
    return (
        "<b>⚙ Настройки</b>\n\n"
        f"🕒 Обновление: <b>{iv}</b>\n"
        f"⭐ Мин. важность: <b>{settings.min_importance:.1f}</b>\n"
        f"📂 Категории: <b>{escape(cats_s)}</b>\n"
        f"🔕 Игнор: <b>{escape(ignored)}</b>"
    )


def format_privacy() -> str:
    return (
        "<b>🔒 Политика конфиденциальности</b>\n\n"
        "Мы храним только то, что нужно для работы бота:\n"
        "• ваш Telegram ID и username\n"
        "• список каналов\n"
        "• реакции и прочитанные новости\n"
        "• настройки ленты\n\n"
        "Сообщения каналов обрабатываются для сводок. "
        "Данные не продаём и не передаём третьим лицам.\n\n"
        "Чтобы удалить данные — напишите в поддержку или используйте "
        "сброс реакций в настройках (полный wipe по запросу)."
    )


ONBOARDING_STEPS = [
    (
        "Шаг 1 · Новости",
        "Лента показывает топ событий без воды.\n"
        "Открой «Подробнее», чтобы читать по одной.",
    ),
    (
        "Шаг 2 · Поиск",
        "Спроси как у Perplexity:\n"
        "«Что нового по NVIDIA?» — получишь AI-ответ и источники.",
    ),
    (
        "Шаг 3 · Каналы",
        "Добавляй каналы списком @username или ссылками t.me — сразу пачкой.",
    ),
    (
        "Шаг 4 · Настройки",
        "Настрой важность, категории и частоту.\n"
        "Лента станет только про то, что важно тебе.",
    ),
    (
        "Готово ✨",
        "Главное меню всегда снизу.\n"
        "Команды тоже работают — но кнопки удобнее.",
    ),
]
