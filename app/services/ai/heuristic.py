"""Heuristic AI fallback when Groq is disabled / unavailable."""

from __future__ import annotations

import re
import time
from typing import Sequence

from app.services.ai.base import PostAnalysisResult, SearchAnswer, TranslationResult
from app.services.scoring import HeuristicSummarizer, ImportanceScorer

_TOPIC_ENTITIES = re.compile(
    r"\b(OpenAI|ChatGPT|GPT-?\d*|Claude|Gemini|NVIDIA|Apple|iPhone(?:\s*\d+\s*Pro)?|"
    r"Google|Microsoft|Cursor|Windows|Linux|Tesla|Meta|Amazon|Intel|AMD|Docker|"
    r"Kubernetes|Steam(?:\s*Machine)?|Burger\s*King)\b",
    re.I,
)

_AD_MARKERS = re.compile(
    r"(промокод|скидка\s*\d|подписывай|реклама|giveaway|promo\s*code|discount\s*\d|"
    r"купить\s+сейчас|order\s+now|affiliate)",
    re.I,
)


class HeuristicAIService:
    provider_name = "heuristic"

    def __init__(self) -> None:
        self._summarizer = HeuristicSummarizer()
        self._scorer = ImportanceScorer()

    async def analyze_post(
        self,
        text: str,
        *,
        source_count: int = 1,
        channel_title: str | None = None,
    ) -> PostAnalysisResult:
        if not (text or "").strip():
            return PostAnalysisResult(
                is_news=False,
                is_advertisement=False,
                title="",
                summary="",
                category="Other",
                topic=None,
                reason="empty",
            )
        is_ad = bool(_AD_MARKERS.search(text))
        if is_ad:
            return PostAnalysisResult(
                is_news=False,
                is_advertisement=True,
                title="",
                summary="",
                category="Other",
                topic=None,
                reason="advertisement",
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
        entities = tuple(dict.fromkeys(m.group(0).strip() for m in _TOPIC_ENTITIES.finditer(text)))
        # Topic = event sentence, not a single word
        topic = summary.title if summary.title else (entities[0] if entities else None)
        if topic and len(topic.split()) < 3 and entities:
            topic = f"{entities[0]}: {summary.title}" if summary.title else entities[0]
        why = f"Источники: {source_count}; сущности: {', '.join(entities) or '—'}"
        lang = await self.detect_language(text)
        return PostAnalysisResult(
            is_news=True,
            is_advertisement=False,
            title=summary.title,
            summary=summary.summary,
            category=summary.category or "Other",
            topic=str(topic)[:512] if topic else None,
            entities=entities,
            keywords=entities,
            importance_score=score,
            why_important=why,
            reasoning=why,
            language=lang,
        )

    async def analyze_message(self, text: str, *, source_count: int = 1, channel_title: str | None = None):
        return await self.analyze_post(text, source_count=source_count, channel_title=channel_title)

    async def answer_question(
        self,
        query: str,
        contexts: Sequence[tuple[int, str, str]],
    ) -> SearchAnswer:
        q_tokens = {t.lower() for t in re.findall(r"[\w]{3,}", query or "", flags=re.UNICODE)}
        # Prefer brand tokens over bare numbers
        meaningful = {t for t in q_tokens if not t.isdigit()}
        check = meaningful or q_tokens
        relevant: list[tuple[int, str, str]] = []
        for event_id, title, summary in contexts:
            blob = f"{title} {summary}".lower()
            hits = sum(1 for t in check if t in blob)
            need = 1 if len(check) <= 2 else max(1, len(check) // 2)
            if hits >= need:
                relevant.append((event_id, title, summary))
        if not relevant:
            return SearchAnswer(
                answer="По вашему запросу релевантных новостей найдено не было.",
                used_event_ids=(),
                relevant=False,
            )
        lines = [f"По запросу «{query}»:"]
        ids: list[int] = []
        for event_id, title, summary in relevant[:5]:
            ids.append(event_id)
            lines.append(f"• {title}: {summary[:160]}")
        return SearchAnswer(answer="\n".join(lines), used_event_ids=tuple(ids), relevant=True)

    async def answer_search(self, query: str, contexts: Sequence[tuple[int, str, str]]):
        return await self.answer_question(query, contexts)

    async def translate(
        self,
        *,
        title: str,
        summary: str,
        target_lang: str,
    ) -> TranslationResult:
        return TranslationResult(title=title, summary=summary)

    async def translate_news(self, *, title: str, summary: str, target_lang: str):
        return await self.translate(title=title, summary=summary, target_lang=target_lang)

    async def detect_language(self, text: str) -> str:
        sample = (text or "")[:500]
        cyr = sum(1 for c in sample if "а" <= c.lower() <= "я" or c in "ёЁ")
        lat = sum(1 for c in sample if "a" <= c.lower() <= "z")
        if cyr > lat * 1.2:
            return "ru"
        if lat > 0:
            return "en"
        return "ru"

    async def close(self) -> None:
        return None
