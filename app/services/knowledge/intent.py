"""Query intent detection for Knowledge Graph search strategies."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class SearchIntent(str, Enum):
    NEWS = "news"  # Что нового по Apple?
    QA = "qa"  # Почему / как / что значит
    TIMELINE = "timeline"  # вчера / хронология
    RECOMMENDATION = "recommendation"  # лучшие / топ
    ENTITY = "entity"  # Все новости NVIDIA / iPhone 18 Pro
    DEEP = "deep"  # forced deep search


@dataclass(frozen=True, slots=True)
class IntentResult:
    intent: SearchIntent
    period_days: int | None  # override if timeline


_QA = re.compile(
    r"\b(почему|зачем|как\s+так|what\s+happened|why|how\s+come|объясн|разбер)\b",
    re.I,
)
_REC = re.compile(
    r"\b(лучш|топ|рекоменд|best|top|для\s+блогеров|which\s+should)\b",
    re.I,
)
_NEWS = re.compile(
    r"\b(что\s+нового|новост|news|updates?|что\s+извс|latest)\b",
    re.I,
)
_TIMELINE = re.compile(
    r"\b(вчера|сегодня|хронолог|timeline|история\s+событ|за\s+24|last\s+24|"
    r"недел[еиюя]|месяц|week|month|today|yesterday)\b",
    re.I,
)
_ENTITY_ALL = re.compile(r"\b(все\s+новост|all\s+news|everything\s+about)\b", re.I)

_PERIOD = [
    (re.compile(r"\b(сегодня|today|heute|hoy|сутки|24\s*h)\b", re.I), 1),
    (re.compile(r"\b(недел[еиюя]|week|woche|semana)\b", re.I), 7),
    (re.compile(r"\b(месяц[аеу]?|month|monat|mes)\b", re.I), 30),
]


def detect_intent(query: str, *, deep: bool = False) -> IntentResult:
    q = (query or "").strip()
    if deep:
        return IntentResult(intent=SearchIntent.DEEP, period_days=_period(q))
    if _QA.search(q):
        return IntentResult(intent=SearchIntent.QA, period_days=_period(q) or 60)
    if _REC.search(q):
        return IntentResult(intent=SearchIntent.RECOMMENDATION, period_days=_period(q) or 30)
    if _TIMELINE.search(q) and not _NEWS.search(q):
        return IntentResult(intent=SearchIntent.TIMELINE, period_days=_period(q) or 7)
    if _ENTITY_ALL.search(q) or (len(q.split()) <= 3 and not _NEWS.search(q) and not _QA.search(q)):
        # short entity-like queries
        if _NEWS.search(q):
            return IntentResult(intent=SearchIntent.NEWS, period_days=_period(q) or 14)
        return IntentResult(intent=SearchIntent.ENTITY, period_days=_period(q) or 30)
    if _NEWS.search(q):
        return IntentResult(intent=SearchIntent.NEWS, period_days=_period(q) or 14)
    if _TIMELINE.search(q):
        return IntentResult(intent=SearchIntent.TIMELINE, period_days=_period(q) or 7)
    return IntentResult(intent=SearchIntent.NEWS, period_days=_period(q) or 30)


def _period(q: str) -> int | None:
    for pattern, days in _PERIOD:
        if pattern.search(q or ""):
            return days
    return None


def related_questions(query: str, node_names: list[str], *, lang: str = "ru") -> list[str]:
    """Suggest follow-up queries from expanded nodes."""
    out: list[str] = []
    seen = {query.strip().lower()}
    for name in node_names[:6]:
        if lang == "ru":
            q = f"Что нового по {name}?"
        else:
            q = f"What's new with {name}?"
        if q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out[:5]
