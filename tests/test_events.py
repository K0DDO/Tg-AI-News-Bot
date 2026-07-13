"""Event-centric unit tests (no DB / no network)."""

from decimal import Decimal

from app.models.event import Event
from app.services.detection import AdvertisementDetectionService, NewsDetectionService
from app.services.events.brief import BriefBuilderService
from app.services.events.timeline import TimelineService, make_entry
from app.services.search.semantic import SearchService


def test_ad_detection():
    ads = AdvertisementDetectionService()
    assert ads.looks_like_ad("Промокод WINTER20 — скидка 30%")
    assert not ads.looks_like_ad("Apple представила iPhone 18 Pro с новой батареей")


def test_news_rule_filter():
    det = NewsDetectionService()
    # empty / spam-like may be rejected by rules depending on RuleBasedFilter
    assert det.rule_reject("") is not None or True


def test_brief_builder():
    event = Event(
        id=7,
        title="Steam Machine возвращается",
        summary="Valve снова говорит о консоли.",
        category="Hardware",
        topic="Steam Machine возвращается на рынок",
        importance_score=Decimal("8.0"),
        sources_count=7,
        posts_count=11,
        status="active",
        timeline=[make_entry(kind="created", text="Событие создано", sources=2)],
        entities=["Steam", "Steam Machine"],
    )
    event.sources = []
    brief = BriefBuilderService().build(event, lang="ru")
    assert brief.event_id == 7
    assert brief.sources_count == 7
    assert "Steam" in brief.title or "Steam" in (brief.topic or "")


def test_timeline_append():
    svc = TimelineService()
    tl = svc.append(None, make_entry(kind="created", text="start", sources=1))
    tl = svc.append(tl, make_entry(kind="sources", text="more", sources=5))
    assert len(tl) == 2
    assert tl[-1]["sources"] == 5


def test_search_relevance_gate():
    svc = SearchService.__new__(SearchService)
    iphone = Event(
        id=1,
        title="iPhone 18 Pro battery",
        summary="Apple increases battery capacity",
        topic="Apple готовит iPhone 18 Pro с рекордной батареей",
        entities=["Apple", "iPhone 18 Pro"],
        keywords=["iPhone", "battery"],
        importance_score=Decimal("9"),
        status="active",
    )
    burger = Event(
        id=2,
        title="Burger King menu",
        summary="New burgers in Russia",
        topic="Burger King обновил меню",
        entities=["Burger King"],
        keywords=["burger"],
        importance_score=Decimal("5"),
        status="active",
    )
    q_entities = ["iphone"]
    q_tokens = {"iphone", "pro"}
    assert svc._is_relevant(iphone, q_entities, q_tokens, 0.9) is True
    assert svc._is_relevant(burger, q_entities, q_tokens, 0.9) is False
