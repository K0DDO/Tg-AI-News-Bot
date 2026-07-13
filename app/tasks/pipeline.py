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


async def _process_raw(
    session,
    *,
    messages_repo: MessageRepository,
    pipeline: EventPipeline,
    limit: int = 200,
) -> dict[str, int]:
    processed = filtered = merged = ai_created = ads = 0
    raw_messages = await messages_repo.list_raw_messages(limit=limit)
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
    return {
        "processed": processed,
        "filtered": filtered,
        "merged": merged,
        "ai_created": ai_created,
        "ads": ads,
    }


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
    backfilled = 0

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
            "backfilled": 0,
        }

    try:
        async with session_factory() as session:
            channels_svc = ChannelService(session)
            messages_repo = MessageRepository(session)
            fetcher = ChannelFetcher(client, messages_repo)
            active_jobs = await channels_svc.list_active_backfill_jobs()
            had_jobs = bool(active_jobs)

            # 1) Job-driven history backfill (progress tracked)
            for job in active_jobs:
                job.status = "running"
                await session.commit()
                done = list(job.done_channel_ids or [])
                for channel_id in list(job.channel_ids or []):
                    if channel_id in done:
                        continue
                    channel = await session.get(Channel, channel_id)
                    if channel is None:
                        done.append(channel_id)
                        job.done_channel_ids = list(done)
                        await session.commit()
                        continue
                    try:
                        n = await fetcher.backfill_channel(channel, days=job.days)
                        created_messages += n
                        backfilled += n
                        job.messages_fetched = int(job.messages_fetched or 0) + n
                        logger.info(
                            "Backfill job=%s %sd channel %s: +%s",
                            job.id,
                            job.days,
                            channel.username or channel.id,
                            n,
                        )
                    except Exception:
                        logger.exception(
                            "Backfill job=%s failed for channel %s",
                            job.id,
                            channel_id,
                        )
                    done.append(channel_id)
                    job.done_channel_ids = list(done)
                    pending = channel.pending_backfill_days or 0
                    if pending and pending <= job.days:
                        channel.pending_backfill_days = None
                    await session.commit()
                job.status = "analyzing"
                await session.commit()

            # Leftover channel flags without a job (e.g. race / legacy)
            pending = await channels_svc.list_pending_backfill()
            for channel in pending:
                days = int(channel.pending_backfill_days or 0)
                if days <= 0:
                    channel.pending_backfill_days = None
                    continue
                try:
                    n = await fetcher.backfill_channel(channel, days=days)
                    created_messages += n
                    backfilled += n
                except Exception:
                    logger.exception("Backfill failed for channel %s", channel.id)
                channel.pending_backfill_days = None
                await session.commit()

            # 2) Incremental poll
            channels = await channels_svc.list_enabled_channels()
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

            # 3) Analyze raw posts
            pipeline = EventPipeline(session, embedding=embedding, ai=ai)
            raw_limit = 500 if backfilled or had_jobs else 200
            stats = await _process_raw(
                session,
                messages_repo=messages_repo,
                pipeline=pipeline,
                limit=raw_limit,
            )
            processed += stats["processed"]
            filtered += stats["filtered"]
            merged += stats["merged"]
            ai_created += stats["ai_created"]
            ads += stats["ads"]
            await session.commit()

            if backfilled or had_jobs:
                for _ in range(5):
                    more = await _process_raw(
                        session,
                        messages_repo=messages_repo,
                        pipeline=pipeline,
                        limit=500,
                    )
                    batch = more["processed"] + more["filtered"]
                    if batch == 0:
                        break
                    processed += more["processed"]
                    filtered += more["filtered"]
                    merged += more["merged"]
                    ai_created += more["ai_created"]
                    ads += more["ads"]
                    for job in active_jobs:
                        if job.status == "analyzing":
                            job.events_processed = int(job.events_processed or 0) + more["processed"]
                    await session.commit()

            for job in active_jobs:
                if job.status in {"analyzing", "running", "queued"}:
                    job.status = "done"
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
        "backfilled": backfilled,
    }


async def run_cleanup() -> int:
    settings = get_settings()
    session_factory = get_session_factory()
    async with session_factory() as session:
        return await CleanupService(session).cleanup_old_messages(
            retention_days=settings.message_retention_days
        )


async def run_kg_maintenance() -> dict[str, int]:
    """Periodic: backfill missing Event→Node links + decay stale edges."""
    from app.services.knowledge import KnowledgeGraphService

    session_factory = get_session_factory()
    async with session_factory() as session:
        kg = KnowledgeGraphService(session)
        backfilled = await kg.backfill_events(limit=200)
        decayed = await kg.decay_stale_edges()
        await session.commit()
    return {"backfilled": backfilled, "decayed": decayed}
