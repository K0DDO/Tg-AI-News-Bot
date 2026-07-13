"""Ensure localized title/summary cached on Event (lazy, cost-aware)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event
from app.services.ai import create_ai_service
from app.services.ai.usage import log_ai_usage


async def ensure_translation(session: AsyncSession, event: Event, lang: str) -> Event:
    if not lang or lang == "ru":
        return event
    title_map = dict(event.title_i18n or {})
    summary_map = dict(event.summary_i18n or {})
    if lang in title_map and lang in summary_map:
        return event

    ai = create_ai_service()
    result = await ai.translate(title=event.title, summary=event.summary, target_lang=lang)
    await log_ai_usage(session, provider=getattr(ai, "provider_name", "unknown"), operation="translate")
    title_map[lang] = result.title
    summary_map[lang] = result.summary
    event.title_i18n = title_map
    event.summary_i18n = summary_map
    await session.commit()
    await session.refresh(event)
    return event
