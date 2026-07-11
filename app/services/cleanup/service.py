"""Retention: delete old processed/filtered messages, keep News + source URLs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message, MessageStatus, NewsSource


class CleanupService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def cleanup_old_messages(self, *, retention_days: int) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        # Detach FK references first so SET NULL is explicit
        await self._session.execute(
            update(NewsSource)
            .where(
                NewsSource.message_id.in_(
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
