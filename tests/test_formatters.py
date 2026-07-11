from app.services.digest.formatters import format_news_card, format_sources_list
from app.models.news import News, NewsSource
from decimal import Decimal


def test_format_news_card():
    news = News(
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
    news = News(id=1, title="Hello", summary="S", category="General", importance_score=Decimal("1"))
    news.sources = [
        NewsSource(id=1, news_id=1, source_url="https://t.me/c/1/2", channel_title="Chan"),
    ]
    text = format_sources_list(news)
    assert "https://t.me/c/1/2" in text
    assert "Chan" in text
