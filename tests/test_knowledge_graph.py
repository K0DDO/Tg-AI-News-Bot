"""Knowledge Graph unit tests (no DB required for linking/ranking/intent)."""

from __future__ import annotations

from app.services.knowledge.aliases import ALIAS_MAP, slugify
from app.services.knowledge.intent import SearchIntent, detect_intent, related_questions
from app.services.knowledge.ranking import combine_scores, graph_distance_score
from app.services.knowledge.service import KnowledgeGraphService


def test_alias_iphone_ru():
    assert ALIAS_MAP["айфон"][0] == "iPhone"
    assert ALIAS_MAP["чатгпт"][0] == "ChatGPT"
    assert ALIAS_MAP["open ai"][0] == "OpenAI"


def test_slugify():
    assert slugify("OpenAI") == "openai"
    assert slugify("iPhone 18 Pro") == "iphone-18-pro"


def test_resolve_one_aliases():
    kg = KnowledgeGraphService.__new__(KnowledgeGraphService)
    r = kg.resolve_one("айфон 18 pro")
    assert r is not None
    assert r.name == "iPhone 18 Pro"
    r2 = kg.resolve_one("Open AI")
    assert r2 is not None
    assert r2.name == "OpenAI"


def test_intent_news_vs_qa():
    assert detect_intent("Что нового по Apple?").intent == SearchIntent.NEWS
    assert detect_intent("Почему Apple судится с OpenAI?").intent == SearchIntent.QA
    assert detect_intent("Лучшие нейросети для блогеров").intent == SearchIntent.RECOMMENDATION
    assert detect_intent("Новости NVIDIA").intent in {SearchIntent.NEWS, SearchIntent.ENTITY}


def test_ranking_weights():
    s = combine_scores(
        semantic=1.0,
        graph_distance=1.0,
        sources=1.0,
        importance=1.0,
        freshness=1.0,
        personal=1.0,
    )
    assert abs(s - 1.0) < 1e-6
    assert graph_distance_score(0) == 1.0
    assert graph_distance_score(1) == 0.65


def test_related_questions():
    qs = related_questions("Что нового по Apple?", ["iPhone", "MacBook"], lang="ru")
    assert qs
    assert "iPhone" in qs[0]


def test_strip_at_mentions():
    from app.utils.text_clean import strip_at_mentions

    s = strip_at_mentions("Маски с миньонами — эксклюзив @trendsetter. С 7 июля.")
    assert "@trendsetter" not in s
    assert "миньонами" in s
    s2 = strip_at_mentions("Бургер, передают источники @trendsetter")
    assert "@" not in s2


def test_rostics_near_dup_overlap():
    from app.services.events.merge import content_overlap, is_near_duplicate

    a = "В Rostic's будут раздавать маски с миньонами всем, кто купит комбо МиньонБУМ. С 7 июля."
    b = "В меню Rostic's добавят БАНАНОВЫЙ Отто Бургер. Он будет продаваться в рамках комбо с миньонами с 7 июля."
    assert is_near_duplicate(a, b)
    assert content_overlap(a, b) >= 0.24
