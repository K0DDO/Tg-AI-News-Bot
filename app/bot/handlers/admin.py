"""Admin-only diagnostics (/status). No web dashboard."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.health import format_uptime, last_errors, last_ingest, started_at
from app.models import Event, Message as TgMessage, User
from app.services.admin_service import AdminService
from app.services.redis_client import ping_redis

router = Router(name="admin")


async def _is_admin(session: AsyncSession, user: User | None, telegram_id: int | None) -> bool:
    if user is not None:
        try:
            if await AdminService(session).is_admin_user(user):
                return True
        except Exception:
            pass
    if telegram_id is None:
        return False
    return telegram_id in get_settings().admin_id_set()


@router.message(Command("status"))
async def cmd_status(message: Message, session: AsyncSession, db_user: User) -> None:
    if not await _is_admin(session, db_user, message.from_user.id if message.from_user else None):
        return

    settings = get_settings()
    lines = [
        "<b>Briefly /status</b>",
        "",
        f"Bot: ✅ running ({settings.app_env})",
        f"Uptime: {format_uptime()}",
        f"Started: {started_at().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

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

    redis_ok = await ping_redis()
    lines.append(f"Redis: {'✅' if redis_ok else '❌ (memory FSM)'}")

    try:
        users_n = await session.scalar(select(func.count()).select_from(User)) or 0
        events_n = await session.scalar(
            select(func.count()).select_from(Event).where(Event.status == "active")
        ) or 0
        posts_n = await session.scalar(select(func.count()).select_from(TgMessage)) or 0
        lines.append("")
        lines.append(f"Users: {users_n}")
        lines.append(f"Events: {events_n}")
        lines.append(f"Telegram posts: {posts_n}")
    except Exception as exc:
        lines.append(f"Counts: ❌ {exc}")

    ingest = last_ingest()
    if ingest:
        lines.append("")
        lines.append(
            "Last ingest: "
            f"+{ingest.get('created_messages', 0)} msgs, "
            f"{ingest.get('processed', 0)} processed, "
            f"{ingest.get('merged', 0)} merged"
        )
    else:
        lines.append("")
        lines.append("Last ingest: —")

    errs = last_errors(limit=3)
    lines.append("")
    if errs:
        lines.append("<b>Recent errors</b>")
        for e in errs:
            lines.append(f"• {e}")
    else:
        lines.append("Recent errors: none")

    lines.append("")
    lines.append(f"Parser interval: {settings.parser_poll_interval_seconds}s")
    lines.append(f"Session dir: {settings.telegram_session_dir}")
    lines.append(f"Embeddings: {settings.embedding_backend}")
    lines.append(f"AI: {settings.ai_provider}")
    lines.append("Mode: long polling + in-process scheduler")

    await message.answer("\n".join(lines))
