"""Periodic digest delivery — unread feed, no mark_read."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.bot.ui import format_feed
from app.config import get_settings
from app.database import get_session_factory
from app.models import User, UserSettings
from app.services.notification import NotificationService
from app.services.preferences import FeedService, PreferencesService
from app.services.time_prefs import is_digest_due, is_dnd_active

logger = logging.getLogger(__name__)


async def run_digest_cycle() -> dict:
    """Scan users due for a digest and send unread feed snippets."""
    settings = get_settings()
    if not settings.bot_token:
        logger.warning("digest skipped: BOT_TOKEN empty")
        return {"sent": 0, "skipped": 0, "errors": 0}

    sent = 0
    skipped = 0
    errors = 0
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    notifier = NotificationService(bot)
    try:
        sf = get_session_factory()
        async with sf() as session:
            result = await session.execute(
                select(UserSettings)
                .options(selectinload(UserSettings.user))
                .where(UserSettings.notifications_enabled.is_(True))
                .where(UserSettings.digest_mode != "off")
            )
            rows = list(result.scalars().all())
            now = datetime.now(timezone.utc)
            for us in rows:
                user: User | None = us.user
                if user is None or getattr(user, "is_banned", False):
                    skipped += 1
                    continue
                if is_dnd_active(us) or not is_digest_due(us, now_utc=now):
                    skipped += 1
                    continue
                try:
                    ok = await _send_one(session, notifier, user, us)
                    if ok:
                        sent += 1
                        us.last_digest_sent_at = datetime.now(timezone.utc)
                    else:
                        skipped += 1
                except Exception:
                    errors += 1
                    logger.exception("digest failed user_id=%s", user.id)
            await session.commit()
    finally:
        await bot.session.close()

    logger.info("digest cycle sent=%s skipped=%s errors=%s", sent, skipped, errors)
    return {"sent": sent, "skipped": skipped, "errors": errors}


async def _send_one(session, notifier: NotificationService, user: User, us: UserSettings) -> bool:
    prefs = PreferencesService(session)
    lang = us.language or "ru"
    limit = max(1, min(int(us.feed_page_size or 5), get_settings().digest_default_limit))
    items, _total = await FeedService(session).get_feed(user, limit=limit, offset=0)
    if not items:
        return False

    text = format_feed(
        lang,
        items,
        title_key="digest_title",
        empty_key="no_more_news",
    )
    # Do NOT mark_read — digest is a peek at the unread queue.
    chat_id = us.digest_chat_id or user.telegram_id
    msg = await notifier.send_html(chat_id, text)
    if msg is not None:
        await prefs.save_digest_message(user, chat_id, msg.message_id)
        return True
    return False
