"""
Pluggable ports for filter / embeddings / clustering / summarization / search.

MVP uses local rule-based and sentence-transformers implementations.
Future AI providers implement the same protocols without changing callers.
"""

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True, slots=True)
class FilterResult:
    passed: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class SummaryResult:
    title: str
    summary: str
    category: str | None = None


@dataclass(slots=True)
class ClusterCandidate:
    news_id: int
    title: str
    summary: str
    embedding: Sequence[float] | None = None


@dataclass(frozen=True, slots=True)
class ClusterResult:
    news_id: int | None
    """Existing news id to attach to, or None to create a new cluster."""
    similarity: float = 0.0
    is_new: bool = True


@dataclass(frozen=True, slots=True)
class SearchHit:
    news_id: int
    score: float
    title: str
    summary: str


class FilterPort(Protocol):
    def evaluate(self, text: str) -> FilterResult:
        """Return whether the message should enter the news pipeline."""
        ...


class EmbeddingPort(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        ...

    def embed_one(self, text: str) -> list[float]:
        ...


class ClusterPort(Protocol):
    def assign(
        self,
        text: str,
        embedding: Sequence[float],
        candidates: Sequence[ClusterCandidate],
        threshold: float,
    ) -> ClusterResult:
        ...


class SummarizerPort(Protocol):
    def summarize(self, texts: Sequence[str], *, channel_titles: Sequence[str] | None = None) -> SummaryResult:
        ...


class SearchPort(Protocol):
    async def search(self, query: str, *, limit: int = 10) -> list[SearchHit]:
        ...


class ScorerPort(Protocol):
    def score(
        self,
        *,
        source_count: int,
        text: str,
        published_at_timestamps: Sequence[float],
        now_timestamp: float,
    ) -> float:
        """Return importance_score in range 0..10."""
        ...
