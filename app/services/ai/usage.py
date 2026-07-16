"""Persist AI call metrics for the admin dashboard."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AiUsageLog
from app.services.ai.base import CallMeta


async def log_ai_usage(
    session: AsyncSession,
    *,
    provider: str,
    operation: str,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    user_id: int | None = None,
    model: str | None = None,
    key_fingerprint: str | None = None,
    latency_ms: int | None = None,
    status: str = "ok",
    error_code: str | None = None,
) -> None:
    session.add(
        AiUsageLog(
            provider=provider,
            operation=operation,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            user_id=user_id,
            model=model,
            key_fingerprint=key_fingerprint,
            latency_ms=latency_ms,
            status=status or "ok",
            error_code=error_code,
        )
    )
    await session.flush()


async def log_call_meta(
    session: AsyncSession,
    meta: CallMeta | None,
    *,
    user_id: int | None = None,
    operation: str | None = None,
) -> None:
    if meta is None:
        return
    await log_ai_usage(
        session,
        provider=meta.provider or "unknown",
        operation=operation or meta.operation or "unknown",
        tokens_in=meta.tokens_in,
        tokens_out=meta.tokens_out,
        user_id=user_id,
        model=meta.model or None,
        key_fingerprint=meta.key_fingerprint or None,
        latency_ms=meta.latency_ms or None,
        status=meta.status or "ok",
        error_code=meta.error_code or None,
    )
