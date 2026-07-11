"""Local embedding providers (sentence-transformers + lightweight fallback)."""

from __future__ import annotations

import hashlib
import logging
import re
from functools import lru_cache
from typing import Sequence

import numpy as np

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


class HashingEmbedding:
    """Fast bag-of-tokens hashing trick — no model download. Good for tests/MVP fallback."""

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]

    def embed_one(self, text: str) -> list[float]:
        vec = np.zeros(self.dim, dtype=np.float32)
        tokens = _TOKEN_RE.findall((text or "").lower())
        if not tokens:
            return vec.tolist()
        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).hexdigest()
            idx = int(digest[:8], 16) % self.dim
            sign = 1.0 if int(digest[8:10], 16) % 2 == 0 else -1.0
            vec[idx] += sign
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec.tolist()


class SentenceTransformerEmbedding:
    """Lazy sentence-transformers wrapper (implements EmbeddingPort)."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model %s", self._model_name)
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        model = self._load()
        vectors = model.encode(list(texts), normalize_embeddings=True)
        return [v.tolist() for v in vectors]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


@lru_cache
def get_default_embedding(model_name: str, *, prefer_transformer: bool = True):
    if prefer_transformer:
        try:
            return SentenceTransformerEmbedding(model_name)
        except Exception:
            logger.exception("Falling back to HashingEmbedding")
    return HashingEmbedding()
