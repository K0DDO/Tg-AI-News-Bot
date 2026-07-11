import time

from app.services.scoring import HeuristicSummarizer, ImportanceScorer


def test_summarizer_title_and_category():
    s = HeuristicSummarizer()
    result = s.summarize(
        ["NVIDIA представила новую архитектуру GPU для обучения LLM моделей искусственного интеллекта"]
    )
    assert "NVIDIA" in result.title or "GPU" in result.title or "LLM" in result.title
    assert result.category in {"AI", "Hardware", "Technology"}
    assert len(result.summary) > 0


def test_importance_score_bounds():
    scorer = ImportanceScorer()
    now = time.time()
    score = scorer.score(
        source_count=5,
        text="Breaking: OpenAI and Microsoft announce new AI release",
        published_at_timestamps=[now - 3600],
        now_timestamp=now,
    )
    assert 0 <= score <= 10
    assert score >= 5
