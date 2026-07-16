"""Ingest → Event pipeline (analyze once, merge without LLM)."""

from __future__ import annotations

import logging

from app.config import get_settings
from app.database import get_session_factory
from app.health import record_error, record_ingest
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
        record_error("Telethon session not authorized")
        await client.disconnect()
        empty = {
            "created_messages": 0,
            "processed": 0,
            "filtered": 0,
            "merged": 0,
            "ai_created": 0,
            "ads": 0,
            "backfilled": 0,
        }
        record_ingest(empty)
        return empty

    try:
        async with session_factory() as session:
            channels_svc = ChannelService(session)
            messages_repo = MessageRepository(session)
            fetcher = ChannelFetcher(client, messages_repo)
            active_jobs = await channels_svc.list_active_backfill_jobs()
            had_jobs = bool(active_jobs)

            # 1) Job-driven history backfill (progress tracked by stages)
            from datetime import datetime, timezone

            from app.services.queue import (
                STAGE_AI,
                STAGE_CONNECT,
                STAGE_DONE,
                STAGE_FETCH,
                STAGE_RELATIONS,
                STAGE_SAVE,
                enqueue_ai_batches_for_raw,
            )

            for job in active_jobs:
                now = datetime.now(timezone.utc)
                if not job.started_at:
                    job.started_at = now
                job.status = "running"
                job.current_stage = STAGE_CONNECT
                job.total_tasks = max(1, len(job.channel_ids or []))
                job.completed_tasks = len(job.done_channel_ids or [])
                await session.commit()

                job.current_stage = STAGE_FETCH
                await session.commit()
                done = list(job.done_channel_ids or [])
                for channel_id in list(job.channel_ids or []):
                    if channel_id in done:
                        continue
                    channel = await session.get(Channel, channel_id)
                    if channel is None:
                        done.append(channel_id)
                        job.done_channel_ids = list(done)
                        job.completed_tasks = len(done)
                        await session.commit()
                        continue
                    try:
                        n = await fetcher.backfill_channel(channel, days=job.days)
                        created_messages += n
                        backfilled += n
                        job.messages_fetched = int(job.messages_fetched or 0) + n
                        job.messages_total = int(job.messages_total or 0) + n
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
                        job.failed_tasks = int(job.failed_tasks or 0) + 1
                    done.append(channel_id)
                    job.done_channel_ids = list(done)
                    job.completed_tasks = len(done)
                    pending = channel.pending_backfill_days or 0
                    if pending and pending <= job.days:
                        channel.pending_backfill_days = None
                    await session.commit()

                # Enqueue AI batches instead of blocking forever inline
                job.current_stage = STAGE_AI
                job.status = "analyzing"
                job.total_tasks = max(1, int(job.messages_total or job.messages_fetched or 1))
                job.completed_tasks = 0
                await session.commit()
                n_batches = await enqueue_ai_batches_for_raw(
                    session, backfill_job_id=job.id, limit=3000
                )
                await session.commit()
                logger.info("Backfill job=%s enqueued %s AI batches", job.id, n_batches)

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

            # 3) Enqueue new RAW + process a limited inline batch for freshness
            await enqueue_ai_batches_for_raw(session, limit=500)
            await session.commit()

            pipeline = EventPipeline(session, embedding=embedding, ai=ai)
            raw_limit = 80  # keep ingest snappy; heavy work goes to queue
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

            # Update backfill AI progress from messages still raw vs processed
            from app.models import Message
            from app.models.enums import MessageStatus
            from sqlalchemy import func, select

            for job in active_jobs:
                if job.status not in {"analyzing", "running"}:
                    continue
                ch_ids = list(job.channel_ids or [])
                if not ch_ids:
                    job.status = "done"
                    job.current_stage = STAGE_DONE
                    job.finished_at = datetime.now(timezone.utc)
                    continue
                raw_left = await session.scalar(
                    select(func.count())
                    .select_from(Message)
                    .where(
                        Message.channel_id.in_(ch_ids),
                        Message.status == MessageStatus.RAW.value,
                    )
                )
                total_m = max(1, int(job.messages_total or job.messages_fetched or 1))
                left = int(raw_left or 0)
                done_m = max(0, total_m - left)
                job.completed_tasks = done_m
                job.total_tasks = total_m
                job.events_processed = int(job.events_processed or 0) + stats["processed"]
                job.events_created = int(job.events_created or 0) + stats["ai_created"]
                job.events_merged = int(job.events_merged or 0) + stats["merged"]
                if left == 0:
                    job.current_stage = STAGE_RELATIONS
                    job.current_stage = STAGE_SAVE
                    job.status = "done"
                    job.current_stage = STAGE_DONE
                    job.finished_at = datetime.now(timezone.utc)
                    job.completed_tasks = total_m
                else:
                    job.current_stage = STAGE_AI
            await session.commit()
    finally:
        await client.disconnect()
        close = getattr(ai, "close", None)
        if close:
            await close()

    out = {
        "created_messages": created_messages,
        "processed": processed,
        "filtered": filtered,
        "merged": merged,
        "ai_created": ai_created,
        "ads": ads,
        "backfilled": backfilled,
    }
    record_ingest(out)
    return out


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


async def run_nightly_maintenance() -> dict[str, int]:
    """03:00 maintenance: KG repair, orphan channels, message cleanup."""
    from app.services.knowledge import KnowledgeGraphService
    from app.services.preferences import PreferencesService

    session_factory = get_session_factory()
    out: dict[str, int] = {}
    async with session_factory() as session:
        kg_stats = await KnowledgeGraphService(session).rebuild_maintenance()
        out.update({f"kg_{k}": int(v) for k, v in kg_stats.items()})
        purged = await PreferencesService(session).purge_all_orphan_channels()
        await session.commit()
        out["orphan_channels_purged"] = purged
    cleaned = await run_cleanup()
    out["messages_cleaned"] = int(cleaned or 0)
    logger.info("Nightly maintenance %s", out)
    return out
