"""Queue helpers: enqueue AI batches, claim/run jobs."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Channel, Message
from app.models.enums import MessageStatus
from app.models.processing_job import ProcessingJob
from app.parser.repository import MessageRepository
from app.services.ai import create_ai_service
from app.services.embedding import build_embedding
from app.services.events import EventPipeline

logger = logging.getLogger(__name__)

STAGE_CONNECT = "connect"
STAGE_FETCH = "fetch"
STAGE_CLEAN = "clean"
STAGE_DEDUPE = "dedupe"
STAGE_AI = "ai"
STAGE_RELATIONS = "relations"
STAGE_SAVE = "save"
STAGE_DONE = "done"


async def enqueue_ai_batches_for_raw(
    session: AsyncSession,
    *,
    backfill_job_id: int | None = None,
    channel_id: int | None = None,
    batch_size: int | None = None,
    limit: int = 2000,
) -> int:
    """Create ai_batch jobs for RAW messages not already queued."""
    settings = get_settings()
    size = max(5, min(50, int(batch_size or settings.ai_batch_size or 30)))
    q = (
        select(Message.id, Message.channel_id)
        .where(Message.status == MessageStatus.RAW.value)
        .order_by(Message.id.asc())
        .limit(limit)
    )
    if channel_id is not None:
        q = q.where(Message.channel_id == channel_id)
    rows = list((await session.execute(q)).all())
    if not rows:
        return 0

    # Skip ids already in queued/running batches
    existing = (
        await session.execute(
            select(ProcessingJob.message_ids).where(
                ProcessingJob.job_type == "ai_batch",
                ProcessingJob.status.in_(("queued", "running")),
            )
        )
    ).scalars().all()
    busy: set[int] = set()
    for ids in existing:
        if ids:
            busy.update(int(x) for x in ids)

    pending = [(mid, cid) for mid, cid in rows if int(mid) not in busy]
    created = 0
    i = 0
    while i < len(pending):
        chunk = pending[i : i + size]
        i += size
        ids = [int(m) for m, _ in chunk]
        ch = int(chunk[0][1]) if chunk else channel_id
        job = ProcessingJob(
            job_type="ai_batch",
            status="queued",
            current_stage=STAGE_AI,
            channel_id=ch,
            backfill_job_id=backfill_job_id,
            message_ids=ids,
            total_tasks=len(ids),
            completed_tasks=0,
            failed_tasks=0,
            priority=50 if backfill_job_id else 100,
        )
        session.add(job)
        created += 1
    await session.flush()
    return created


async def claim_next_job(session: AsyncSession, *, job_type: str | None = None) -> ProcessingJob | None:
    now = datetime.now(timezone.utc)
    q = (
        select(ProcessingJob)
        .where(ProcessingJob.status == "queued")
        .where(or_(ProcessingJob.run_after.is_(None), ProcessingJob.run_after <= now))
        .order_by(ProcessingJob.priority.asc(), ProcessingJob.id.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job_type:
        q = q.where(ProcessingJob.job_type == job_type)
    job = (await session.execute(q)).scalar_one_or_none()
    if not job:
        return None
    job.status = "running"
    job.attempts = int(job.attempts or 0) + 1
    job.updated_at = now
    await session.flush()
    return job


async def process_ai_batch_job(session: AsyncSession, job: ProcessingJob) -> dict[str, int]:
    embedding = build_embedding()
    ai = create_ai_service()
    pipeline = EventPipeline(session, embedding=embedding, ai=ai)
    repo = MessageRepository(session)
    ids = [int(x) for x in (job.message_ids or [])]
    processed = filtered = merged = created = failed = 0
    job.current_stage = STAGE_AI
    for mid in ids:
        msg = await session.get(Message, mid)
        if msg is None or msg.status != MessageStatus.RAW.value:
            job.completed_tasks = int(job.completed_tasks or 0) + 1
            continue
        channel = await session.get(Channel, msg.channel_id)
        try:
            result = await pipeline.process_post(
                msg,
                channel_title=channel.title if channel else None,
                channel_username=channel.username if channel else None,
            )
            if result.action in {"filtered", "ad"}:
                filtered += 1
            elif result.action == "merged":
                merged += 1
                processed += 1
            else:
                created += 1
                processed += 1
            job.completed_tasks = int(job.completed_tasks or 0) + 1
        except Exception as exc:
            failed += 1
            job.failed_tasks = int(job.failed_tasks or 0) + 1
            job.last_error = str(exc)[:500]
            logger.exception("ai_batch message_id=%s failed", mid)
        await session.commit()

    # If AI keys exhausted mid-batch, remaining RAW stay for next cycle
    if getattr(ai, "keys_exhausted", False) and failed:
        job.status = "queued"
        job.run_after = datetime.now(timezone.utc) + timedelta(seconds=45)
        job.current_stage = STAGE_AI
    else:
        job.status = "done"
        job.current_stage = STAGE_DONE
    job.updated_at = datetime.now(timezone.utc)
    await session.flush()
    try:
        await ai.close()
    except Exception:
        pass
    return {
        "processed": processed,
        "filtered": filtered,
        "merged": merged,
        "created": created,
        "failed": failed,
    }


async def run_queue_cycle(*, max_jobs: int = 3) -> dict[str, int]:
    """Claim and run up to max_jobs from the durable queue."""
    sf = __import__("app.database", fromlist=["get_session_factory"]).get_session_factory()
    done = failed = 0
    async with sf() as session:
        for _ in range(max_jobs):
            job = await claim_next_job(session, job_type="ai_batch")
            if not job:
                break
            await session.commit()
            try:
                async with sf() as s2:
                    j2 = await s2.get(ProcessingJob, job.id)
                    if j2 is None:
                        continue
                    stats = await process_ai_batch_job(s2, j2)
                    await s2.commit()
                    done += 1
                    logger.info("queue job id=%s stats=%s", job.id, stats)
            except Exception:
                failed += 1
                logger.exception("queue job id=%s crashed", job.id)
                async with sf() as s3:
                    j3 = await s3.get(ProcessingJob, job.id)
                    if j3:
                        if j3.attempts >= j3.max_attempts:
                            j3.status = "failed"
                        else:
                            j3.status = "queued"
                            j3.run_after = datetime.now(timezone.utc) + timedelta(minutes=2)
                        await s3.commit()
    return {"jobs_done": done, "jobs_failed": failed}


async def queue_depth(session: AsyncSession) -> dict[str, int]:
    from sqlalchemy import func

    queued = await session.scalar(
        select(func.count()).select_from(ProcessingJob).where(ProcessingJob.status == "queued")
    )
    running = await session.scalar(
        select(func.count()).select_from(ProcessingJob).where(ProcessingJob.status == "running")
    )
    return {"queued": int(queued or 0), "running": int(running or 0)}
