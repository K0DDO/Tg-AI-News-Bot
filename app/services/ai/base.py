"""AI provider abstractions — swap Groq for OpenAI/Gemini/Claude/DeepSeek later."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence


ALLOWED_CATEGORIES = (
    "AI",
    "Technology",
    "Hardware",
    "Software",
    "Science",
    "Business",
    "Other",
)


@dataclass(frozen=True, slots=True)
class NewsAnalysisResult:
    is_news: bool
    title: str
    summary: str
    category: str
    importance_score: float
    reason: str | None = None
    topic: str | None = None
    why_important: str | None = None


@dataclass(frozen=True, slots=True)
class SearchAnswer:
    answer: str
    used_news_ids: tuple[int, ...] = ()
    relevant: bool = True


@dataclass(frozen=True, slots=True)
class TranslationResult:
    title: str
    summary: str


class AIService(Protocol):
    """Provider-agnostic AI interface used by the news pipeline and bot."""

    provider_name: str

    async def analyze_message(
        self,
        text: str,
        *,
        source_count: int = 1,
        channel_title: str | None = None,
    ) -> NewsAnalysisResult:
        ...

    async def answer_search(
        self,
        query: str,
        contexts: Sequence[tuple[int, str, str]],
    ) -> SearchAnswer:
        """
        Answer using ONLY provided contexts.
        If none are relevant, relevant=False and a honest empty message.
        """
        ...

    async def translate_news(
        self,
        *,
        title: str,
        summary: str,
        target_lang: str,
    ) -> TranslationResult:
        ...

    async def close(self) -> None:
        ...
