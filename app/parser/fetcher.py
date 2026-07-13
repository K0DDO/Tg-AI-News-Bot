"""Fetch recent messages from enabled Telegram channels via Telethon."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import Channel as TlChannel
from telethon.tl.types import Message as TlMessage

from app.models import Channel
from app.parser.repository import MessageRepository
from app.utils.telegram import build_message_url

logger = logging.getLogger(__name__)

# Limits for calendar backfill (busy channels can post a lot)
_BACKFILL_LIMITS = {
    1: 200,
    2: 400,
    7: 800,
    14: 1200,
    30: 2000,
}


@dataclass(frozen=True, slots=True)
class FetchedMessage:
    channel_id: int
    telegram_message_id: int
    text: str
    url: str
    published_at: datetime


class ChannelFetcher:
    def __init__(
        self,
        client: TelegramClient,
        messages: MessageRepository,
        *,
        limit_per_channel: int = 50,
    ) -> None:
        self._client = client
        self._messages = messages
        self._limit = limit_per_channel

    async def resolve_entity(self, username_or_id: str | int):
        return await self._client.get_entity(username_or_id)

    async def _resolve(self, channel: Channel):
        entity_ref: str | int
        if channel.username:
            entity_ref = channel.username
        else:
            entity_ref = channel.telegram_id
        try:
            return await self._client.get_entity(entity_ref)
        except Exception:
            logger.exception("Failed to resolve channel id=%s", channel.id)
            return None

    def _to_fetched(self, channel: Channel, entity, msg: TlMessage) -> FetchedMessage | None:
        if not isinstance(msg, TlMessage) or not msg.id:
            return None
        text = (msg.message or "").strip()
        if not text:
            return None
        username = channel.username
        if isinstance(entity, TlChannel) and entity.username:
            username = entity.username
        url = build_message_url(
            username=username,
            channel_id=channel.telegram_id,
            message_id=msg.id,
        )
        published = msg.date
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return FetchedMessage(
            channel_id=channel.id,
            telegram_message_id=msg.id,
            text=text,
            url=url,
            published_at=published,
        )

    async def fetch_channel(self, channel: Channel) -> list[FetchedMessage]:
        """Incremental fetch: only messages newer than last stored id."""
        entity = await self._resolve(channel)
        if entity is None:
            return []

        min_id = await self._messages.get_last_telegram_message_id(channel.id) or 0
        fetched: list[FetchedMessage] = []

        try:
            async for msg in self._client.iter_messages(entity, limit=self._limit, min_id=min_id):
                item = self._to_fetched(channel, entity, msg)
                if item:
                    fetched.append(item)
        except FloodWaitError as exc:
            logger.warning("FloodWait %ss for channel id=%s", exc.seconds, channel.id)
        except Exception:
            logger.exception("Failed fetching channel id=%s", channel.id)

        fetched.sort(key=lambda m: m.telegram_message_id)
        return fetched

    async def fetch_channel_since(
        self,
        channel: Channel,
        *,
        days: int,
        limit: int | None = None,
    ) -> list[FetchedMessage]:
        """
        Load history for the last `days` calendar days (newest → older, stop at cutoff).
        Does not use min_id — fills gaps / initial history.
        """
        entity = await self._resolve(channel)
        if entity is None:
            return []

        days = max(1, min(int(days), 30))
        cap = limit or _BACKFILL_LIMITS.get(days) or max(200, days * 80)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        fetched: list[FetchedMessage] = []

        try:
            async for msg in self._client.iter_messages(entity, limit=cap):
                published = msg.date
                if published is None:
                    continue
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                if published < cutoff:
                    break
                item = self._to_fetched(channel, entity, msg)
                if item:
                    fetched.append(item)
        except FloodWaitError as exc:
            logger.warning("FloodWait %ss during backfill channel id=%s", exc.seconds, channel.id)
        except Exception:
            logger.exception("Backfill failed for channel id=%s", channel.id)

        fetched.sort(key=lambda m: m.telegram_message_id)
        return fetched

    async def ingest_channel(self, channel: Channel) -> int:
        """Fetch and persist new messages. Returns count of newly created rows."""
        items = await self.fetch_channel(channel)
        return await self._persist(items)

    async def backfill_channel(self, channel: Channel, *, days: int) -> int:
        """Fetch and persist history for the last N days. Returns newly created count."""
        items = await self.fetch_channel_since(channel, days=days)
        return await self._persist(items)

    async def _persist(self, items: list[FetchedMessage]) -> int:
        created = 0
        for item in items:
            _, is_new = await self._messages.upsert_message(
                channel_id=item.channel_id,
                telegram_message_id=item.telegram_message_id,
                text=item.text,
                url=item.url,
                published_at=item.published_at,
            )
            if is_new:
                created += 1
        return created
