"""Combined bot + worker runtime for a single briefly-app container."""

from __future__ import annotations

import asyncio
import logging
import os
import signal

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot.handlers import setup_routers
from app.bot.middlewares import CleanChatMiddleware, DbUserMiddleware
from app.config import get_settings
from app.health import record_admin_log, record_error, record_ingest, set_scheduler_running
from app.logging_setup import setup_logging
from app.services.digest_dispatch import run_digest_cycle
from app.services.redis_client import close_redis, create_fsm_storage, ping_redis
from app.tasks.pipeline import run_cleanup, run_ingest_cycle, run_kg_maintenance

logger = logging.getLogger("briefly.runtime")


def _wrap_job(name: str, coro_fn):
    """Never let a single job crash the scheduler / process."""
    from app.health import record_job_run

    async def _runner(*args, **kwargs):
        try:
            result = await coro_fn(*args, **kwargs)
            record_job_run(name)
            if name == "ingest" and isinstance(result, dict):
                record_ingest(result)
            return result
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Job %s failed", name)
            record_error(f"{name}: {exc}")
            return None

    _runner.__name__ = f"safe_{name}"
    return _runner


async def _start_scheduler(settings) -> AsyncIOScheduler:
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
    from app.services.queue import run_queue_cycle
    from app.tasks.pipeline import run_nightly_maintenance

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
    set_scheduler_running(True)
    logger.info("Scheduler started (poll every %ss)", settings.parser_poll_interval_seconds)
    return scheduler


async def run() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, logs_dir=settings.logs_dir or os.getenv("LOGS_DIR"))

    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")
    if not settings.admin_id_set():
        logger.warning(
            "ADMIN_TELEGRAM_IDS is empty — /status and owner bootstrap will not work"
        )

    redis_ok = await ping_redis()
    logger.info(
        "env=%s Redis: %s",
        settings.app_env,
        "ok" if redis_ok else "unavailable (FSM falls back to memory)",
    )

    storage = await create_fsm_storage()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)
    dp.update.middleware(DbUserMiddleware())
    # Only on user messages — never on callback_query (those are bot inline UIs)
    dp.message.middleware(CleanChatMiddleware())
    dp.include_router(setup_routers())

    scheduler = await _start_scheduler(settings)
    record_admin_log("INFO", "Parser/scheduler started")
    stop_event = asyncio.Event()

    def _request_stop(sig: signal.Signals) -> None:
        logger.info("Received %s — graceful shutdown", sig.name)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop, sig)
        except (NotImplementedError, RuntimeError):
            # Windows: signal handlers limited; aiogram / KeyboardInterrupt still work
            pass

    try:
        stats = await run_ingest_cycle()
        record_ingest(stats)
        logger.info("Initial ingest: %s", stats)
    except Exception as exc:
        logger.exception("Initial ingest failed")
        record_error(f"initial_ingest: {exc}")

    logger.info("Bot polling started (long polling)")
    poll_task = asyncio.create_task(
        dp.start_polling(bot, handle_signals=False),
        name="bot-polling",
    )
    wait_stop = asyncio.create_task(stop_event.wait(), name="stop-wait")

    done, pending = await asyncio.wait(
        {poll_task, wait_stop},
        return_when=asyncio.FIRST_COMPLETED,
    )

    logger.info("Shutting down…")
    if not poll_task.done():
        await dp.stop_polling()
        try:
            await asyncio.wait_for(poll_task, timeout=20)
        except (asyncio.TimeoutError, Exception):
            poll_task.cancel()
            try:
                await poll_task
            except Exception:
                pass
    for task in pending:
        task.cancel()

    try:
        scheduler.shutdown(wait=False)
        set_scheduler_running(False)
    except Exception:
        logger.exception("Scheduler shutdown failed")

    await close_redis()
    try:
        await bot.session.close()
    except Exception:
        logger.exception("Bot session close failed")
    logger.info("Shutdown complete")


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Interrupted")


if __name__ == "__main__":
    main()
