"""Unit tests for AI layer (no network)."""

import json

import pytest

from app.services.ai.groq_service import _to_analysis
from app.services.ai.heuristic import HeuristicAIService


@pytest.mark.asyncio
async def test_heuristic_analyze_news():
    ai = HeuristicAIService()
    result = await ai.analyze_message(
        "NVIDIA представила новую архитектуру GPU для обучения LLM моделей",
        source_count=1,
        channel_title="Tech",
    )
    assert result.is_news is True
    assert result.title
    assert result.summary
    assert 0 <= result.importance_score <= 10


@pytest.mark.asyncio
async def test_heuristic_empty_not_news():
    ai = HeuristicAIService()
    result = await ai.analyze_message("   ")
    assert result.is_news is False


def test_groq_json_mapping():
    raw = {
        "is_news": True,
        "title": "NVIDIA представила GPU",
        "summary": "Коротко о релизе.",
        "category": "Hardware",
        "importance_score": 8.5,
        "reason": None,
    }
    result = _to_analysis(raw)
    assert result.is_news is True
    assert result.category == "Hardware"
    assert result.importance_score == 8.5


def test_groq_json_unknown_category():
    result = _to_analysis(
        {
            "is_news": True,
            "title": "X",
            "summary": "Y",
            "category": "CryptoXYZ",
            "importance_score": 11,
        }
    )
    assert result.category == "Other"
    assert result.importance_score == 10.0


@pytest.mark.asyncio
async def test_heuristic_search_answer():
    ai = HeuristicAIService()
    answer = await ai.answer_search(
        "NVIDIA",
        [(1, "NVIDIA GPU", "Новая архитектура")],
    )
    assert "NVIDIA" in answer.answer
    assert answer.used_news_ids == (1,)
