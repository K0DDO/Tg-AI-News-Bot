"""Keyword search over News (implements SearchPort; swap for semantic later)."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import News
from app.services.ports import SearchHit


class KeywordSearch:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(self, query: str, *, limit: int = 10) -> list[SearchHit]:
        q = (query or "").strip()
        if not q:
            return []
        pattern = f"%{q}%"
        result = await self._session.execute(
            select(News)
            .where(
                or_(
                    News.title.ilike(pattern),
                    News.summary.ilike(pattern),
                    News.category.ilike(pattern),
                )
            )
            .order_by(News.importance_score.desc(), News.created_at.desc())
            .limit(limit)
        )
        hits: list[SearchHit] = []
        for news in result.scalars().all():
            hits.append(
                SearchHit(
                    news_id=news.id,
                    score=float(news.importance_score),
                    title=news.title,
                    summary=news.summary,
                )
            )
        return hits
