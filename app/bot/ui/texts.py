"""Briefly UI formatters — work with Brief / Event presentation."""

from __future__ import annotations

from datetime import datetime, timezone

from app.bot.i18n import t
from app.models import Event
from app.services.categories import normalize_category, theme_display
from app.services.events.brief import Brief, BriefBuilderService
from app.utils.relative_dates import resolve_relative_dates
from app.utils.title_case import normalize_title

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


def format_meta_line(
    *,
    score: float,
    category: str,
    sources: int,
    posts: int,
    first_seen: datetime | None = None,
) -> str:
    cat_label = theme_display(normalize_category(category))
    line = f"⭐️ {score:.1f}/10 • 📂 {escape(cat_label)} • 📡 {sources} • 📰 {posts}"
    if first_seen is not None:
        ts = first_seen
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        line += f" • 🗓 {ts.strftime('%d.%m')}"
    return line


def to_brief(event: Event, lang: str, *, show_summary: bool = True) -> Brief:
    return _builder.build(event, lang=lang, show_summary=show_summary)


def format_home(
    lang: str,
    *,
    messages: int | None = None,
    news: int | None = None,
    avg_importance: float | None = None,
    last_update: datetime | None = None,
    read: int = 0,
    saved: int = 0,
    liked: int = 0,
) -> str:
    if last_update is None:
        updated = "—"
    else:
        if last_update.tzinfo is None:
            last_update = last_update.replace(tzinfo=timezone.utc)
        updated = last_update.astimezone().strftime("%d.%m %H:%M")
    lines = [
        f"<b>🍓 {t(lang, 'brand')}</b>",
        "",
        t(lang, "welcome"),
        "",
        f"<b>{t(lang, 'your_stats')}</b>",
        f"👁 {t(lang, 'stat_read')}: <b>{read}</b>",
        f"⭐ {t(lang, 'stat_saved')}: <b>{saved}</b>",
        f"❤️ {t(lang, 'stat_liked')}: <b>{liked}</b>",
        f"🕒 {t(lang, 'updated')}: <b>{updated}</b>",
    ]
    return "\n".join(lines)


def format_feed(
    lang: str,
    items: list[Event] | list[Brief],
    *,
    title_key: str = "feed_title",
    empty_key: str = "no_more_news",
    empty_plain: str | None = None,
) -> str:
    if not items:
        if empty_plain:
            return empty_plain
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
        lines.append(
            format_meta_line(
                score=brief.importance_score,
                category=brief.category,
                sources=brief.sources_count,
                posts=brief.posts_count,
                first_seen=brief.first_seen,
            )
        )
        lines.append("")
    return "\n".join(lines).rstrip()


def format_news_detail(
    lang: str,
    news: Event | Brief,
    *,
    index: int,
    total: int,
    show_summary: bool = True,
    related: list[Event] | None = None,
) -> str:
    brief = news if isinstance(news, Brief) else to_brief(news, lang, show_summary=show_summary)
    lines = [
        f"<b>{index} / {total}</b>",
        "",
        f"<b>{escape(brief.title)}</b>",
        "",
    ]
    if show_summary and brief.summary:
        lines.append(escape(brief.summary))
        lines.append("")
    lines.append(
        format_meta_line(
            score=brief.importance_score,
            category=brief.category,
            sources=brief.sources_count,
            posts=brief.posts_count,
            first_seen=brief.first_seen,
        )
    )
    if brief.topic:
        lines.append(f"🏷 {escape(brief.topic)}")
    if brief.updated:
        lines.append("")
        lines.append(f"📈 {t(lang, 'updated_badge')}: {brief.sources_count} {t(lang, 'sources_n')}")
    if related:
        lines.append("")
        lines.append(f"<b>{t(lang, 'related_events')}</b>")
        for ev in related[:4]:
            lines.append(f"• {escape(normalize_title(ev.title))}")
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
        author = escape(src.author) if src.author else "—"
        lines.append(f"{circled(i)} 📰 {title}{uname}")
        if date:
            lines.append(f"   🕒 {date}")
        lines.append(f"   ✍️ {t(lang, 'author')}: {author}")
        if src.url:
            lines.append(f'   🔗 <a href="{escape(src.url)}">link</a>')
    return "\n".join(lines)


