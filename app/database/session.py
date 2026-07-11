from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.async_database_url,
        echo=settings.app_debug,
        pool_pre_ping=True,
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session


# Backwards-compatible aliases used by services (resolved lazily via properties below)
def __getattr__(name: str):
    if name == "engine":
        return get_engine()
    if name == "AsyncSessionLocal":
        return get_session_factory()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
