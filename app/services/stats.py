"""Aggregate counts for admin dashboard."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AiUsageLog, Channel, Event, EventSource, Message, MessageStatus, User


class StatsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def snapshot(self) -> dict[str, int]:
        channels = await self._count(Channel)
        messages = await self._count(Message)
        news = await self._count(Event)
        users = await self._count(User)
        sources = await self._count(EventSource)
        filtered = await self._session.scalar(
            select(func.count()).select_from(Message).where(
                Message.status == MessageStatus.FILTERED_OUT.value
            )
        )
        processed = await self._session.scalar(
            select(func.count()).select_from(Message).where(
                Message.status == MessageStatus.PROCESSED.value
            )
        )
        ai_requests = await self._count(AiUsageLog)
        ai_analyze = await self._session.scalar(
            select(func.count())
            .select_from(AiUsageLog)
            .where(
                or_(
                    AiUsageLog.operation == "analyze_message",
                    AiUsageLog.operation == "analyze_post",
                )
            )
        )
        ai_search = await self._session.scalar(
            select(func.count())
            .select_from(AiUsageLog)
            .where(
                or_(
                    AiUsageLog.operation == "answer_search",
                    AiUsageLog.operation == "answer_question",
                )
            )
        )
        return {
            "channels": channels,
            "messages": messages,
            "processed_messages": int(processed or 0),
            "news": news,
            "sources": sources,
            "users": users,
            "filtered_messages": int(filtered or 0),
            "ai_requests": ai_requests,
            "ai_analyze": int(ai_analyze or 0),
            "ai_search": int(ai_search or 0),
        }

    async def _count(self, model) -> int:
        result = await self._session.scalar(select(func.count()).select_from(model))
        return int(result or 0)
