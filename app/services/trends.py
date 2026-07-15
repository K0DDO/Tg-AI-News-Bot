"""Trends = Events, clustered via shared Knowledge Graph nodes + lexical near-dupes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Event
from app.services.events.merge import is_near_duplicate
from app.services.knowledge import KnowledgeGraphService
from app.services.preferences import FeedService
from app.utils.text_clean import strip_at_mentions


class TrendsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._kg = KnowledgeGraphService(session)

    async def top_events(
        self,
        *,
        limit: int = 10,
        channel_ids: list[int] | None = None,
        event_ids: set[int] | None = None,
        since: datetime | None = None,
    ) -> list[dict]:
        now = datetime.now(timezone.utc)
        day_ago = now - timedelta(hours=24)
        since_cut = since or day_ago

        allowed = event_ids
        if allowed is None and channel_ids is not None:
            if not channel_ids:
                return []
            allowed = await FeedService(self._session)._event_ids_for_channels(channel_ids)
            if not allowed:
                return []

        result = await self._session.execute(
            select(Event)
            .options(selectinload(Event.sources))
            .where(Event.status == "active")
            .where(Event.importance_score >= 3.0)
            .where(Event.created_at >= since_cut)
            .order_by(Event.sources_count.desc(), Event.updated_at.desc())
            .limit(200)
        )
        candidates: list[Event] = []
        for event in result.scalars().all():
            if allowed is not None and event.id not in allowed:
                continue
            sources = event.sources_count or len(event.sources or [])
            if sources < 1:
                continue
            title = strip_at_mentions((event.topic or event.title or "").strip())
            if len(title) < 8:
                continue
            candidates.append(event)

        used_clusters: set[frozenset[int]] = set()
        kept: list[Event] = []
        rows: list[dict] = []
        for event in candidates:
            nodes = await self._kg.nodes_for_event(event.id)
            node_ids = frozenset(n.id for n in nodes[:5])
            if node_ids:
                if node_ids in used_clusters:
                    continue
                skip = False
                for existing in used_clusters:
                    if len(node_ids & existing) >= 2:
                        skip = True
                        break
                if skip:
                    continue

            # Lexical near-dupe vs already kept trends (Rostic's promo variants)
            blob = f"{event.title} {event.summary}"
            if any(is_near_duplicate(blob, f"{k.title} {k.summary}") for k in kept):
                continue

            if node_ids:
                used_clusters.add(node_ids)
            kept.append(event)

            sources = event.sources_count or len(event.sources or [])
            posts = event.posts_count or sources
            growth = 0
            first_seen = event.created_at
            for src in event.sources or []:
                if src.created_at and src.created_at >= day_ago:
                    growth += 1
                if src.created_at and (first_seen is None or src.created_at < first_seen):
                    first_seen = src.created_at
            if first_seen is None:
                first_seen = event.updated_at or now
            title = strip_at_mentions((event.topic or event.title or "").strip())
            kg_labels = [n.name for n in nodes[:4]]
            rows.append(
                {
                    "event_id": event.id,
                    "topic": title,
                    "title": title,
                    "category": event.category or "Other",
                    "sources": sources,
                    "news_count": posts,
                    "posts_count": posts,
                    "growth_today": growth,
                    "importance": float(event.importance_score),
                    "importance_score": float(event.importance_score),
                    "kg_nodes": kg_labels,
                    "first_seen": first_seen,
                }
            )
            if len(rows) >= limit:
                break

        rows.sort(
            key=lambda r: (r["sources"], r["growth_today"], r["importance"]),
            reverse=True,
        )
        return rows[:limit]

    async def top_topics(
        self,
        *,
        limit: int = 10,
        channel_ids: list[int] | None = None,
        event_ids: set[int] | None = None,
        since: datetime | None = None,
    ) -> list[dict]:
        return await self.top_events(
            limit=limit, channel_ids=channel_ids, event_ids=event_ids, since=since
        )
