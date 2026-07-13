"""User settings and personalized Event feed / favorites / history."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Channel, Event, EventSource, Message, User, UserChannel, UserEventState, UserSettings
from app.services.ai.base import ALLOWED_CATEGORIES

DEFAULT_CATEGORIES = list(ALLOWED_CATEGORIES)
RESURFACE_SCORE_DELTA = 1.5
RESURFACE_SOURCES_DELTA = 3


class PreferencesService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, user: User) -> UserSettings:
        result = await self._session.execute(
            select(UserSettings).where(UserSettings.user_id == user.id)
        )
        settings = result.scalar_one_or_none()
        if settings:
            return settings
        settings = UserSettings(
            user_id=user.id,
            enabled_categories=DEFAULT_CATEGORIES.copy(),
            language="ru",
        )
        self._session.add(settings)
        await self._session.flush()
        return settings

    async def lang(self, user: User) -> str:
        s = await self.get_or_create(user)
        return s.language or "ru"

    async def mark_welcome_seen(self, user: User) -> None:
        settings = await self.get_or_create(user)
        settings.welcome_seen = True
        await self._session.commit()

    async def set_language(self, user: User, language: str) -> UserSettings:
        settings = await self.get_or_create(user)
        settings.language = language
        settings.language_chosen = True
        await self._session.commit()
        return settings

    async def save_digest_message(self, user: User, chat_id: int, message_id: int) -> None:
        settings = await self.get_or_create(user)
        settings.digest_chat_id = chat_id
        settings.digest_message_id = message_id
        await self._session.commit()

    async def set_interval(self, user: User, minutes: int) -> UserSettings:
        settings = await self.get_or_create(user)
        settings.update_interval_minutes = minutes
        await self._session.commit()
        return settings

    async def set_min_importance(self, user: User, value: float) -> UserSettings:
        settings = await self.get_or_create(user)
        settings.min_importance = max(0.0, min(10.0, value))
        await self._session.commit()
        return settings

    async def toggle_category(self, user: User, category: str) -> UserSettings:
        settings = await self.get_or_create(user)
        cats = list(settings.enabled_categories or DEFAULT_CATEGORIES.copy())
        if category in cats:
            cats.remove(category)
        else:
            cats.append(category)
        settings.enabled_categories = cats
        await self._session.commit()
        return settings

    async def set_ignored_topics(self, user: User, text: str) -> UserSettings:
        settings = await self.get_or_create(user)
        settings.ignored_topics = (text or "").strip()
        await self._session.commit()
        return settings

    async def reset_reactions(self, user: User) -> None:
        await self._session.execute(delete(UserEventState).where(UserEventState.user_id == user.id))
        from app.models import Reaction

        await self._session.execute(delete(Reaction).where(Reaction.user_id == user.id))
        await self._session.commit()


class FeedService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._prefs = PreferencesService(session)

    async def get_feed(
        self,
        user: User,
        *,
        limit: int = 5,
        offset: int = 0,
    ) -> tuple[list[Event], int]:
        settings = await self._prefs.get_or_create(user)
        cats = settings.enabled_categories or DEFAULT_CATEGORIES
        ignored = [t.strip().lower() for t in (settings.ignored_topics or "").split(",") if t.strip()]

        channel_ids = await self._user_channel_ids(user.id)
        if not channel_ids:
            return [], 0

        allowed_ids = await self._event_ids_for_channels(channel_ids)
        # If links are missing (old data), fall back to global active events
        # so the feed is not permanently empty for a user who already added channels.
        use_channel_filter = bool(allowed_ids)

        result = await self._session.execute(
            select(Event)
            .options(selectinload(Event.sources))
            .where(Event.status == "active")
            .where(Event.importance_score >= settings.min_importance)
            .order_by(Event.importance_score.desc(), Event.updated_at.desc())
            .limit(500)
        )
        items = list(result.scalars().all())
        states = await self._load_states(user.id)
        filtered: list[Event] = []
        for event in items:
            if use_channel_filter and event.id not in allowed_ids:
                continue
            if cats and event.category and event.category not in cats:
                continue
            blob = f"{event.title} {event.summary} {event.topic or ''}".lower()
            if any(topic in blob for topic in ignored):
                continue
            if not self._should_show(event, states.get(event.id)):
                continue
            filtered.append(event)
        page = filtered[offset : offset + limit]
        return page, len(filtered)

    async def _user_channel_ids(self, user_id: int) -> list[int]:
        result = await self._session.execute(
            select(UserChannel.channel_id).where(
                UserChannel.user_id == user_id,
                UserChannel.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    async def _event_ids_for_channels(self, channel_ids: list[int]) -> set[int]:
        """Resolve events linked to user channels (by message OR source username/title)."""
        if not channel_ids:
            return set()

        ch_result = await self._session.execute(
            select(Channel).where(Channel.id.in_(channel_ids))
        )
        channels = list(ch_result.scalars().all())
        usernames = {(c.username or "").lower() for c in channels if c.username}
        titles = {(c.title or "").lower() for c in channels if c.title}

        # 1) Via live Message.channel_id (preferred)
        via_msg = await self._session.execute(
            select(EventSource.event_id)
            .join(Message, Message.id == EventSource.message_id)
            .where(Message.channel_id.in_(channel_ids))
            .where(Message.is_advertisement.is_(False))
        )
        ids = set(via_msg.scalars().all())

        # 2) Via source username (works after message cleanup / NULL message_id)
        if usernames:
            via_user = await self._session.execute(
                select(EventSource.event_id).where(
                    EventSource.channel_username.is_not(None),
                    func.lower(EventSource.channel_username).in_(list(usernames)),
                )
            )
            ids |= set(via_user.scalars().all())

        # 3) Via channel title on source (best-effort)
        if titles:
            via_title = await self._session.execute(
                select(EventSource.event_id).where(
                    EventSource.channel_title.is_not(None),
                    func.lower(EventSource.channel_title).in_(list(titles)),
                )
            )
            ids |= set(via_title.scalars().all())

        return ids

    def _should_show(self, event: Event, state: UserEventState | None) -> bool:
        if state is None:
            return True
        if state.is_hidden:
            return False
        if not state.is_read:
            return True
        score_grew = float(event.importance_score) >= float(state.score_at_interaction) + RESURFACE_SCORE_DELTA
        sources_now = event.sources_count or len(event.sources or [])
        sources_grew = sources_now >= int(state.sources_at_interaction) + RESURFACE_SOURCES_DELTA
        return score_grew or sources_grew

    async def _load_states(self, user_id: int) -> dict[int, UserEventState]:
        result = await self._session.execute(
            select(UserEventState).where(UserEventState.user_id == user_id)
        )
        return {s.event_id: s for s in result.scalars().all()}

    async def _get_or_create_state(self, user: User, event: Event) -> UserEventState:
        result = await self._session.execute(
            select(UserEventState).where(
                UserEventState.user_id == user.id,
                UserEventState.event_id == event.id,
            )
        )
        state = result.scalar_one_or_none()
        if state is None:
            state = UserEventState(user_id=user.id, event_id=event.id)
            self._session.add(state)
            await self._session.flush()
        return state

    async def mark_read(self, user: User, event: Event, *, hidden: bool = False) -> None:
        state = await self._get_or_create_state(user, event)
        state.is_read = True
        state.read_at = datetime.now(timezone.utc)
        if hidden:
            state.is_hidden = True
        state.score_at_interaction = event.importance_score
        state.sources_at_interaction = event.sources_count or len(event.sources or [])
        await self._session.commit()

    async def dislike(self, user: User, event: Event) -> None:
        await self.mark_read(user, event, hidden=True)

    async def toggle_favorite(self, user: User, event: Event) -> bool:
        state = await self._get_or_create_state(user, event)
        state.is_favorite = not state.is_favorite
        state.favorited_at = datetime.now(timezone.utc) if state.is_favorite else None
        await self._session.commit()
        return state.is_favorite

    async def list_favorites(self, user: User, *, limit: int = 20) -> list[Event]:
        result = await self._session.execute(
            select(Event)
            .join(UserEventState, UserEventState.event_id == Event.id)
            .options(selectinload(Event.sources))
            .where(UserEventState.user_id == user.id, UserEventState.is_favorite.is_(True))
            .order_by(UserEventState.favorited_at.desc().nulls_last())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_history(
        self,
        user: User,
        *,
        limit: int = 30,
        since: datetime | None = None,
        query: str | None = None,
    ) -> list[Event]:
        stmt = (
            select(Event)
            .join(UserEventState, UserEventState.event_id == Event.id)
            .options(selectinload(Event.sources))
            .where(UserEventState.user_id == user.id, UserEventState.is_read.is_(True))
        )
        if since is not None:
            stmt = stmt.where(UserEventState.read_at >= since)
        stmt = stmt.order_by(UserEventState.read_at.desc().nulls_last()).limit(limit * 3 if query else limit)
        result = await self._session.execute(stmt)
        items = list(result.scalars().all())
        q = (query or "").strip().lower()
        if q:
            items = [
                n
                for n in items
                if q in (n.title or "").lower()
                or q in (n.summary or "").lower()
                or q in (n.topic or "").lower()
            ]
        return items[:limit]
