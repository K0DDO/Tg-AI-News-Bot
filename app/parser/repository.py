"""Persist ingested Telegram messages."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message, MessageStatus


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_last_telegram_message_id(self, channel_id: int) -> int | None:
        result = await self._session.execute(
            select(func.max(Message.telegram_message_id)).where(Message.channel_id == channel_id)
        )
        return result.scalar_one_or_none()

    async def upsert_message(
        self,
        *,
        channel_id: int,
        telegram_message_id: int,
        text: str,
        url: str,
        published_at: datetime,
    ) -> tuple[Message, bool]:
        """Insert message if new. Returns (message, created)."""
        stmt = (
            insert(Message)
            .values(
                channel_id=channel_id,
                telegram_message_id=telegram_message_id,
                text=text or "",
                url=url,
                published_at=published_at,
                status=MessageStatus.RAW.value,
            )
            .on_conflict_do_nothing(
                constraint="uq_messages_channel_id_telegram_message_id",
            )
            .returning(Message.id)
        )
        result = await self._session.execute(stmt)
        row = result.first()
        if row is None:
            existing = await self._session.execute(
                select(Message).where(
                    Message.channel_id == channel_id,
                    Message.telegram_message_id == telegram_message_id,
                )
            )
            return existing.scalar_one(), False

        await self._session.flush()
        message = await self._session.get(Message, row[0])
        assert message is not None
        return message, True

    async def list_raw_messages(self, *, limit: int = 100) -> list[Message]:
        result = await self._session.execute(
            select(Message)
            .where(Message.status == MessageStatus.RAW.value)
            .order_by(Message.published_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
