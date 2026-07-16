"""Background worker: periodic ingest + cleanup (local split-process mode)."""

from __future__ import annotations

import asyncio
import logging
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings
from app.health import record_error, record_ingest
from app.logging_setup import setup_logging
from app.services.digest_dispatch import run_digest_cycle
from app.tasks.pipeline import run_cleanup, run_ingest_cycle, run_kg_maintenance, run_nightly_maintenance
from app.services.queue import run_queue_cycle

logger = logging.getLogger(__name__)


def _wrap_job(name: str, coro_fn):
    async def _runner(*args, **kwargs):
        try:
            result = await coro_fn(*args, **kwargs)
            if name == "ingest" and isinstance(result, dict):
                record_ingest(result)
            return result
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Job %s failed", name)
            record_error(f"{name}: {exc}")
            return None

    return _runner


async def run_worker() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, logs_dir=settings.logs_dir)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _wrap_job("ingest", run_ingest_cycle),
        "interval",
        seconds=settings.parser_poll_interval_seconds,
        id="ingest",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _wrap_job("cleanup", run_cleanup),
        "interval",
        hours=6,
        id="cleanup",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _wrap_job("kg_maintenance", run_kg_maintenance),
        "interval",
        hours=2,
        id="kg_maintenance",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _wrap_job("digest", run_digest_cycle),
        "interval",
        minutes=15,
        id="digest",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _wrap_job("ai_queue", run_queue_cycle),
        "interval",
        seconds=20,
        id="ai_queue",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _wrap_job("nightly", run_nightly_maintenance),
        "cron",
        hour=3,
        minute=0,
        id="nightly",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(
        "Worker started (poll every %ss)",
        settings.parser_poll_interval_seconds,
    )

    try:
        stats = await run_ingest_cycle()
        record_ingest(stats)
        logger.info("Initial ingest: %s", stats)
    except Exception as exc:
        logger.exception("Initial ingest failed")
        record_error(f"initial_ingest: {exc}")

    stop = asyncio.Event()

    def _request_stop(sig: signal.Signals) -> None:
        logger.info("Received %s — stopping worker", sig.name)
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop, sig)
        except (NotImplementedError, RuntimeError):
            pass

    await stop.wait()
    scheduler.shutdown(wait=False)
    logger.info("Worker stopped")


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Interrupted")


if __name__ == "__main__":
    main()
