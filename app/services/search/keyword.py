"""Keyword fallback over Events (not posts)."""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event
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
            select(Event)
            .where(Event.status == "active")
            .where(
                or_(
                    Event.title.ilike(pattern),
                    Event.summary.ilike(pattern),
                    Event.category.ilike(pattern),
                    Event.topic.ilike(pattern),
                )
            )
            .order_by(Event.importance_score.desc(), Event.created_at.desc())
            .limit(limit)
        )
        return [
            SearchHit(
                news_id=event.id,
                score=float(event.importance_score),
                title=event.title,
                summary=event.summary,
            )
            for event in result.scalars().all()
        ]
