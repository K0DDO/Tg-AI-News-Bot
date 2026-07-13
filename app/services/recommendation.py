"""Graph-aware recommendations from user's reading patterns."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, EventNode, Node, User, UserEventState
from app.services.knowledge import KnowledgeGraphService
from app.services.preferences import FeedService


class RecommendationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._feed = FeedService(session)
        self._kg = KnowledgeGraphService(session)

    async def recommend(self, user: User, *, limit: int = 5) -> list[Event]:
        """Prefer KG expansion from liked/read nodes; fall back to personal feed."""
        liked_nodes = await self._user_affinity_nodes(user.id, limit=12)
        if liked_nodes:
            expanded = await self._kg.expand_nodes([n.id for n in liked_nodes], max_extra=16)
            node_ids = [n.id for n, _ in expanded]
            event_ids = await self._kg.event_ids_for_nodes(node_ids, limit=200)
            allowed = await self._feed.event_ids_for_user(user)
            event_ids &= allowed
            # Exclude already shown/disliked
            states = await self._session.execute(
                select(UserEventState).where(
                    UserEventState.user_id == user.id,
                    UserEventState.event_id.in_(list(event_ids)[:200]),
                )
            )
            skip = {
                st.event_id
                for st in states.scalars().all()
                if st.is_shown or st.is_disliked or st.is_hidden
            }
            candidates = [eid for eid in event_ids if eid not in skip]
            if candidates:
                result = await self._session.execute(
                    select(Event)
                    .where(Event.id.in_(candidates[:80]))
                    .where(Event.status == "active")
                    .order_by(Event.importance_score.desc(), Event.updated_at.desc())
                    .limit(limit)
                )
                items = list(result.scalars().all())
                if items:
                    return items

        items, _ = await self._feed.get_feed(user, limit=limit, offset=0)
        return items

    async def _user_affinity_nodes(self, user_id: int, *, limit: int = 12) -> list[Node]:
        result = await self._session.execute(
            select(UserEventState.event_id)
            .where(UserEventState.user_id == user_id)
            .where(
                (UserEventState.is_liked.is_(True))
                | (UserEventState.is_favorite.is_(True))
                | (UserEventState.is_read.is_(True))
            )
            .order_by(UserEventState.updated_at.desc())
            .limit(40)
        )
        event_ids = list(result.scalars().all())
        if not event_ids:
            return []
        result = await self._session.execute(
            select(Node)
            .join(EventNode, EventNode.node_id == Node.id)
            .where(EventNode.event_id.in_(event_ids))
            .order_by(Node.mention_count.desc())
            .limit(limit)
        )
        return list(result.scalars().unique().all())
