"""Heuristic AI fallback when Groq is disabled / unavailable."""

from __future__ import annotations

from typing import Sequence

from app.services.ai.base import AIService, NewsAnalysisResult, SearchAnswer
from app.services.scoring import HeuristicSummarizer, ImportanceScorer
import time


class HeuristicAIService:
    """No external API — keeps pipeline working offline."""

    provider_name = "heuristic"

    def __init__(self) -> None:
        self._summarizer = HeuristicSummarizer()
        self._scorer = ImportanceScorer()

    async def analyze_message(
        self,
        text: str,
        *,
        source_count: int = 1,
        channel_title: str | None = None,
    ) -> NewsAnalysisResult:
        if not (text or "").strip():
            return NewsAnalysisResult(
                is_news=False,
                title="",
                summary="",
                category="Other",
                importance_score=0.0,
                reason="empty",
            )
        summary = self._summarizer.summarize([text], channel_titles=[channel_title] if channel_title else None)
        score = self._scorer.score(
            source_count=source_count,
            text=text,
            published_at_timestamps=[time.time()],
            now_timestamp=time.time(),
        )
        return NewsAnalysisResult(
            is_news=True,
            title=summary.title,
            summary=summary.summary,
            category=summary.category or "Other",
            importance_score=score,
            reason=None,
        )

    async def answer_search(
        self,
        query: str,
        contexts: Sequence[tuple[int, str, str]],
    ) -> SearchAnswer:
        if not contexts:
            return SearchAnswer(answer="Ничего не нашлось по этому запросу.", used_news_ids=())
        lines = [f"По запросу «{query}» нашлось:"]
        ids: list[int] = []
        for news_id, title, summary in contexts[:5]:
            ids.append(news_id)
            lines.append(f"• {title}: {summary[:180]}")
        return SearchAnswer(answer="\n".join(lines), used_news_ids=tuple(ids))

    async def close(self) -> None:
        return None


# Protocol satisfaction helper
def _check() -> AIService:
    return HeuristicAIService()
