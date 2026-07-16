"""Background watcher that edits a single Telegram message with backfill progress."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from app.bot.keyboards import backfill_progress_keyboard
from app.bot.ui import format_backfill_progress
from app.database import get_session_factory
from app.services.channels import ChannelService

logger = logging.getLogger(__name__)
_WATCHING: set[int] = set()


def start_backfill_watch(bot: Bot, job_id: int, lang: str) -> None:
    if job_id in _WATCHING:
        return
    _WATCHING.add(job_id)
    asyncio.create_task(_watch(bot, job_id, lang), name=f"bf-watch-{job_id}")


async def _watch(bot: Bot, job_id: int, lang: str) -> None:
    try:
        last_text = ""
        for _ in range(900):  # ~15 min at 1s
            await asyncio.sleep(1)
            sf = get_session_factory()
            async with sf() as session:
                job = await ChannelService(session).get_backfill_job(job_id)
                if job is None:
                    break
                text = format_backfill_progress(lang, job)
                chat_id = job.chat_id
                message_id = job.message_id
                status = job.status
                kb = backfill_progress_keyboard(lang, job.id)
            if not chat_id or not message_id:
                if status in {"done", "failed"}:
                    break
                continue
            if text != last_text:
                try:
                    await bot.edit_message_text(
                        text,
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=kb,
                        disable_web_page_preview=True,
                    )
                    last_text = text
                except TelegramBadRequest as exc:
                    # "message is not modified" is fine
                    if "not modified" not in str(exc).lower():
                        logger.debug("bf watch edit failed job=%s: %s", job_id, exc)
                except Exception:
                    logger.exception("bf watch failed job=%s", job_id)
            if status in {"done", "failed"}:
                break
    finally:
        _WATCHING.discard(job_id)
