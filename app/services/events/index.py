"""Event Index — search/trends candidates over Events only (not Telegram posts)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Event, EventSource, Message
from app.services.clustering import cosine_similarity
from app.services.ports import EmbeddingPort


class EventIndexService:
    def __init__(self, session: AsyncSession, embedding: EmbeddingPort) -> None:
        self._session = session
        self._embedding = embedding

    async def load_active(
        self,
        *,
        since: datetime | None = None,
        limit: int = 500,
        min_importance: float = 0.0,
        channel_ids: list[int] | None = None,
    ) -> list[Event]:
        stmt = (
            select(Event)
            .options(selectinload(Event.sources).selectinload(EventSource.message))
            .where(Event.status == "active")
            .where(Event.importance_score >= min_importance)
            .order_by(Event.updated_at.desc())
            .limit(limit)
        )
        if since is not None:
            stmt = stmt.where(Event.updated_at >= since)
        result = await self._session.execute(stmt)
        events = list(result.scalars().unique().all())
        if channel_ids:
            allowed = await self._event_ids_for_channels(channel_ids)
            # If linkage is empty, keep global candidates (caller may also fall back)
            if allowed:
                events = [e for e in events if e.id in allowed]
        # Exclude events that only have ad-linked posts when all sources flagged
        return [e for e in events if not self._is_ad_only(e)]

    async def _event_ids_for_channels(self, channel_ids: list[int]) -> set[int]:
        from app.services.preferences import FeedService

        return await FeedService(self._session)._event_ids_for_channels(channel_ids)
    def _is_ad_only(self, event: Event) -> bool:
        from sqlalchemy import inspect as sa_inspect

        msgs = []
        for s in event.sources or []:
            # Skip unloaded relationships — avoid MissingGreenlet in async
            if "message" in sa_inspect(s).unloaded:
                continue
            if s.message is not None:
                msgs.append(s.message)
        if not msgs:
            return False
        return all(bool(m.is_advertisement) for m in msgs)

    def semantic_rank(
        self,
        query: str,
        events: list[Event],
        *,
        limit: int = 15,
        min_sim: float = 0.22,
    ) -> list[tuple[Event, float]]:
        q_vec = self._embedding.embed_one(query)
        scored: list[tuple[Event, float]] = []
        for event in events:
            vec = event.embedding
            if not vec:
                continue
            sim = cosine_similarity(q_vec, vec)
            if sim >= min_sim:
                scored.append((event, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]