def format_search_answer(
    lang: str,
    answer: str,
    news_items: list[Event],
    *,
    external_count: int = 0,
    related_questions: list[str] | None = None,
    matched_nodes: list[str] | None = None,
) -> str:
    if not news_items:
        empty = (answer or "").strip() or t(lang, "search_empty")
        return (
            f"🔍 <b>{t(lang, 'search')}</b>\n\n"
            f"❌ <b>{t(lang, 'search_not_found')}</b>\n\n"
            f"{escape(empty)}"
        )
    ref = news_items[0].created_at if news_items else None
    answer_resolved = resolve_relative_dates(answer, ref)
    lines = [f"<b>🤖 {t(lang, 'search_answer')}</b>", ""]
    if matched_nodes:
        lines.append("🧭 " + ", ".join(escape(n) for n in matched_nodes[:6]))
        lines.append("")
    lines.append(escape(answer_resolved))
    lines.append("")
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
        lines.append(
            format_meta_line(
                score=brief.importance_score,
                category=brief.category,
                sources=brief.sources_count,
                posts=brief.posts_count,
            )
        )
        lines.append(f"   📰 {channel}" + (f" · {date}" if date else ""))
        if url:
            lines.append(f'   🔗 <a href="{escape(url)}">link</a>')
        lines.append("")
    if related_questions:
        lines.append(f"<b>{t(lang, 'related_questions')}</b>")
        for q in related_questions[:4]:
            lines.append(f"• {escape(q)}")
        lines.append("")
    if external_count > 0:
        lines.append(t(lang, "search_external_hint").format(n=external_count))
    return "\n".join(lines).rstrip()


def format_search_explain(lang: str, explanations: dict[int, list[str]], events: list[Event]) -> str:
    lines = [f"<b>❔ {t(lang, 'why_found')}</b>", ""]
    by_id = {e.id: e for e in events}
    for eid, reasons in explanations.items():
        ev = by_id.get(eid)
        title = normalize_title(ev.title) if ev else f"#{eid}"
        lines.append(f"<b>{escape(title)}</b>")
        for r in reasons:
            lines.append(f"✔ {escape(r)}")
        lines.append("")
    if len(lines) <= 2:
        lines.append("—")
    return "\n".join(lines).rstrip()


