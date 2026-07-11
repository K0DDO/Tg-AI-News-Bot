"""Cosine-similarity clustering (implements ClusterPort)."""

from __future__ import annotations

from typing import Sequence

import numpy as np

from app.services.ports import ClusterCandidate, ClusterResult


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


class CosineClusterer:
    def assign(
        self,
        text: str,
        embedding: Sequence[float],
        candidates: Sequence[ClusterCandidate],
        threshold: float,
    ) -> ClusterResult:
        best_id: int | None = None
        best_sim = -1.0
        for candidate in candidates:
            if not candidate.embedding:
                continue
            sim = cosine_similarity(embedding, candidate.embedding)
            if sim > best_sim:
                best_sim = sim
                best_id = candidate.news_id
        if best_id is not None and best_sim >= threshold:
            return ClusterResult(news_id=best_id, similarity=best_sim, is_new=False)
        return ClusterResult(news_id=None, similarity=max(best_sim, 0.0), is_new=True)
