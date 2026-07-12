"""User settings and personalized feed state."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import News, User, UserNewsState, UserSettings
from app.services.ai.base import ALLOWED_CATEGORIES


DEFAULT_CATEGORIES = list(ALLOWED_CATEGORIES)
RESURFACE_SCORE_DELTA = 2.0


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
        )
        self._session.add(settings)
        await self._session.flush()
        return settings

    async def mark_welcome_seen(self, user: User) -> None:
        settings = await self.get_or_create(user)
        settings.welcome_seen = True
        await self._session.commit()

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
        await self._session.execute(
            delete(UserNewsState).where(UserNewsState.user_id == user.id)
        )
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
    ) -> list[News]:
        settings = await self._prefs.get_or_create(user)
        cats = settings.enabled_categories or DEFAULT_CATEGORIES
        ignored = [t.strip().lower() for t in (settings.ignored_topics or "").split(",") if t.strip()]

        result = await self._session.execute(
            select(News)
            .options(selectinload(News.sources))
            .where(News.importance_score >= settings.min_importance)
            .order_by(News.importance_score.desc(), News.updated_at.desc())
            .limit(200)
        )
        items = list(result.scalars().all())
        states = await self._load_states(user.id)
        filtered: list[News] = []
        for news in items:
            if cats and news.category and news.category not in cats:
                continue
            blob = f"{news.title} {news.summary}".lower()
            if any(topic in blob for topic in ignored):
                continue
            state = states.get(news.id)
            if state and state.is_hidden:
                continue
            if state and state.is_read:
                # resurface if score grew a lot since interaction
                if float(news.importance_score) < float(state.score_at_interaction) + RESURFACE_SCORE_DELTA:
                    continue
            filtered.append(news)
        return filtered[offset : offset + limit]

    async def _load_states(self, user_id: int) -> dict[int, UserNewsState]:
        result = await self._session.execute(
            select(UserNewsState).where(UserNewsState.user_id == user_id)
        )
        return {s.news_id: s for s in result.scalars().all()}

    async def mark_read(self, user: User, news: News, *, hidden: bool = False) -> None:
        result = await self._session.execute(
            select(UserNewsState).where(
                UserNewsState.user_id == user.id,
                UserNewsState.news_id == news.id,
            )
        )
        state = result.scalar_one_or_none()
        if state is None:
            state = UserNewsState(
                user_id=user.id,
                news_id=news.id,
                score_at_interaction=news.importance_score,
            )
            self._session.add(state)
        state.is_read = True
        if hidden:
            state.is_hidden = True
        state.score_at_interaction = news.importance_score
        await self._session.commit()

    async def dislike(self, user: User, news: News) -> None:
        # mild global score penalty + hide for user
        news.importance_score = Decimal(str(max(0.0, float(news.importance_score) - 0.4)))
        await self.mark_read(user, news, hidden=True)
