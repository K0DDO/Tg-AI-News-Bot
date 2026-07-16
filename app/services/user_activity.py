"""Persist notable user actions for admin per-user audit."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserActionLog


async def log_user_action(
    session: AsyncSession,
    *,
    user: User | None = None,
    user_id: int | None = None,
    telegram_id: int | None = None,
    action: str,
    detail: str = "",
) -> None:
    tid = telegram_id
    uid = user_id
    if user is not None:
        uid = user.id
        tid = user.telegram_id
    session.add(
        UserActionLog(
            user_id=uid,
            telegram_id=tid,
            action=(action or "")[:64],
            detail=(detail or "")[:1000],
        )
    )
    await session.flush()
