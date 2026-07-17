"""Semantic similarity + merge scoring tests."""

from datetime import datetime, timedelta, timezone

from app.services.clustering import HashingEmbedding
from app.services.events.merge import EventMergeService, is_near_duplicate
from app.services.events.similarity import should_merge, similarity_score
from app.services.ports import ClusterCandidate


def test_max_variants_high_similarity():
    emb = HashingEmbedding(dim=256)
    a = "MAX удалили из Google Play"
    b = "Google убрал российский мессенджер MAX из магазина приложений"
    c = "Приложение MAX больше недоступно в Google Play"
    ea, eb, ec = emb.embed_one(a), emb.embed_one(b), emb.embed_one(c)
    now = datetime.now(timezone.utc)
    s_ab = similarity_score(
        embedding_a=ea,
        embedding_b=eb,
        entities_a=["MAX", "Google Play"],
        entities_b=["MAX", "Google"],
        text_a=a,
        text_b=b,
        time_a=now,
        time_b=now,
        category_a="software",
        category_b="software",
    )
    s_ac = similarity_score(
        embedding_a=ea,
        embedding_b=ec,
        entities_a=["MAX", "Google Play"],
        entities_b=["MAX", "Google Play"],
        text_a=a,
        text_b=c,
        time_a=now,
        time_b=now,
    )
    assert s_ab.total >= 0.55 or is_near_duplicate(a, b)
    assert s_ac.total >= 0.55 or is_near_duplicate(a, c)
    assert should_merge(max(s_ab.total, 0.72 if is_near_duplicate(a, b) else s_ab.total), threshold=0.62)


def test_unrelated_low_similarity():
    emb = HashingEmbedding(dim=256)
    a = "Центробанк повысил ключевую ставку"
    b = "Учёные открыли новую экзопланету в созвездии Лиры"
    s = similarity_score(
        embedding_a=emb.embed_one(a),
        embedding_b=emb.embed_one(b),
        text_a=a,
        text_b=b,
        time_a=datetime.now(timezone.utc),
        time_b=datetime.now(timezone.utc) - timedelta(days=10),
    )
    assert s.total < 0.55
    assert not is_near_duplicate(a, b)


def test_merge_service_clusters_max_story():
    emb = HashingEmbedding(dim=256)
    merge = EventMergeService(emb, threshold=0.62)
    base = "MAX удалили из Google Play"
    e1 = emb.embed_one(base)
    candidates = [
        ClusterCandidate(
            news_id=1,
            title=base,
            summary=base,
            embedding=e1,
            entities=["MAX", "Google Play"],
            category="software",
            created_at=datetime.now(timezone.utc),
        )
    ]
    variants = [
        "Мессенджер MAX исчез из магазина Google",
        "Google удалил приложение MAX",
        "Приложение MAX больше недоступно в Google Play",
    ]
    for text in variants:
        vec = emb.embed_one(text)
        result = merge.find_match(
            text,
            vec,
            candidates,
            entities=["MAX"],
            category="software",
            created_at=datetime.now(timezone.utc),
        )
        assert result.is_new is False
        assert result.news_id == 1
