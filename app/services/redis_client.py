"""Optional Redis for FSM + lightweight caches. Safe if Redis is down."""

from __future__ import annotations

import json
import logging
from typing import Any

from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import get_settings

logger = logging.getLogger(__name__)

_redis = None


async def get_redis():
    """Lazy redis singleton; returns None when unavailable."""
    global _redis
    settings = get_settings()
    if not settings.redis_url:
        return None
    if _redis is not None:
        return _redis
    try:
        from redis.asyncio import Redis

        client = Redis.from_url(settings.redis_url, decode_responses=True)
        await client.ping()
        _redis = client
        return _redis
    except Exception:
        logger.warning("Redis unavailable", exc_info=True)
        _redis = None
        return None


async def ping_redis() -> bool:
    client = await get_redis()
    if client is None:
        return False
    try:
        return bool(await client.ping())
    except Exception:
        return False


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        try:
            await _redis.aclose()
        except Exception:
            pass
        _redis = None


async def create_fsm_storage() -> BaseStorage:
    settings = get_settings()
    if not settings.redis_url:
        return MemoryStorage()
    try:
        from aiogram.fsm.storage.redis import RedisStorage

        return RedisStorage.from_url(settings.redis_url)
    except Exception:
        logger.warning("Redis FSM storage failed; using memory", exc_info=True)
        return MemoryStorage()


async def cache_get(key: str) -> Any | None:
    client = await get_redis()
    if client is None:
        return None
    try:
        raw = await client.get(f"briefly:{key}")
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> None:
    client = await get_redis()
    if client is None:
        return
    try:
        await client.set(f"briefly:{key}", json.dumps(value, default=str), ex=ttl_seconds)
    except Exception:
        logger.debug("cache_set failed", exc_info=True)
