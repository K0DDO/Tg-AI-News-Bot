"""User settings and personalized Event feed / favorites / history."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer, selectinload

from app.models import Channel, Event, EventSource, Message, User, UserChannel, UserEventState, UserSettings
from app.services.categories import DEFAULT_CATEGORIES

LIKE_SCORE_DELTA = Decimal("1.5")
DISLIKE_SCORE_DELTA = Decimal("-2.0")


class PreferencesService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, user: User) -> UserSettings:
        result = await self._session.execute(
            select(UserSettings).where(UserSettings.user_id == user.id)
        )
        settings = result.scalar_one_or_none()
        if settings:
            self._ensure_categories(settings)
            return settings
        settings = UserSettings(
            user_id=user.id,
            enabled_categories=DEFAULT_CATEGORIES.copy(),
            language="ru",
            news_language="ru",
        )
        self._session.add(settings)
        await self._session.flush()
        return settings

    @staticmethod
    def _ensure_categories(settings: UserSettings) -> None:
        """Auto-enable newly added taxonomy categories for existing users."""
        current = list(settings.enabled_categories or [])
        if not current:
            settings.enabled_categories = DEFAULT_CATEGORIES.copy()
            return
        changed = False
        for cat in DEFAULT_CATEGORIES:
            if cat not in current:
                current.append(cat)
                changed = True
        cleaned = [c for c in current if c in DEFAULT_CATEGORIES]
        if cleaned != current:
            current = cleaned
            changed = True
        if changed:
            settings.enabled_categories = current

    async def lang(self, user: User) -> str:
        s = await self.get_or_create(user)
        return s.language or "ru"

    async def news_lang(self, user: User) -> str:
        s = await self.get_or_create(user)
        return s.news_language or s.language or "ru"

    async def mark_welcome_seen(self, user: User) -> None:
        settings = await self.get_or_create(user)
        settings.welcome_seen = True
        await self._session.commit()

    async def mark_tutorial_seen(self, user: User) -> None:
        settings = await self.get_or_create(user)
        settings.tutorial_seen = True
        await self._session.commit()

    async def set_language(self, user: User, language: str) -> UserSettings:
        settings = await self.get_or_create(user)
        settings.language = language
        settings.language_chosen = True
        await self._session.commit()
        return settings

    async def set_news_language(self, user: User, language: str) -> UserSettings:
        settings = await self.get_or_create(user)
        settings.news_language = language
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

    async def set_feed_page_size(self, user: User, size: int) -> UserSettings:
        settings = await self.get_or_create(user)
        settings.feed_page_size = max(1, min(15, size))
        await self._session.commit()
        return settings

    async def toggle_bool(self, user: User, field: str) -> UserSettings:
        settings = await self.get_or_create(user)
        if not hasattr(settings, field):
            return settings
        setattr(settings, field, not bool(getattr(settings, field)))
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

    async def user_stats(self, user: User) -> dict[str, int]:
        read_n = await self._session.scalar(
            select(func.count())
            .select_from(UserEventState)
            .where(UserEventState.user_id == user.id, UserEventState.is_read.is_(True))
        )
        fav_n = await self._session.scalar(
            select(func.count())
            .select_from(UserEventState)
            .where(UserEventState.user_id == user.id, UserEventState.is_favorite.is_(True))
        )
        liked_n = await self._session.scalar(
            select(func.count())
            .select_from(UserEventState)
            .where(UserEventState.user_id == user.id, UserEventState.is_liked.is_(True))
        )
        return {
            "read": int(read_n or 0),
            "saved": int(fav_n or 0),
            "liked": int(liked_n or 0),
        }


class FeedService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._prefs = PreferencesService(session)

    async def get_feed(
        self,
        user: User,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[list[Event], int]:
        """Fast personal feed: SQL filters + small page, no heavy Python scan."""
        settings = await self._prefs.get_or_create(user)
        page_size = limit if limit is not None else int(settings.feed_page_size or 5)
        cats = list(settings.enabled_categories or DEFAULT_CATEGORIES)
        ignored = [t.strip().lower() for t in (settings.ignored_topics or "").split(",") if t.strip()]

        channel_ids = await self._user_channel_ids(user.id)
        if not channel_ids:
            return [], 0

        via_msg = (
            select(EventSource.event_id)
            .join(Message, Message.id == EventSource.message_id)
            .where(Message.channel_id.in_(channel_ids))
            .where(Message.is_advertisement.is_(False))
        )
        via_user = (
            select(EventSource.event_id)
            .join(
                Channel,
                func.lower(Channel.username) == func.lower(EventSource.channel_username),
            )
            .where(EventSource.message_id.is_(None))
            .where(Channel.id.in_(channel_ids))
            .where(Channel.username.is_not(None))
        )
        allowed = via_msg.union(via_user)

        blocked = (
            select(UserEventState.event_id)
            .where(UserEventState.user_id == user.id)
            .where(
                or_(
                    UserEventState.is_read.is_(True),
                    UserEventState.is_hidden.is_(True),
                    UserEventState.is_disliked.is_(True),
                )
            )
        )
        personal = func.coalesce(UserEventState.personal_score, 0)

        stmt = (
            select(Event)
            .outerjoin(
                UserEventState,
                and_(
                    UserEventState.event_id == Event.id,
                    UserEventState.user_id == user.id,
                ),
            )
            .options(defer(Event.embedding))
            .where(Event.status == "active")
            .where(Event.importance_score >= settings.min_importance)
            .where(Event.id.in_(allowed))
            .where(Event.id.not_in(blocked))
        )
        if cats:
            stmt = stmt.where(or_(Event.category.is_(None), Event.category.in_(cats)))
        for topic in ignored:
            pat = f"%{topic}%"
            stmt = stmt.where(
                ~func.lower(func.coalesce(Event.title, "")).like(pat),
                ~func.lower(func.coalesce(Event.summary, "")).like(pat),
                ~func.lower(func.coalesce(Event.topic, "")).like(pat),
            )

        stmt = (
            stmt.order_by(
                (personal + Event.importance_score).desc(),
                Event.importance_score.desc(),
                Event.updated_at.desc(),
            )
            .offset(max(0, offset))
            .limit(page_size + 1)
        )
        rows = list((await self._session.execute(stmt)).scalars().unique().all())
        has_more = len(rows) > page_size
        page = rows[:page_size]
        # Approximate total for pager: enough to compute has_more correctly.
        total = offset + len(page) + (1 if has_more else 0)
        return page, total

    async def event_ids_for_user(self, user: User) -> set[int]:
        channel_ids = await self._user_channel_ids(user.id)
        return await self._event_ids_for_channels(channel_ids)

    async def _user_channel_ids(self, user_id: int) -> list[int]:
        result = await self._session.execute(
            select(UserChannel.channel_id).where(
                UserChannel.user_id == user_id,
                UserChannel.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    async def _event_ids_for_channels(self, channel_ids: list[int]) -> set[int]:
        """Events that have at least one source message from the given channels."""
        if not channel_ids:
            return set()

        via_msg = await self._session.execute(
            select(EventSource.event_id)
            .join(Message, Message.id == EventSource.message_id)
            .where(Message.channel_id.in_(channel_ids))
            .where(Message.is_advertisement.is_(False))
        )
        ids = set(via_msg.scalars().all())

        # Fallback for sources without message_id: exact username match only
        ch_result = await self._session.execute(
            select(Channel).where(Channel.id.in_(channel_ids))
        )
        usernames = {(c.username or "").lower() for c in ch_result.scalars().all() if c.username}
        if usernames:
            via_user = await self._session.execute(
                select(EventSource.event_id).where(
                    EventSource.message_id.is_(None),
                    EventSource.channel_username.is_not(None),
                    func.lower(EventSource.channel_username).in_(list(usernames)),
                )
            )
            ids |= set(via_user.scalars().all())

        return ids

    @staticmethod
    def _should_show(state: UserEventState | None) -> bool:
        if state is None:
            return True
        if state.is_hidden or state.is_disliked:
            return False
        return not state.is_read

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

    async def mark_shown(self, user: User, event: Event) -> None:
        state = await self._get_or_create_state(user, event)
        state.is_shown = True
        state.shown_count = int(state.shown_count or 0) + 1
        await self._session.commit()

    async def mark_read(self, user: User, event: Event, *, hidden: bool = False) -> None:
        state = await self._get_or_create_state(user, event)
        now = datetime.now(timezone.utc)
        state.is_read = True
        state.is_shown = True
        state.read_at = now
        state.opened_at = state.opened_at or now
        state.shown_count = max(int(state.shown_count or 0), 1)
        if hidden:
            state.is_hidden = True
            state.is_disliked = True
            state.is_liked = False
            state.personal_score = Decimal(state.personal_score or 0) + DISLIKE_SCORE_DELTA
        state.score_at_interaction = event.importance_score
        state.sources_at_interaction = event.sources_count or len(event.sources or [])
        await self._session.commit()

    async def mark_liked(self, user: User, event: Event) -> None:
        state = await self._get_or_create_state(user, event)
        if not state.is_liked:
            state.personal_score = Decimal(state.personal_score or 0) + LIKE_SCORE_DELTA
        state.is_liked = True
        state.is_disliked = False
        state.is_hidden = False
        state.is_read = True
        state.read_at = state.read_at or datetime.now(timezone.utc)
        state.opened_at = state.opened_at or datetime.now(timezone.utc)
        await self._session.commit()

    async def dislike(self, user: User, event: Event) -> None:
        await self.mark_read(user, event, hidden=True)

    async def toggle_favorite(self, user: User, event: Event) -> bool:
        state = await self._get_or_create_state(user, event)
        state.is_favorite = not state.is_favorite
        state.favorited_at = datetime.now(timezone.utc) if state.is_favorite else None
        await self._session.commit()
        return state.is_favorite

    async def remove_from_history(self, user: User, event: Event) -> None:
        state = await self._get_or_create_state(user, event)
        state.is_read = False
        state.read_at = None
        state.opened_at = None
        await self._session.commit()

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
    ) -> list[tuple[Event, UserEventState]]:
        stmt = (
            select(Event, UserEventState)
            .join(UserEventState, UserEventState.event_id == Event.id)
            .options(selectinload(Event.sources))
            .where(UserEventState.user_id == user.id, UserEventState.is_read.is_(True))
        )
        if since is not None:
            stmt = stmt.where(UserEventState.read_at >= since)
        stmt = stmt.order_by(UserEventState.read_at.desc().nulls_last()).limit(limit * 3 if query else limit)
        result = await self._session.execute(stmt)
        rows = list(result.all())
        q = (query or "").strip().lower()
        if q:
            rows = [
                (n, st)
                for n, st in rows
                if q in (n.title or "").lower()
                or q in (n.summary or "").lower()
                or q in (n.topic or "").lower()
            ]
        return rows[:limit]
