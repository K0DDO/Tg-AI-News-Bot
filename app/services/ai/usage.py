"""Persist AI call metrics for the admin dashboard."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AiUsageLog


async def log_ai_usage(session: AsyncSession, *, provider: str, operation: str) -> None:
    session.add(AiUsageLog(provider=provider, operation=operation))
    await session.flush()
