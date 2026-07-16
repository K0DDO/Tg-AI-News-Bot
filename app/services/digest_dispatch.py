"""Periodic feed push — same UI as Лента; edit unread previous instead of spam."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.bot.keyboards import feed_keyboard
from app.bot.ui import format_feed
from app.config import get_settings
from app.database import get_session_factory
from app.models import User, UserSettings
from app.services.preferences import FeedService, PreferencesService
from app.services.time_prefs import is_digest_due, is_dnd_active

logger = logging.getLogger(__name__)


async def run_digest_cycle() -> dict:
    """Scan users due for a feed push and send/update unread feed."""
    settings = get_settings()
    if not settings.bot_token:
        logger.warning("digest skipped: BOT_TOKEN empty")
        return {"sent": 0, "skipped": 0, "errors": 0, "updated": 0}

    sent = 0
    updated = 0
    skipped = 0
    errors = 0
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
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
                from app.services.whitelist import WhitelistService

                if not await WhitelistService(session).can_use_bot(user.telegram_id):
                    skipped += 1
                    continue
                if is_dnd_active(us) or not is_digest_due(us, now_utc=now):
                    skipped += 1
                    continue
                try:
                    result_kind = await _send_one(session, bot, user, us)
                    if result_kind == "sent":
                        sent += 1
                        us.last_digest_sent_at = datetime.now(timezone.utc)
                    elif result_kind == "updated":
                        updated += 1
                        us.last_digest_sent_at = datetime.now(timezone.utc)
                    else:
                        skipped += 1
                except Exception:
                    errors += 1
                    logger.exception("digest failed user_id=%s", user.id)
            await session.commit()
    finally:
        await bot.session.close()

    logger.info(
        "digest cycle sent=%s updated=%s skipped=%s errors=%s",
        sent,
        updated,
        skipped,
        errors,
    )
    return {"sent": sent, "updated": updated, "skipped": skipped, "errors": errors}


async def _send_one(session, bot: Bot, user: User, us: UserSettings) -> str | None:
    prefs = PreferencesService(session)
    lang = us.language or "ru"
    limit = max(1, min(int(us.feed_page_size or 5), get_settings().digest_default_limit))
    items, total = await FeedService(session).get_feed(user, limit=limit, offset=0)
    if not items:
        return None

    ids = [n.id for n in items]
    has_more = len(items) < total
    text = format_feed(lang, items, title_key="feed_title", empty_key="no_more_news")
    kb = feed_keyboard(lang, offset=0, page_ids=ids, has_more=has_more)
    chat_id = us.digest_chat_id or user.telegram_id

    # If previous push still unread — update that message in place
    still_unread = await prefs.digest_feed_still_unread(user)
    if still_unread and us.digest_message_id and chat_id:
        try:
            await bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=int(us.digest_message_id),
                reply_markup=kb,
                disable_web_page_preview=True,
            )
            await prefs.save_digest_message(
                user, int(chat_id), int(us.digest_message_id), event_ids=ids
            )
            return "updated"
        except TelegramBadRequest:
            pass
        except Exception:
            logger.exception("digest edit failed user_id=%s", user.id)

    # New push: remove previous interactive screen so buttons don't stack
    ui_chat, ui_msg = await prefs.get_ui_message(user)
    if ui_chat and ui_msg:
        try:
            await bot.delete_message(chat_id=int(ui_chat), message_id=int(ui_msg))
        except TelegramBadRequest:
            pass
        except Exception:
            pass
        await prefs.clear_ui_message(user)

    try:
        msg = await bot.send_message(
            chat_id,
            text,
            reply_markup=kb,
            disable_web_page_preview=True,
        )
    except Exception:
        logger.exception("digest send failed user_id=%s", user.id)
        return None

    await prefs.save_digest_message(user, msg.chat.id, msg.message_id, event_ids=ids)
    return "sent"
