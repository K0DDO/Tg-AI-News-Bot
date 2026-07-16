"""Factory for AIService / AIManager."""

from __future__ import annotations

import logging
from functools import lru_cache

from app.config import get_settings
from app.services.ai.base import AIService
from app.services.ai.heuristic import HeuristicAIService
from app.services.ai.manager import AIManager, build_manager_from_settings

logger = logging.getLogger(__name__)


def create_ai_service() -> AIService:
    settings = get_settings()
    provider = (settings.ai_provider or "heuristic").strip().lower()

    if provider in {"none", "off", "heuristic", "local"}:
        logger.info("AI provider: heuristic")
        return HeuristicAIService()

    # hybrid / groq / kimi / auto → manager with available keys
    manager = build_manager_from_settings(settings)
    if manager.groq_key_count == 0 and manager.kimi_key_count == 0:
        logger.warning("No GROQ/KIMI API keys configured — using heuristic")
        return HeuristicAIService()

    logger.info(
        "AI provider: manager groq_keys=%s kimi_keys=%s mode=%s",
        manager.groq_key_count,
        manager.kimi_key_count,
        provider,
    )
    return manager


@lru_cache
def get_ai_service() -> AIService:
    return create_ai_service()


def reset_ai_service_cache() -> None:
    get_ai_service.cache_clear()


def get_ai_manager() -> AIManager | None:
    svc = get_ai_service()
    return svc if isinstance(svc, AIManager) else None
