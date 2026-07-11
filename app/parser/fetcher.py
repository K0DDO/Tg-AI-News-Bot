"""Fetch recent messages from enabled Telegram channels via Telethon."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import Channel as TlChannel
from telethon.tl.types import Message as TlMessage

from app.models import Channel
from app.parser.repository import MessageRepository
from app.utils.telegram import build_message_url

logger = logging.getLogger(__name__)


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

    async def fetch_channel(self, channel: Channel) -> list[FetchedMessage]:
        entity_ref: str | int
        if channel.username:
            entity_ref = channel.username
        else:
            entity_ref = channel.telegram_id

        try:
            entity = await self._client.get_entity(entity_ref)
        except Exception:
            logger.exception("Failed to resolve channel id=%s", channel.id)
            return []

        min_id = await self._messages.get_last_telegram_message_id(channel.id) or 0
        fetched: list[FetchedMessage] = []

        try:
            async for msg in self._client.iter_messages(entity, limit=self._limit, min_id=min_id):
                if not isinstance(msg, TlMessage) or not msg.id:
                    continue
                text = (msg.message or "").strip()
                if not text:
                    continue
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
                fetched.append(
                    FetchedMessage(
                        channel_id=channel.id,
                        telegram_message_id=msg.id,
                        text=text,
                        url=url,
                        published_at=published,
                    )
                )
        except FloodWaitError as exc:
            logger.warning("FloodWait %ss for channel id=%s", exc.seconds, channel.id)
        except Exception:
            logger.exception("Failed fetching channel id=%s", channel.id)

        # iter_messages returns newest first; keep chronological for pipeline
        fetched.sort(key=lambda m: m.telegram_message_id)
        return fetched

    async def ingest_channel(self, channel: Channel) -> int:
        """Fetch and persist new messages. Returns count of newly created rows."""
        items = await self.fetch_channel(channel)
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
