"""aiogram Telegram bot entrypoint."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers import setup_routers
from app.bot.middlewares import CleanChatMiddleware, DbUserMiddleware
from app.config import get_settings
from app.logging_setup import setup_logging

logger = logging.getLogger(__name__)


async def run_bot() -> None:
    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")

    setup_logging(settings.log_level, logs_dir=settings.logs_dir)

    from app.services.redis_client import create_fsm_storage

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=await create_fsm_storage())
    dp.update.middleware(DbUserMiddleware())
    # Only on user messages — never on callback_query (those are bot inline UIs)
    dp.message.middleware(CleanChatMiddleware())
    dp.include_router(setup_routers())

    logger.info("Bot polling started")
    await dp.start_polling(bot)


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
