"""Retention: delete old processed/filtered messages; protect favorited events."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Event, EventSource, Message, MessageStatus, UserEventState


class CleanupService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def cleanup_old_messages(self, *, retention_days: int) -> int:
        settings = get_settings()
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=max(1, retention_days))
        fav_cutoff = now - timedelta(days=int(settings.favorite_retention_days or 365 * 5))

        fav_ids = set(
            (
                await self._session.execute(
                    select(UserEventState.event_id).where(
                        UserEventState.is_favorite.is_(True),
                        or_(
                            UserEventState.favorited_at.is_(None),
                            UserEventState.favorited_at >= fav_cutoff,
                        ),
                    )
                )
            ).scalars().all()
        )

        # Soft-archive old non-favorite events
        old_events = (
            await self._session.execute(
                select(Event).where(Event.status == "active", Event.updated_at < cutoff)
            )
        ).scalars().all()
        for ev in old_events:
            if ev.id not in fav_ids:
                ev.status = "archived"

        await self._session.execute(
            update(EventSource)
            .where(
                EventSource.message_id.in_(
                    select(Message.id).where(
                        Message.created_at < cutoff,
                        Message.status.in_(
                            [
                                MessageStatus.PROCESSED.value,
                                MessageStatus.FILTERED_OUT.value,
                            ]
                        ),
                    )
                )
            )
            .values(message_id=None)
        )
        result = await self._session.execute(
            delete(Message).where(
                Message.created_at < cutoff,
                Message.status.in_(
                    [
                        MessageStatus.PROCESSED.value,
                        MessageStatus.FILTERED_OUT.value,
                    ]
                ),
            )
        )
        await self._session.commit()
        return int(result.rowcount or 0)
