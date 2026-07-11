"""Semantic + optional AI-synthesized search."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.ai import create_ai_service
from app.services.ai.usage import log_ai_usage
from app.services.digest.service import NewsService
from app.services.ports import SearchHit
from app.services.search.keyword import KeywordSearch

logger = logging.getLogger(__name__)


class SemanticSearch:
    """
    1) Local embeddings cosine over News.embedding (free)
    2) Optional Groq synthesis over top hits
    Falls back to keyword search if semantic returns nothing useful.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        news_service: NewsService | None = None,
    ) -> None:
        self._session = session
        self._news = news_service or NewsService(session)
        self._keyword = KeywordSearch(session)
        self._ai = create_ai_service()
        self._settings = get_settings()

    async def search(self, query: str, *, limit: int = 10) -> list[SearchHit]:
        q = (query or "").strip()
        if not q:
            return []

        semantic = await self._news.semantic_candidates(q, limit=limit)
        hits = [
            SearchHit(
                news_id=news.id,
                score=round(sim * 10, 2),
                title=news.title,
                summary=news.summary,
            )
            for news, sim in semantic
            if sim >= 0.15
        ]
        if hits:
            return hits
        return await self._keyword.search(q, limit=limit)

    async def search_with_answer(self, query: str, *, limit: int = 8) -> tuple[str, list[SearchHit]]:
        hits = await self.search(query, limit=limit)
        if not hits:
            return "Ничего не нашлось.", []

        if not self._settings.ai_search_synthesis:
            lines = [f"Результаты по «{query}»:"]
            for h in hits[:5]:
                lines.append(f"• {h.title}")
            return "\n".join(lines), hits

        contexts = [(h.news_id, h.title, h.summary) for h in hits]
        answer = await self._ai.answer_search(query, contexts)
        await log_ai_usage(
            self._session,
            provider=getattr(self._ai, "provider_name", "unknown"),
            operation="answer_search",
        )
        return answer.answer, hits
