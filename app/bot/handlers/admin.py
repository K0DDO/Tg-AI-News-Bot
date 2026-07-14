"""Admin-only diagnostics (/status). No web dashboard."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Event, Message as TgMessage, User
from app.services.redis_client import ping_redis

router = Router(name="admin")


def _is_admin(telegram_id: int | None) -> bool:
    if telegram_id is None:
        return False
    return telegram_id in get_settings().admin_id_set()


@router.message(Command("status"))
async def cmd_status(message: Message, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id if message.from_user else None):
        return

    settings = get_settings()
    lines = ["<b>Briefly /status</b>", ""]

    # PostgreSQL
    pg_ok = False
    db_size = "?"
    try:
        await session.execute(text("SELECT 1"))
        pg_ok = True
        size = await session.scalar(text("SELECT pg_size_pretty(pg_database_size(current_database()))"))
        db_size = str(size or "?")
    except Exception as exc:
        lines.append(f"PostgreSQL: ❌ {exc}")
    if pg_ok:
        lines.append(f"PostgreSQL: ✅ ({db_size})")

    # Redis
    redis_ok = await ping_redis()
    lines.append(f"Redis: {'✅' if redis_ok else '❌'}")

    # Counts
    try:
        users_n = await session.scalar(select(func.count()).select_from(User)) or 0
        events_n = await session.scalar(
            select(func.count()).select_from(Event).where(Event.status == "active")
        ) or 0
        posts_n = await session.scalar(select(func.count()).select_from(TgMessage)) or 0
        lines.append(f"Users: {users_n}")
        lines.append(f"Events: {events_n}")
        lines.append(f"Telegram posts: {posts_n}")
    except Exception as exc:
        lines.append(f"Counts: ❌ {exc}")

    lines.append("")
    lines.append(f"Parser interval: {settings.parser_poll_interval_seconds}s")
    lines.append(f"Embeddings: {settings.embedding_backend}")
    lines.append(f"AI: {settings.ai_provider}")
    lines.append("Scheduler: ✅ (in-process APScheduler)")
    lines.append("Search: ✅ (in-process)")
    lines.append("Knowledge Graph: ✅ (in-process)")
    lines.append("Bot mode: long polling")

    await message.answer("\n".join(lines))
