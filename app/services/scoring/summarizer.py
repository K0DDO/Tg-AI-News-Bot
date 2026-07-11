"""Heuristic title/summary/category without LLM (implements SummarizerPort)."""

from __future__ import annotations

import re
from typing import Sequence

from app.services.ports import SummaryResult

_CATEGORY_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(ai|ии|нейросет|chatgpt|openai|llm|machine learning)\b", re.I), "AI"),
    (re.compile(r"\b(nvidia|gpu|chip|процессор|полупроводник)\b", re.I), "Hardware"),
    (re.compile(r"\b(apple|iphone|macbook|ios|android|google)\b", re.I), "Technology"),
    (re.compile(r"\b(crypto|bitcoin|ethereum|блокчейн)\b", re.I), "Crypto"),
    (re.compile(r"\b(startup|funding|инвестиц|ipo)\b", re.I), "Business"),
    (re.compile(r"\b(security|взлом|уязвим|хакер)\b", re.I), "Security"),
]


class HeuristicSummarizer:
    def summarize(
        self,
        texts: Sequence[str],
        *,
        channel_titles: Sequence[str] | None = None,
    ) -> SummaryResult:
        primary = max((t.strip() for t in texts if t and t.strip()), key=len, default="")
        lines = [ln.strip() for ln in primary.splitlines() if ln.strip()]
        title = (lines[0] if lines else primary)[:180]
        if len(title) < 8:
            title = primary[:180] or "Без заголовка"
        summary = primary[:400]
        if len(primary) > 400:
            summary = summary.rsplit(" ", 1)[0] + "…"
        category = self._guess_category(primary)
        return SummaryResult(title=title, summary=summary, category=category)

    def _guess_category(self, text: str) -> str:
        for pattern, category in _CATEGORY_RULES:
            if pattern.search(text):
                return category
        return "General"
