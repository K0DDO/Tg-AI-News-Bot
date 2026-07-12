"""Ensure localized title/summary cached on News (lazy, cost-aware)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import News
from app.services.ai import create_ai_service
from app.services.ai.usage import log_ai_usage


async def ensure_translation(session: AsyncSession, news: News, lang: str) -> News:
    if not lang or lang == "ru":
        # default storage language assumed Russian/original — no force translate
        return news
    title_map = dict(news.title_i18n or {})
    summary_map = dict(news.summary_i18n or {})
    if lang in title_map and lang in summary_map:
        return news

    ai = create_ai_service()
    result = await ai.translate_news(title=news.title, summary=news.summary, target_lang=lang)
    await log_ai_usage(session, provider=getattr(ai, "provider_name", "unknown"), operation="translate")
    title_map[lang] = result.title
    summary_map[lang] = result.summary
    news.title_i18n = title_map
    news.summary_i18n = summary_map
    await session.commit()
    await session.refresh(news)
    return news
