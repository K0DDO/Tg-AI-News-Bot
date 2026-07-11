"""Background worker: periodic ingest + cleanup."""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings
from app.tasks.pipeline import run_cleanup, run_ingest_cycle

logger = logging.getLogger(__name__)


async def run_worker() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
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
