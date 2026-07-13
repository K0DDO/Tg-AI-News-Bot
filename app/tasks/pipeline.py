"""Ingest → Event pipeline (analyze once, merge without LLM)."""

from __future__ import annotations

import logging

from app.config import get_settings
from app.database import get_session_factory
from app.models import Channel
from app.parser import ChannelFetcher, MessageRepository, create_telegram_client
from app.services.ai import create_ai_service
from app.services.channels import ChannelService
from app.services.cleanup import CleanupService
from app.services.embedding import build_embedding
from app.services.events import EventPipeline

logger = logging.getLogger(__name__)


async def run_ingest_cycle() -> dict[str, int]:
    embedding = build_embedding()
    ai = create_ai_service()
    session_factory = get_session_factory()
    created_messages = 0
    processed = 0
    filtered = 0
    merged = 0
    ai_created = 0
    ads = 0

    client = create_telegram_client()
    await client.connect()
    if not await client.is_user_authorized():
        logger.error("Telethon session is not authorized. Run scripts/auth_telethon.py first.")
        await client.disconnect()
        return {
            "created_messages": 0,
            "processed": 0,
            "filtered": 0,
            "merged": 0,
            "ai_created": 0,
            "ads": 0,
        }

    try:
        async with session_factory() as session:
            channels = await ChannelService(session).list_enabled_channels()
            messages_repo = MessageRepository(session)
            fetcher = ChannelFetcher(client, messages_repo)

            for channel in channels:
                try:
                    n = await fetcher.ingest_channel(channel)
                    created_messages += n
                    if n:
                        logger.info(
                            "Channel %s: +%s messages",
                            channel.username or channel.id,
                            n,
                        )
                except Exception:
                    logger.exception("Ingest failed for channel %s", channel.id)
            await session.commit()

            pipeline = EventPipeline(session, embedding=embedding, ai=ai)
            raw_messages = await messages_repo.list_raw_messages(limit=200)
            for message in raw_messages:
                channel = await session.get(Channel, message.channel_id)
                title = channel.title if channel else None
                username = channel.username if channel else None
                result = await pipeline.process_post(
                    message,
                    channel_title=title,
                    channel_username=username,
                )
                if result.action == "filtered":
                    filtered += 1
                elif result.action == "ad":
                    ads += 1
                    filtered += 1
                elif result.action == "merged":
                    merged += 1
                    processed += 1
                else:
                    ai_created += 1
                    processed += 1
            await session.commit()
    finally:
        await client.disconnect()
        close = getattr(ai, "close", None)
        if close:
            await close()

    return {
        "created_messages": created_messages,
        "processed": processed,
        "filtered": filtered,
        "merged": merged,
        "ai_created": ai_created,
        "ads": ads,
    }


async def run_cleanup() -> int:
    settings = get_settings()
    session_factory = get_session_factory()
    async with session_factory() as session:
        return await CleanupService(session).cleanup_old_messages(
            retention_days=settings.message_retention_days
        )
