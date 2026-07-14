"""Background worker: periodic ingest + cleanup."""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings
from app.logging_setup import setup_logging
from app.tasks.pipeline import run_cleanup, run_ingest_cycle, run_kg_maintenance

logger = logging.getLogger(__name__)


async def run_worker() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, logs_dir=settings.logs_dir)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_ingest_cycle,
        "interval",
        seconds=settings.parser_poll_interval_seconds,
        id="ingest",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_cleanup,
        "interval",
        hours=6,
        id="cleanup",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_kg_maintenance,
        "interval",
        hours=2,
        id="kg_maintenance",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(
        "Worker started (poll every %ss)",
        settings.parser_poll_interval_seconds,
    )
    # Run once immediately
    try:
        stats = await run_ingest_cycle()
        logger.info("Initial ingest: %s", stats)
    except Exception:
        logger.exception("Initial ingest failed")

    stop = asyncio.Event()
    await stop.wait()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
