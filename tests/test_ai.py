"""Unit tests for AI layer (no network)."""

import pytest

from app.services.ai.groq_service import _to_analysis
from app.services.ai.heuristic import HeuristicAIService


@pytest.mark.asyncio
async def test_heuristic_analyze_news():
    ai = HeuristicAIService()
    result = await ai.analyze_post(
        "NVIDIA представила новую архитектуру GPU для обучения LLM моделей",
        source_count=1,
        channel_title="Tech",
    )
    assert result.is_news is True
    assert result.is_advertisement is False
    assert result.title
    assert result.summary
    assert result.topic
    assert 0 <= result.importance_score <= 10
    assert "NVIDIA" in " ".join(result.entities).upper() or "nvidia" in (result.topic or "").lower()


@pytest.mark.asyncio
async def test_heuristic_ad_rejected():
    ai = HeuristicAIService()
    result = await ai.analyze_post("Промокод SALE50 — скидка 50% купить сейчас")
    assert result.is_advertisement is True
    assert result.is_news is False


@pytest.mark.asyncio
async def test_heuristic_empty_not_news():
    ai = HeuristicAIService()
    result = await ai.analyze_post("   ")
    assert result.is_news is False


def test_groq_json_mapping():
    raw = {
        "is_news": True,
        "is_advertisement": False,
        "title": "NVIDIA представила GPU",
        "summary": "Коротко о релизе.",
        "category": "technology",
        "topic": "NVIDIA представила новую GPU архитектуру",
        "entities": ["NVIDIA"],
        "keywords": ["GPU"],
        "importance_score": 8.5,
        "reason": None,
    }
    result = _to_analysis(raw)
    assert result.is_news is True
    assert result.category == "technology"
    assert result.importance_score == 8.5
    assert result.entities == ("NVIDIA",)


def test_groq_json_unknown_category():
    result = _to_analysis(
        {
            "is_news": True,
            "is_advertisement": False,
            "title": "X",
            "summary": "Y",
            "category": "CryptoXYZ",
            "topic": "Something happened",
            "importance_score": 11,
            "entities": ["Bitcoin"],
            "why_important": "market move",
        }
    )
    assert result.category == "other"
    assert result.importance_score == 10.0
    ok = _to_analysis(
        {
            "is_news": True,
            "title": "X",
            "summary": "Y",
            "category": "Politics",
            "importance_score": 5,
        }
    )
    assert ok.category == "politics"
    huge = _to_analysis(
        {
            "is_news": True,
            "title": "X",
            "summary": "Y",
            "category": "A" * 40,
            "importance_score": 5,
        }
    )
    assert huge.category == "other"


@pytest.mark.asyncio
async def test_heuristic_search_answer():
    ai = HeuristicAIService()
    answer = await ai.answer_question(
        "NVIDIA",
        [(1, "NVIDIA GPU", "Новая архитектура"), (2, "Burger King menu", "Новые бургеры")],
    )
    assert answer.relevant is True
    assert 1 in answer.used_event_ids
    assert 2 not in answer.used_event_ids
