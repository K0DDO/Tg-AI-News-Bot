"""Dedup scenario: 20 posts → ~7-10 unique stories."""

from __future__ import annotations

from app.services.clustering import HashingEmbedding
from app.services.events.merge import EventMergeService, is_near_duplicate
from app.services.ports import ClusterCandidate
from app.services.preferences import FeedService


def _cluster_texts(texts: list[str], *, threshold: float = 0.85) -> list[str]:
    emb = HashingEmbedding(dim=256)
    merge = EventMergeService(emb, threshold=threshold)
    representatives: list[str] = []
    candidates: list[ClusterCandidate] = []
    next_id = 1
    for text in texts:
        vector = emb.embed_one(text)
        match = merge.find_match(text, vector, candidates)
        if match.is_new or match.news_id is None:
            candidates.append(
                ClusterCandidate(
                    news_id=next_id,
                    title=text,
                    summary=text,
                    embedding=vector,
                )
            )
            representatives.append(text)
            next_id += 1
        else:
            # soft confirm near-dupe against chosen representative
            chosen = next(c for c in candidates if c.news_id == match.news_id)
            assert is_near_duplicate(text, f"{chosen.title}\n{chosen.summary}") or match.similarity >= 0.2
    return representatives


def test_max_play_store_variants_merge():
    variants = [
        "MAX удалили из Google Play",
        "Мессенджер MAX исчез из магазина Google",
        "Google удалил приложение MAX",
        "Приложение MAX больше недоступно в Google Play",
        "MAX убрали из Play Store",
    ]
    unique = _cluster_texts(variants)
    assert len(unique) == 1


def test_twenty_posts_collapse_to_unique_set():
    event_a = [
        "MAX удалили из Google Play",
        "Мессенджер MAX исчез из магазина Google",
        "Google удалил приложение MAX",
        "Приложение MAX больше недоступно в Google Play",
        "MAX убрали из Play Store",
    ]
    event_b = [
        "Apple представила новый MacBook Pro с чипом M4",
        "Новый MacBook Pro получил чип M4 от Apple",
        "Apple анонсировала MacBook Pro на M4",
        "MacBook Pro M4 выходит в продажу",
        "Apple показала обновлённый MacBook Pro M4",
    ]
    unique_news = [
        "Центробанк повысил ключевую ставку",
        "Учёные открыли новую экзопланету",
        "Valve анонсировала Steam Machine",
        "Открыта вакансия Python-разработчика",
        "NASA запустила новый телескоп",
        "Стартап привлёк $50M на IPO",
        "NVIDIA представила новый GPU",
        "Pixel 11 Pro Fold получит новый дизайн",
        "Евросоюз ввёл санкции против компаний",
        "Сегодня в городе прошёл марафон",
    ]
    texts = event_a + event_b + unique_news
    assert len(texts) == 20
    unique = _cluster_texts(texts)
    # 2 clustered events + 10 unique ≈ 12; allow some hashing noise
    assert 7 <= len(unique) <= 14


def test_feed_collapse_near_duplicates():
    class _E:
        def __init__(self, title: str, summary: str = "", sources: int = 1):
            self.title = title
            self.summary = summary
            self.sources_count = sources

    events = [
        _E("MAX удалили из Google Play", sources=1),
        _E("Google удалил приложение MAX", sources=3),
        _E("Учёные открыли новую экзопланету", sources=1),
    ]
    kept = FeedService._collapse_near_duplicates(events)  # type: ignore[arg-type]
    assert len(kept) == 2
    assert kept[0].sources_count == 3


def test_timezone_format_local():
    from datetime import datetime, timezone

    from app.services.time_prefs import format_local

    dt = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
    assert format_local(dt, "Europe/Moscow", fmt="%d.%m %H:%M") == "16.07 15:00"
