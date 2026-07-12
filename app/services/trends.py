"""Topic-based trends (not bag-of-words)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import News


class TrendsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def top_topics(self, *, limit: int = 10) -> list[dict]:
        """
        Returns list of dicts:
        topic, sources, news_count, growth_today
        """
        now = datetime.now(timezone.utc)
        day_ago = now - timedelta(hours=24)
        result = await self._session.execute(
            select(News)
            .options(selectinload(News.sources))
            .where(News.topic.is_not(None))
            .order_by(News.updated_at.desc())
            .limit(500)
        )
        by_topic: dict[str, list[News]] = defaultdict(list)
        for news in result.scalars().all():
            topic = (news.topic or "").strip()
            if len(topic) < 2:
                continue
            # normalize key case-insensitively but keep display form
            key = topic
            by_topic[key].append(news)

        # merge case variants
        merged: dict[str, list[News]] = {}
        for topic, items in by_topic.items():
            found = None
            for existing in merged:
                if existing.lower() == topic.lower():
                    found = existing
                    break
            if found:
                merged[found].extend(items)
            else:
                merged[topic] = list(items)

        rows: list[dict] = []
        for topic, items in merged.items():
            source_ids: set[int] = set()
            growth = 0
            for n in items:
                for s in n.sources or []:
                    source_ids.add(s.id)
                if not n.sources:
                    source_ids.add(n.id)
                if n.updated_at and n.updated_at >= day_ago:
                    growth += max(1, n.sources_count or len(n.sources or []))
            rows.append(
                {
                    "topic": topic,
                    "sources": len(source_ids),
                    "news_count": len(items),
                    "growth_today": growth,
                }
            )
        rows.sort(key=lambda r: (r["sources"], r["growth_today"], r["news_count"]), reverse=True)
        return rows[:limit]
