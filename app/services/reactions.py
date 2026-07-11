"""User reactions for personalization foundation."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Reaction, ReactionType


class ReactionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def set_reaction(self, user_id: int, news_id: int, reaction_type: str) -> Reaction:
        result = await self._session.execute(
            select(Reaction).where(
                Reaction.user_id == user_id,
                Reaction.news_id == news_id,
            )
        )
        reaction = result.scalar_one_or_none()
        if reaction:
            reaction.reaction_type = reaction_type
        else:
            reaction = Reaction(
                user_id=user_id,
                news_id=news_id,
                reaction_type=reaction_type,
            )
            self._session.add(reaction)
        await self._session.commit()
        await self._session.refresh(reaction)
        return reaction

    async def mark_interesting(self, user_id: int, news_id: int) -> Reaction:
        return await self.set_reaction(user_id, news_id, ReactionType.INTERESTING.value)

    async def mark_not_interesting(self, user_id: int, news_id: int) -> Reaction:
        return await self.set_reaction(user_id, news_id, ReactionType.NOT_INTERESTING.value)
