"""Unified embedding access for the Event pipeline."""

from __future__ import annotations

from app.config import get_settings
from app.services.clustering import HashingEmbedding, get_default_embedding
from app.services.ports import EmbeddingPort


def build_embedding() -> EmbeddingPort:
    settings = get_settings()
    backend = (settings.embedding_backend or "hashing").strip().lower()
    if backend in {"hashing", "hash", "local"}:
        return HashingEmbedding()
    if backend in {"sentence-transformers", "st", "transformer"}:
        try:
            emb = get_default_embedding(settings.embedding_model, prefer_transformer=True)
            if hasattr(emb, "_load"):
                emb._load()  # type: ignore[attr-defined]
            return emb
        except Exception:
            return HashingEmbedding()
    try:
        emb = get_default_embedding(settings.embedding_model, prefer_transformer=True)
        if hasattr(emb, "_load"):
            emb._load()  # type: ignore[attr-defined]
        return emb
    except Exception:
        return HashingEmbedding()


class EmbeddingService:
    def __init__(self, port: EmbeddingPort | None = None) -> None:
        self._port = port or build_embedding()

    @property
    def port(self) -> EmbeddingPort:
        return self._port

    def embed(self, text: str) -> list[float]:
        return list(self._port.embed_one(text))
