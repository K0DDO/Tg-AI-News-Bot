"""User settings and personalized feed / favorites / history."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Message, News, NewsSource, User, UserChannel, UserNewsState, UserSettings
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
        await self._session.execute(delete(UserNewsState).where(UserNewsState.user_id == user.id))
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
    ) -> tuple[list[News], int]:
        """Return (page, total_matching). Personal feed from user's channels when set."""
        settings = await self._prefs.get_or_create(user)
        cats = settings.enabled_categories or DEFAULT_CATEGORIES
        ignored = [t.strip().lower() for t in (settings.ignored_topics or "").split(",") if t.strip()]

        channel_ids = await self._user_channel_ids(user.id)
        if not channel_ids:
            return [], 0

        allowed_news_ids = await self._news_ids_for_channels(channel_ids)
        result = await self._session.execute(
            select(News)
            .options(selectinload(News.sources))
            .where(News.importance_score >= settings.min_importance)
            .order_by(News.importance_score.desc(), News.updated_at.desc())
            .limit(500)
        )
        items = list(result.scalars().all())

        states = await self._load_states(user.id)
        filtered: list[News] = []
        for news in items:
            if news.id not in allowed_news_ids:
                continue
            if cats and news.category and news.category not in cats:
                continue
            blob = f"{news.title} {news.summary} {news.topic or ''}".lower()
            if any(topic in blob for topic in ignored):
                continue
            if not self._should_show(news, states.get(news.id)):
                continue
            filtered.append(news)
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

    async def _news_ids_for_channels(self, channel_ids: list[int]) -> set[int]:
        result = await self._session.execute(
            select(NewsSource.news_id)
            .join(Message, Message.id == NewsSource.message_id)
            .where(Message.channel_id.in_(channel_ids))
        )
        return set(result.scalars().all())

    def _should_show(self, news: News, state: UserNewsState | None) -> bool:
        if state is None:
            return True
        if state.is_hidden:
            return False
        if not state.is_read:
            return True
        # resurface only if score OR sources grew significantly
        score_grew = float(news.importance_score) >= float(state.score_at_interaction) + RESURFACE_SCORE_DELTA
        sources_now = news.sources_count or len(news.sources or [])
        sources_grew = sources_now >= int(state.sources_at_interaction) + RESURFACE_SOURCES_DELTA
        return score_grew or sources_grew

    async def _load_states(self, user_id: int) -> dict[int, UserNewsState]:
        result = await self._session.execute(
            select(UserNewsState).where(UserNewsState.user_id == user_id)
        )
        return {s.news_id: s for s in result.scalars().all()}

    async def _get_or_create_state(self, user: User, news: News) -> UserNewsState:
        result = await self._session.execute(
            select(UserNewsState).where(
                UserNewsState.user_id == user.id,
                UserNewsState.news_id == news.id,
            )
        )
        state = result.scalar_one_or_none()
        if state is None:
            state = UserNewsState(user_id=user.id, news_id=news.id)
            self._session.add(state)
            await self._session.flush()
        return state

    async def mark_read(self, user: User, news: News, *, hidden: bool = False) -> None:
        state = await self._get_or_create_state(user, news)
        state.is_read = True
        state.read_at = datetime.now(timezone.utc)
        if hidden:
            state.is_hidden = True
        state.score_at_interaction = news.importance_score
        state.sources_at_interaction = news.sources_count or len(news.sources or [])
        await self._session.commit()

    async def dislike(self, user: User, news: News) -> None:
        # personal hide only — do not mutate global score for everyone
        await self.mark_read(user, news, hidden=True)

    async def toggle_favorite(self, user: User, news: News) -> bool:
        state = await self._get_or_create_state(user, news)
        state.is_favorite = not state.is_favorite
        state.favorited_at = datetime.now(timezone.utc) if state.is_favorite else None
        await self._session.commit()
        return state.is_favorite

    async def list_favorites(self, user: User, *, limit: int = 20) -> list[News]:
        result = await self._session.execute(
            select(News)
            .join(UserNewsState, UserNewsState.news_id == News.id)
            .options(selectinload(News.sources))
            .where(UserNewsState.user_id == user.id, UserNewsState.is_favorite.is_(True))
            .order_by(UserNewsState.favorited_at.desc().nulls_last())
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
    ) -> list[News]:
        stmt = (
            select(News)
            .join(UserNewsState, UserNewsState.news_id == News.id)
            .options(selectinload(News.sources))
            .where(UserNewsState.user_id == user.id, UserNewsState.is_read.is_(True))
        )
        if since is not None:
            stmt = stmt.where(UserNewsState.read_at >= since)
        stmt = stmt.order_by(UserNewsState.read_at.desc().nulls_last()).limit(limit * 3 if query else limit)
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
