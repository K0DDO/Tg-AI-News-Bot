from app.services.clustering import CosineClusterer, HashingEmbedding, cosine_similarity
from app.services.ports import ClusterCandidate


def test_cosine_identical():
    v = [1.0, 0.0, 0.0]
    assert cosine_similarity(v, v) == 1.0


def test_hashing_embedding_stable():
    emb = HashingEmbedding(dim=64)
    a = emb.embed_one("Apple представила новый MacBook")
    b = emb.embed_one("Apple представила новый MacBook")
    assert a == b
    assert abs(sum(x * x for x in a) - 1.0) < 1e-3


def test_cluster_merges_similar():
    emb = HashingEmbedding(dim=128)
    clusterer = CosineClusterer()
    text1 = "Apple представила новый MacBook Pro с чипом M4"
    text2 = "Новый MacBook Pro получил новый чип от Apple"
    e1 = emb.embed_one(text1)
    e2 = emb.embed_one(text2)
    candidates = [
        ClusterCandidate(news_id=1, title=text1, summary=text1, embedding=e1),
    ]
    # Lower threshold for hashing embeddings which are noisier than transformers
    result = clusterer.assign(text2, e2, candidates, threshold=0.2)
    assert result.is_new is False
    assert result.news_id == 1


def test_cluster_creates_new_for_unrelated():
    emb = HashingEmbedding(dim=128)
    clusterer = CosineClusterer()
    text1 = "Центробанк повысил ключевую ставку"
    text2 = "Учёные открыли новую экзопланету в созвездии Лиры"
    e1 = emb.embed_one(text1)
    e2 = emb.embed_one(text2)
    candidates = [
        ClusterCandidate(news_id=1, title=text1, summary=text1, embedding=e1),
    ]
    result = clusterer.assign(text2, e2, candidates, threshold=0.85)
    assert result.is_new is True
