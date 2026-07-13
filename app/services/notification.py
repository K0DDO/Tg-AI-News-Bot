"""Notification stub — ready for digests / push without wiring UX yet."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class NotificationService:
    async def notify_user(self, user_id: int, text: str) -> None:
        logger.info("notify user_id=%s: %s", user_id, text[:120])
