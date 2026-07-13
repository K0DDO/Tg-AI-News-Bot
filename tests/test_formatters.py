from decimal import Decimal

from app.models.event import Event, EventSource
from app.services.digest.formatters import format_news_card, format_sources_list


def test_format_news_card():
    news = Event(
        id=1,
        title="Test <b>Title</b>",
        summary="Summary & more",
        category="AI",
        importance_score=Decimal("8.5"),
    )
    news.sources = []
    text = format_news_card(news, source_count=3)
    assert "Test &lt;b&gt;Title&lt;/b&gt;" in text
    assert "8.5/10" in text or "8.0/10" in text or "9.0/10" in text
    assert "Источники: 3" in text


def test_format_sources_list():
    news = Event(id=1, title="Hello", summary="S", category="General", importance_score=Decimal("1"))
    news.sources = [
        EventSource(id=1, event_id=1, source_url="https://t.me/c/1/2", channel_title="Chan"),
    ]
    text = format_sources_list(news)
    assert "https://t.me/c/1/2" in text
    assert "Chan" in text
