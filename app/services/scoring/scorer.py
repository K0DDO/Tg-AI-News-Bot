"""Importance scoring 0..10 (implements ScorerPort)."""

from __future__ import annotations

import re
from typing import Sequence

_IMPORTANT = re.compile(
    r"\b(breaking|срочно|запуск|release|acquired|ipo|breach|уязвим|"
    r"nvidia|openai|apple|google|microsoft|ai|llm)\b",
    re.I,
)


class ImportanceScorer:
    def score(
        self,
        *,
        source_count: int,
        text: str,
        published_at_timestamps: Sequence[float],
        now_timestamp: float,
    ) -> float:
        # Sources: 0..4
        source_score = min(4.0, float(source_count) * 1.2)

        # Freshness: 0..3 (decay over 48h)
        if published_at_timestamps:
            newest = max(published_at_timestamps)
            age_hours = max(0.0, (now_timestamp - newest) / 3600.0)
            freshness = max(0.0, 3.0 * (1.0 - age_hours / 48.0))
        else:
            freshness = 1.0

        # Length: 0..1.5
        length = len(text or "")
        if length < 80:
            length_score = 0.3
        elif length < 280:
            length_score = 0.9
        elif length < 1200:
            length_score = 1.5
        else:
            length_score = 1.2

        # Keywords: 0..1.5
        hits = len(_IMPORTANT.findall(text or ""))
        keyword_score = min(1.5, hits * 0.5)

        total = source_score + freshness + length_score + keyword_score
        return round(min(10.0, max(0.0, total)), 2)
