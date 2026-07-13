"""Recommendation stub — wraps personalized feed for future ranking models."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, User
from app.services.preferences import FeedService


class RecommendationService:
    def __init__(self, session: AsyncSession) -> None:
        self._feed = FeedService(session)

    async def recommend(self, user: User, *, limit: int = 5) -> list[Event]:
        items, _ = await self._feed.get_feed(user, limit=limit, offset=0)
        return items
