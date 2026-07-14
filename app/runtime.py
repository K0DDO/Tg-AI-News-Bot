"""Combined bot + worker runtime for a single briefly-app container."""

from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot.handlers import setup_routers
from app.bot.middlewares import DbUserMiddleware
from app.config import get_settings
from app.logging_setup import setup_logging
from app.services.redis_client import close_redis, create_fsm_storage, ping_redis
from app.tasks.pipeline import run_cleanup, run_ingest_cycle, run_kg_maintenance

logger = logging.getLogger("briefly.runtime")


async def _start_scheduler(settings) -> AsyncIOScheduler:
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
    logger.info("Scheduler started (poll every %ss)", settings.parser_poll_interval_seconds)
    return scheduler


async def run() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, logs_dir=settings.logs_dir or os.getenv("LOGS_DIR"))

    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")

    redis_ok = await ping_redis()
    logger.info("Redis: %s", "ok" if redis_ok else "unavailable (FSM falls back to memory)")

    storage = await create_fsm_storage()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)
    dp.update.middleware(DbUserMiddleware())
    dp.include_router(setup_routers())

    scheduler = await _start_scheduler(settings)

    # Kick once at boot (parser)
    try:
        stats = await run_ingest_cycle()
        logger.info("Initial ingest: %s", stats)
    except Exception:
        logger.exception("Initial ingest failed")

    logger.info("Bot polling started (long polling)")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await close_redis()
        await bot.session.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
