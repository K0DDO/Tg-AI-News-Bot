"""Heuristic AI fallback when Groq is disabled / unavailable."""

from __future__ import annotations

import re
import time
from typing import Sequence

from app.services.ai.base import NewsAnalysisResult, SearchAnswer, TranslationResult
from app.services.scoring import HeuristicSummarizer, ImportanceScorer

_TOPIC = re.compile(
    r"\b(OpenAI|ChatGPT|GPT-?\d*|Claude|Gemini|NVIDIA|Apple|iPhone|Google|Microsoft|"
    r"Cursor|Windows|Linux|Tesla|Meta|Amazon|Intel|AMD|Docker|Kubernetes)\b",
    re.I,
)


class HeuristicAIService:
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
        summary = self._summarizer.summarize(
            [text], channel_titles=[channel_title] if channel_title else None
        )
        score = self._scorer.score(
            source_count=source_count,
            text=text,
            published_at_timestamps=[time.time()],
            now_timestamp=time.time(),
        )
        m = _TOPIC.search(text) or _TOPIC.search(summary.title)
        topic = m.group(0) if m else (summary.title.split()[:2] and " ".join(summary.title.split()[:2]))
        why = f"Источники: {source_count}; свежесть и сигналы в тексте."
        return NewsAnalysisResult(
            is_news=True,
            title=summary.title,
            summary=summary.summary,
            category=summary.category or "Other",
            importance_score=score,
            reason=None,
            topic=str(topic)[:128] if topic else None,
            why_important=why,
        )

    async def answer_search(
        self,
        query: str,
        contexts: Sequence[tuple[int, str, str]],
    ) -> SearchAnswer:
        q_tokens = {t.lower() for t in re.findall(r"[\w]{3,}", query or "", flags=re.UNICODE)}
        relevant: list[tuple[int, str, str]] = []
        for news_id, title, summary in contexts:
            blob = f"{title} {summary}".lower()
            if q_tokens and sum(1 for t in q_tokens if t in blob) >= max(1, len(q_tokens) // 2):
                relevant.append((news_id, title, summary))
        if not relevant:
            return SearchAnswer(
                answer="По вашему запросу релевантных новостей найдено не было.",
                used_news_ids=(),
                relevant=False,
            )
        lines = [f"По запросу «{query}»:"]
        ids: list[int] = []
        for news_id, title, summary in relevant[:5]:
            ids.append(news_id)
            lines.append(f"• {title}: {summary[:160]}")
        return SearchAnswer(answer="\n".join(lines), used_news_ids=tuple(ids), relevant=True)

    async def translate_news(
        self,
        *,
        title: str,
        summary: str,
        target_lang: str,
    ) -> TranslationResult:
        # No API — return original; UI may show as-is
        return TranslationResult(title=title, summary=summary)

    async def close(self) -> None:
        return None
