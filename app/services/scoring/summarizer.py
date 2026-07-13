"""Heuristic title/summary/category without LLM (implements SummarizerPort)."""

from __future__ import annotations

from typing import Sequence

from app.services.categories import guess_category
from app.services.ports import SummaryResult


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
        category = guess_category(primary)
        return SummaryResult(title=title, summary=summary, category=category)