def format_history_list(
    lang: str,
    rows: list[tuple[Event, object]],
    *,
    total: int = 0,
    page: int = 0,
    page_size: int = 10,
) -> str:
    if not rows and total <= 0:
        return t(lang, "empty_history")
    start = page * page_size + 1
    end = page * page_size + len(rows)
    lines = [
        f"<b>📚 {t(lang, 'history')}</b>",
        f"<i>{start}–{end} {t(lang, 'hist_of')} {total}</i>",
        "",
    ]
    for event, state in rows:
        brief = to_brief(event, lang)
        score = float(brief.importance_score or 0)
        stars = max(1, min(5, round(score / 2))) if score else 1
        star_txt = "⭐" * stars
        lines.append(f"📰 <b>{escape(brief.title)}</b>")
        lines.append(f"   {star_txt} · {score:.1f}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_trends(lang: str, rows: list[dict]) -> str:
    if not rows:
        return f"<b>🔥 {t(lang, 'trends')}</b>\n\n{t(lang, 'trends_empty')}"
    lines = [f"<b>🔥 {t(lang, 'trends')}</b>", ""]
    for row in rows:
        title = normalize_title(row.get("title") or row.get("topic") or "")
        first_seen = row.get("first_seen")
        if isinstance(first_seen, str):
            first_seen = None
        lines.append(f"🔥 <b>{escape(title)}</b>")
        lines.append(
            format_meta_line(
                score=float(row.get("importance_score") or row.get("score") or 0),
                category=str(row.get("category") or "Other"),
                sources=int(row.get("sources") or 0),
                posts=int(row.get("posts_count", row.get("news_count", 0)) or 0),
                first_seen=first_seen if isinstance(first_seen, datetime) else None,
            )
        )
        lines.append("")
    return "\n".join(lines).rstrip()


def _progress_bar(percent: int, width: int = 10) -> str:
    p = max(0, min(100, int(percent)))
    filled = int(round(width * p / 100))
    return "█" * filled + "░" * (width - filled)


def format_backfill_progress(lang: str, job) -> str:
    pct = int(getattr(job, "percent", 0) or 0)
    done = int(getattr(job, "done", 0) or 0)
    total = int(getattr(job, "total", 0) or 0)
    days = int(getattr(job, "days", 0) or 0)
    msgs = int(getattr(job, "messages_fetched", 0) or 0)
    events_n = int(getattr(job, "events_processed", 0) or 0)
    status = str(getattr(job, "status", "") or "")
    status_key = {
        "queued": "bf_status_queued",
        "running": "bf_status_running",
        "analyzing": "bf_status_analyzing",
        "done": "bf_status_done",
        "failed": "bf_status_failed",
    }.get(status, "bf_status_queued")

    if status == "done":
        created = getattr(job, "created_at", None)
        updated = getattr(job, "updated_at", None)
        elapsed = ""
        if created and updated:
            try:
                secs = int((updated - created).total_seconds())
                m, s = divmod(max(0, secs), 60)
                elapsed = f"\n⏱ {t(lang, 'bf_time')}: <b>{m}:{s:02d}</b>"
            except Exception:
                elapsed = ""
        return (
            f"<b>✅ {t(lang, 'bf_done_title')}</b>\n\n"
            f"{t(lang, 'bf_added')}:\n"
            f"📰 {t(lang, 'bf_news_label')}: <b>{msgs}</b>\n"
            f"🔥 Events: <b>{events_n}</b>"
            f"{elapsed}"
        )

    waiting = t(lang, "bf_waiting") if status in {"queued", "running", "analyzing"} else ""
    return (
        f"<b>📰 {t(lang, 'bf_loading_title')}</b>\n\n"
        f"<code>{_progress_bar(pct)}</code> <b>{pct}%</b>\n\n"
        f"📡 {t(lang, 'bf_channels', done=done, total=total)}\n"
        f"📝 {t(lang, 'bf_posts_label')}: <b>{msgs}</b>\n"
        f"🧠 {t(lang, 'bf_analysis_label')}: <b>{events_n}</b>\n"
        f"{t(lang, 'bf_status')}: <b>{t(lang, status_key)}</b>\n"
        f"{waiting}"
    )


def format_settings(lang: str, settings) -> str:
    from app.services.categories import theme_display

    cats = settings.enabled_categories or []
    if cats:
        cats_s = ", ".join(theme_display(c) for c in cats)
    else:
        cats_s = "—"
    mode = settings.digest_mode or "off"
    digest_label = {
        "off": t(lang, "digest_off"),
        "1h": t(lang, "digest_1h"),
        "3h": t(lang, "digest_3h"),
        "6h": t(lang, "digest_6h"),
        "daily": t(lang, "digest_daily"),
    }.get(mode, mode)
    if mode == "daily":
        digest_label = f"{digest_label} ({settings.digest_time})"
    on = t(lang, "on")
    off = t(lang, "off")
    dnd = on if getattr(settings, "dnd_enabled", True) else off
    lines = [
        f"<b>⚙ {t(lang, 'settings')}</b>",
        "",
        f"{t(lang, 'language')} — <b>{settings.language}</b>",
        f"{t(lang, 'news_language')} — <b>{settings.news_language}</b>",
        f"{t(lang, 'feed_page_size')} — <b>{settings.feed_page_size}</b>",
        f"{t(lang, 'set_digests')} — <b>{digest_label}</b>",
        f"{t(lang, 'set_dnd')} — <b>{dnd}</b>",
        f"{t(lang, 'set_tz')} — <b>{escape(settings.timezone or 'Europe/Moscow')}</b>",
        f"{t(lang, 'set_min')} — <b>{settings.min_importance:.1f}+</b>",
        f"{t(lang, 'set_themes')} — <b>{escape(cats_s)}</b>",
        f"{t(lang, 'show_summary')} — <b>{on if settings.show_summary else off}</b>",
    ]
    return "\n".join(lines)


def format_how_to_use(lang: str) -> str:
    return t(lang, "howto_body")


def format_about(lang: str) -> str:
    return f"<b>ℹ️ {t(lang, 'about')}</b>\n\n{t(lang, 'about_body')}"


def format_privacy(lang: str) -> str:
    if lang == "en":
        return (
            "<b>🔒 Privacy policy</b>\n\n"
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
    """Legacy helper — tour keys live in home.onboarding now."""
    return [
        (t(lang, "ob_tour1_t"), t(lang, "ob_tour1_b")),
        (t(lang, "ob_tour2_t"), t(lang, "ob_tour2_b")),
        (t(lang, "ob_tour3_t"), t(lang, "ob_tour3_b")),
        (t(lang, "ob_tour4_t"), t(lang, "ob_tour4_b")),
        (t(lang, "ob_tour5_t"), t(lang, "ob_tour5_b")),
        (t(lang, "ob_tour_done_t"), t(lang, "ob_tour_done_b")),
    ]
