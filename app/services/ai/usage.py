"""Persist AI call metrics for the admin dashboard."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AiUsageLog


async def log_ai_usage(
    session: AsyncSession,
    *,
    provider: str,
    operation: str,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    user_id: int | None = None,
) -> None:
    session.add(
        AiUsageLog(
            provider=provider,
            operation=operation,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            user_id=user_id,
        )
    )
    await session.flush()
