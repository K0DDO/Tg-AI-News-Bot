"""AI provider abstractions — swap Groq for OpenAI/Gemini/Claude/DeepSeek later."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence


from app.services.categories import ALLOWED_CATEGORIES, CATEGORY_ALIASES


@dataclass(frozen=True, slots=True)
class PostAnalysisResult:
    """Single-shot analysis of a Telegram post → Event fields."""

    is_news: bool
    is_advertisement: bool
    title: str
    summary: str
    category: str
    topic: str | None
    entities: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    importance_score: float = 0.0
    why_important: str | None = None
    reasoning: str | None = None
    language: str | None = None
    reason: str | None = None  # reject reason when not news


# Compat alias
NewsAnalysisResult = PostAnalysisResult


@dataclass(frozen=True, slots=True)
class SearchAnswer:
    answer: str
    used_event_ids: tuple[int, ...] = ()
    relevant: bool = True

    @property
    def used_news_ids(self) -> tuple[int, ...]:
        return self.used_event_ids


@dataclass(frozen=True, slots=True)
class TranslationResult:
    title: str
    summary: str


class AIService(Protocol):
    """Provider-agnostic AI interface. No other service talks to Groq directly."""

    provider_name: str

    async def analyze_post(
        self,
        text: str,
        *,
        source_count: int = 1,
        channel_title: str | None = None,
    ) -> PostAnalysisResult:
        """One-shot: news/ad/entities/topic/summary/importance (analyze once, reuse)."""
        ...

    async def answer_question(
        self,
        query: str,
        contexts: Sequence[tuple[int, str, str]],
    ) -> SearchAnswer:
        """Answer using ONLY provided Event contexts. Never invent facts."""
        ...

    async def translate(
        self,
        *,
        title: str,
        summary: str,
        target_lang: str,
    ) -> TranslationResult:
        ...

    async def detect_language(self, text: str) -> str:
        ...

    async def close(self) -> None:
        ...

    # --- compat wrappers ---
    async def analyze_message(
        self,
        text: str,
        *,
        source_count: int = 1,
        channel_title: str | None = None,
    ) -> PostAnalysisResult:
        return await self.analyze_post(
            text, source_count=source_count, channel_title=channel_title
        )

    async def answer_search(
        self,
        query: str,
        contexts: Sequence[tuple[int, str, str]],
    ) -> SearchAnswer:
        return await self.answer_question(query, contexts)

    async def translate_news(
        self,
        *,
        title: str,
        summary: str,
        target_lang: str,
    ) -> TranslationResult:
        return await self.translate(title=title, summary=summary, target_lang=target_lang)
