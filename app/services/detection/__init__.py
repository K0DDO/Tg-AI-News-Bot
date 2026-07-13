"""Rule + flag helpers for news / advertisement detection."""

from __future__ import annotations

import re

from app.services.ai.base import PostAnalysisResult
from app.services.filter import RuleBasedFilter

_AD = re.compile(
    r"(промокод|скидка\s*\d|подписывай|реклама|giveaway|promo\s*code|"
    r"affiliate|купить\s+сейчас|order\s+now)",
    re.I,
)


class NewsDetectionService:
    def __init__(self) -> None:
        self._rules = RuleBasedFilter()

    def rule_reject(self, text: str) -> str | None:
        result = self._rules.evaluate(text)
        if not result.passed:
            return result.reason
        return None

    def from_analysis(self, analysis: PostAnalysisResult) -> bool:
        return bool(analysis.is_news) and not analysis.is_advertisement


class AdvertisementDetectionService:
    def looks_like_ad(self, text: str) -> bool:
        return bool(_AD.search(text or ""))

    def from_analysis(self, analysis: PostAnalysisResult) -> bool:
        return bool(analysis.is_advertisement) or self.looks_like_ad(
            f"{analysis.title} {analysis.summary}"
        )
