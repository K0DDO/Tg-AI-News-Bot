"""Trends built from Events (full event cards), not bag-of-words."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Event, EventSource


class TrendsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def top_events(self, *, limit: int = 10) -> list[dict]:
        """
        Each trend row is one Event:
        title, sources, posts_count, growth_today
        """
        now = datetime.now(timezone.utc)
        day_ago = now - timedelta(hours=24)
        result = await self._session.execute(
            select(Event)
            .options(selectinload(Event.sources))
            .where(Event.status == "active")
            .where(Event.importance_score >= 3.0)
            .order_by(Event.sources_count.desc(), Event.updated_at.desc())
            .limit(80)
        )
        rows: list[dict] = []
        for event in result.scalars().all():
            sources = event.sources_count or len(event.sources or [])
            posts = event.posts_count or sources
            if sources < 1:
                continue
            growth = 0
            for src in event.sources or []:
                if src.created_at and src.created_at >= day_ago:
                    growth += 1
            if event.updated_at and event.updated_at >= day_ago and growth == 0:
                growth = max(1, sources // 3)
            title = (event.topic or event.title or "").strip()
            if len(title) < 8:
                continue
            rows.append(
                {
                    "event_id": event.id,
                    "topic": title,  # UI key kept for format_trends
                    "title": title,
                    "sources": sources,
                    "news_count": posts,
                    "posts_count": posts,
                    "growth_today": growth,
                    "importance": float(event.importance_score),
                }
            )
        rows.sort(
            key=lambda r: (r["sources"], r["growth_today"], r["importance"]),
            reverse=True,
        )
        return rows[:limit]

    # compat name used by bot
    async def top_topics(self, *, limit: int = 10) -> list[dict]:
        return await self.top_events(limit=limit)
