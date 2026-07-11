"""Factory for AIService implementations."""

from __future__ import annotations

import logging
from functools import lru_cache

from app.config import get_settings
from app.services.ai.base import AIService
from app.services.ai.groq_client import GroqClient
from app.services.ai.groq_service import GroqAIService
from app.services.ai.heuristic import HeuristicAIService

logger = logging.getLogger(__name__)


def create_ai_service() -> AIService:
    settings = get_settings()
    provider = (settings.ai_provider or "heuristic").strip().lower()

    if provider in {"none", "off", "heuristic", "local"}:
        logger.info("AI provider: heuristic")
        return HeuristicAIService()

    if provider == "groq":
        if not settings.groq_api_key:
            logger.warning("AI_PROVIDER=groq but GROQ_API_KEY empty — using heuristic")
            return HeuristicAIService()
        client = GroqClient(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            base_url=settings.groq_base_url,
            timeout=settings.groq_timeout_seconds,
        )
        logger.info("AI provider: groq model=%s", settings.groq_model)
        return GroqAIService(client)

    logger.warning("Unknown AI_PROVIDER=%s — using heuristic", provider)
    return HeuristicAIService()


@lru_cache
def get_ai_service() -> AIService:
    return create_ai_service()


def reset_ai_service_cache() -> None:
    get_ai_service.cache_clear()
