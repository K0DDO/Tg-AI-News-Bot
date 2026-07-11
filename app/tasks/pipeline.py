"""Ingest → rule filter → embed/merge → AI analyze (new only)."""

from __future__ import annotations

import logging

from app.config import get_settings
from app.database import get_session_factory
from app.models import Channel
from app.parser import ChannelFetcher, MessageRepository, create_telegram_client
from app.services.ai import create_ai_service
from app.services.channels import ChannelService
from app.services.cleanup import CleanupService
from app.services.clustering import HashingEmbedding, get_default_embedding
from app.services.digest import NewsService

logger = logging.getLogger(__name__)


def _build_embedding():
    settings = get_settings()
    backend = (settings.embedding_backend or "hashing").strip().lower()
    if backend in {"hashing", "hash", "local"}:
        logger.info("Embedding backend: hashing")
        return HashingEmbedding()
    if backend in {"sentence-transformers", "st", "transformer"}:
        try:
            emb = get_default_embedding(settings.embedding_model, prefer_transformer=True)
            if hasattr(emb, "_load"):
                emb._load()  # type: ignore[attr-defined]
            logger.info("Embedding backend: sentence-transformers")
            return emb
        except Exception:
            logger.exception("sentence-transformers unavailable, using HashingEmbedding")
            return HashingEmbedding()
    # auto
    try:
        emb = get_default_embedding(settings.embedding_model, prefer_transformer=True)
        if hasattr(emb, "_load"):
            emb._load()  # type: ignore[attr-defined]
        return emb
    except Exception:
        return HashingEmbedding()


async def run_ingest_cycle() -> dict[str, int]:
    embedding = _build_embedding()
    ai = create_ai_service()
    session_factory = get_session_factory()
    created_messages = 0
    processed = 0
    filtered = 0
    merged = 0
    ai_created = 0

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

            news_service = NewsService(session, embedding=embedding, ai=ai)
            raw_messages = await messages_repo.list_raw_messages(limit=200)
            for message in raw_messages:
                channel = await session.get(Channel, message.channel_id)
                title = channel.title if channel else None
                result = await news_service.process_message(message, channel_title=title)
                if result.action == "filtered":
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
    }


async def run_cleanup() -> int:
    settings = get_settings()
    session_factory = get_session_factory()
    async with session_factory() as session:
        deleted = await CleanupService(session).cleanup_old_messages(
            retention_days=settings.message_retention_days
        )
    logger.info("Cleanup removed %s messages", deleted)
    return deleted
