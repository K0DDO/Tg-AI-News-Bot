"""aiogram Telegram bot entrypoint."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers import setup_routers
from app.bot.middlewares import DbUserMiddleware
from app.config import get_settings

logger = logging.getLogger(__name__)


async def run_bot() -> None:
    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")

    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(DbUserMiddleware())
    dp.include_router(setup_routers())

    logger.info("Bot polling started")
    await dp.start_polling(bot)


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
