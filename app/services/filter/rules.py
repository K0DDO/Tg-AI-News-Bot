"""Rule-based spam / promo filter (implements FilterPort)."""

from __future__ import annotations

import re

from app.services.ports import FilterResult

# Obvious promo / spam patterns (RU + EN)
_KEYWORD_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bпромокод\b", re.I), "promocode"),
    (re.compile(r"\bpromo\s*code\b", re.I), "promocode"),
    (re.compile(r"\bскидк[аиуе]\b", re.I), "discount"),
    (re.compile(r"\bdiscount\b", re.I), "discount"),
    (re.compile(r"подпиши(тесь|сь)\s+на\s+(наш|мой|канал)", re.I), "subscribe_cta"),
    (re.compile(r"subscribe\s+to\s+(our|my|the)\s+channel", re.I), "subscribe_cta"),
    (re.compile(r"\bреклама\b", re.I), "ad_label"),
    (re.compile(r"#\s*реклама\b", re.I), "ad_label"),
    (re.compile(r"\berid\b", re.I), "ad_label"),
    (re.compile(r"партн[её]рский\s+материал", re.I), "sponsored"),
    (re.compile(r"\bsponsored\b", re.I), "sponsored"),
    (re.compile(r"только\s+сегодня[!.,]?", re.I), "urgency_promo"),
    (re.compile(r"успей\s+купить", re.I), "urgency_promo"),
    (re.compile(r"бесплатный\s+вебинар", re.I), "webinar_spam"),
    (re.compile(r"заработ[ао]к\s+без\s+вложений", re.I), "scam"),
    (re.compile(r"казино|ставк[аи]|букмекер", re.I), "gambling"),
    (re.compile(r"t\.me/\+", re.I), "invite_link"),
    (re.compile(r"https?://t\.me/\+", re.I), "invite_link"),
]

_URL_HEAVY = re.compile(r"https?://", re.I)
_SHORT_JUNK = re.compile(r"^[\W\d_]{0,12}$", re.UNICODE)


class RuleBasedFilter:
    """Keyword / regex filter. Swap for an LLM FilterPort later."""

    def evaluate(self, text: str) -> FilterResult:
        normalized = (text or "").strip()
        if not normalized:
            return FilterResult(passed=False, reason="empty")

        if len(normalized) < 40 and _SHORT_JUNK.match(normalized):
            return FilterResult(passed=False, reason="too_short_junk")

        for pattern, reason in _KEYWORD_PATTERNS:
            if pattern.search(normalized):
                return FilterResult(passed=False, reason=reason)

        url_count = len(_URL_HEAVY.findall(normalized))
        if url_count >= 4 and len(normalized) < 280:
            return FilterResult(passed=False, reason="link_spam")

        # Mostly emoji / repeated chars
        letters = sum(1 for ch in normalized if ch.isalpha())
        if letters < 20 and len(normalized) > 30:
            return FilterResult(passed=False, reason="low_text_signal")

        return FilterResult(passed=True, reason=None)
