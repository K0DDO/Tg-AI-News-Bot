"""Groq-backed AIService implementation."""

from __future__ import annotations

import logging
from typing import Sequence

from app.services.ai.base import ALLOWED_CATEGORIES, NewsAnalysisResult, SearchAnswer
from app.services.ai.groq_client import GroqClient
from app.services.ai.heuristic import HeuristicAIService

logger = logging.getLogger(__name__)

_ANALYZE_SYSTEM = """You are a news analyst for a Telegram tech/AI news aggregator.
Return ONLY valid JSON with keys:
is_news (bool), title (string, concise Russian headline), summary (string, 2-4 Russian sentences),
category (one of: AI, Technology, Hardware, Software, Science, Business, Other),
importance_score (number 0-10), reason (string|null).

is_news=false for ads, promo codes, subscribe CTAs, spam, personal chatter, off-topic junk.
importance_score: weigh event scale, company fame, usefulness, and source_count hint.
"""


class GroqAIService:
    provider_name = "groq"

    def __init__(self, client: GroqClient) -> None:
        self._client = client
        self._fallback = HeuristicAIService()

    async def analyze_message(
        self,
        text: str,
        *,
        source_count: int = 1,
        channel_title: str | None = None,
    ) -> NewsAnalysisResult:
        clipped = (text or "").strip()[:4000]
        if not clipped:
            return NewsAnalysisResult(
                is_news=False,
                title="",
                summary="",
                category="Other",
                importance_score=0.0,
                reason="empty",
            )
        user = (
            f"channel: {channel_title or 'unknown'}\n"
            f"source_count_hint: {source_count}\n\n"
            f"message:\n{clipped}"
        )
        try:
            data = await self._client.chat_json(system=_ANALYZE_SYSTEM, user=user)
            return _to_analysis(data)
        except Exception:
            logger.exception("Groq analyze_message failed; using heuristic fallback")
            return await self._fallback.analyze_message(
                text,
                source_count=source_count,
                channel_title=channel_title,
            )

    async def answer_search(
        self,
        query: str,
        contexts: Sequence[tuple[int, str, str]],
    ) -> SearchAnswer:
        if not contexts:
            return SearchAnswer(answer="По сохранённым новостям ничего не нашлось.", used_news_ids=())
        blocks = []
        ids: list[int] = []
        for news_id, title, summary in contexts[:8]:
            ids.append(news_id)
            blocks.append(f"[{news_id}] {title}\n{summary}")
        system = (
            "You are a helpful Russian-speaking news assistant. "
            "Answer the user using ONLY the provided news snippets. "
            "Be concise (5-10 sentences max). If insufficient data, say so."
        )
        user = f"Вопрос: {query}\n\nНовости:\n" + "\n\n".join(blocks)
        try:
            answer = await self._client.chat_text(system=system, user=user)
            return SearchAnswer(answer=answer, used_news_ids=tuple(ids))
        except Exception:
            logger.exception("Groq answer_search failed; using heuristic fallback")
            return await self._fallback.answer_search(query, contexts)

    async def close(self) -> None:
        await self._client.close()


def _to_analysis(data: dict) -> NewsAnalysisResult:
    category = str(data.get("category") or "Other").strip()
    if category not in ALLOWED_CATEGORIES:
        category = "Other"
    try:
        score = float(data.get("importance_score", 0))
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(10.0, score))
    is_news = bool(data.get("is_news", False))
    title = str(data.get("title") or "").strip() or "Без заголовка"
    summary = str(data.get("summary") or "").strip()
    reason = data.get("reason")
    return NewsAnalysisResult(
        is_news=is_news,
        title=title[:512],
        summary=summary,
        category=category,
        importance_score=round(score, 2),
        reason=str(reason) if reason else None,
    )
