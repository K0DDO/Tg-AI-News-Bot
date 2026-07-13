"""Replace relative day words (завтра, tomorrow, …) with concrete DD.MM dates."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

_PATTERNS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"\bпослезавтра\b", re.IGNORECASE), 2),
    (re.compile(r"\bday\s+after\s+tomorrow\b", re.IGNORECASE), 2),
    (re.compile(r"\bпозавчера\b", re.IGNORECASE), -2),
    (re.compile(r"\bзавтра\b", re.IGNORECASE), 1),
    (re.compile(r"\btomorrow\b", re.IGNORECASE), 1),
    (re.compile(r"\bвчера\b", re.IGNORECASE), -1),
    (re.compile(r"\byesterday\b", re.IGNORECASE), -1),
    (re.compile(r"\bсегодня\b", re.IGNORECASE), 0),
    (re.compile(r"\btoday\b", re.IGNORECASE), 0),
]

_THROUGH_NUM = re.compile(
    r"\bчерез\s+(\d+)\s+(?:день|дня|дней|day|days)\b",
    re.IGNORECASE,
)
_THROUGH_WORD = re.compile(
    r"\bчерез\s+(один|одну|два|две|три|четыре|пять|шесть|семь)\s+"
    r"(?:день|дня|дней)\b",
    re.IGNORECASE,
)

_WORD_DAYS = {
    "один": 1,
    "одну": 1,
    "два": 2,
    "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
}


def _fmt(d: date) -> str:
    return d.strftime("%d.%m")


def _as_date(reference: datetime | date | None) -> date:
    if reference is None:
        return datetime.now(timezone.utc).date()
    if isinstance(reference, date) and not isinstance(reference, datetime):
        return reference
    dt = reference
    if isinstance(dt, datetime) and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.date() if isinstance(dt, datetime) else reference  # type: ignore[return-value]


def resolve_relative_dates(text: str, reference: datetime | date | None = None) -> str:
    """
    Turn relative day words into DD.MM based on the news reference date.

    Example: «завтра Apple представит iPhone» → «14.07 Apple представит iPhone»
    """
    if not (text or "").strip():
        return text or ""
    base = _as_date(reference)
    out = text

    def through_num(m: re.Match[str]) -> str:
        return _fmt(base + timedelta(days=int(m.group(1))))

    def through_word(m: re.Match[str]) -> str:
        days = _WORD_DAYS.get(m.group(1).lower(), 0)
        return _fmt(base + timedelta(days=days)) if days else m.group(0)

    out = _THROUGH_NUM.sub(through_num, out)
    out = _THROUGH_WORD.sub(through_word, out)

    for pattern, offset in _PATTERNS:
        label = _fmt(base + timedelta(days=offset))
        out = pattern.sub(label, out)
    return out
