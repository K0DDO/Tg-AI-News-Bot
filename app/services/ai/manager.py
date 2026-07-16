"""AIManager — routes ops, rotates keys, falls back to heuristic."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Sequence

from app.services.ai.base import (
    AIService,
    AnalyzedPost,
    AnsweredQuestion,
    CallMeta,
    PostAnalysisResult,
    SearchAnswer,
    TranslatedText,
    TranslationResult,
)
from app.services.ai.groq_provider import GroqProvider
from app.services.ai.heuristic import HeuristicAIService
from app.services.ai.kimi_provider import KimiProvider
from app.services.ai.openai_compat import AIProviderError

logger = logging.getLogger(__name__)

# Operations preferred on Groq (fast) vs Kimi (heavy)
_FAST_OPS = frozenset({"analyze", "classify", "summarize", "translate"})
_HEAVY_OPS = frozenset({"search", "merge", "relations"})


class _KeySlot:
    __slots__ = ("provider", "cooldown_until", "failures")

    def __init__(self, provider: GroqProvider | KimiProvider) -> None:
        self.provider = provider
        self.cooldown_until = 0.0
        self.failures = 0

    @property
    def available(self) -> bool:
        return time.monotonic() >= self.cooldown_until


class AIManager:
    """
    Unified AI facade. External code should not care which model answered.
    Implements AIService for drop-in compatibility.
    """

    provider_name = "manager"

    def __init__(
        self,
        *,
        groq_slots: list[_KeySlot] | None = None,
        kimi_slots: list[_KeySlot] | None = None,
        fallback: HeuristicAIService | None = None,
    ) -> None:
        self._groq = list(groq_slots or [])
        self._kimi = list(kimi_slots or [])
        self._fallback = fallback or HeuristicAIService()
        self._rr_groq = 0
        self._rr_kimi = 0
        self._lock = asyncio.Lock()
        self.last_meta: CallMeta | None = None
        # When all keys rate-limited — signal callers to defer
        self.keys_exhausted = False

    @property
    def groq_key_count(self) -> int:
        return len(self._groq)

    @property
    def kimi_key_count(self) -> int:
        return len(self._kimi)

    def status_snapshot(self) -> dict:
        now = time.monotonic()
        return {
            "groq_keys": len(self._groq),
            "kimi_keys": len(self._kimi),
            "groq_available": sum(1 for s in self._groq if s.cooldown_until <= now),
            "kimi_available": sum(1 for s in self._kimi if s.cooldown_until <= now),
            "keys_exhausted": self.keys_exhausted,
        }

    async def analyze_post(
        self,
        text: str,
        *,
        source_count: int = 1,
        channel_title: str | None = None,
    ) -> PostAnalysisResult:
        wrapped = await self._run_fast(
            "analyze",
            lambda p: p.classify_news(
                text, source_count=source_count, channel_title=channel_title
            ),
        )
        if wrapped is not None:
            self.last_meta = wrapped.meta
            return wrapped.result
        result = await self._fallback.analyze_post(
            text, source_count=source_count, channel_title=channel_title
        )
        self.last_meta = CallMeta(provider="heuristic", status="fallback", operation="analyze")
        return result

    async def answer_question(
        self,
        query: str,
        contexts: Sequence[tuple[int, str, str]],
    ) -> SearchAnswer:
        if not contexts:
            self.last_meta = CallMeta(provider="none", status="ok", operation="search")
            return SearchAnswer(
                answer="По вашему запросу релевантных новостей найдено не было.",
                used_event_ids=(),
                relevant=False,
            )
        wrapped = await self._run_heavy(
            "search",
            lambda p: p.search_answer(query, contexts),
        )
        if wrapped is not None:
            self.last_meta = wrapped.meta
            return wrapped.result
        result = await self._fallback.answer_question(query, contexts)
        self.last_meta = CallMeta(provider="heuristic", status="fallback", operation="search")
        return result

    async def translate(
        self,
        *,
        title: str,
        summary: str,
        target_lang: str,
    ) -> TranslationResult:
        wrapped = await self._run_fast(
            "translate",
            lambda p: p.translate_news(title=title, summary=summary, target_lang=target_lang),
        )
        if wrapped is not None:
            self.last_meta = wrapped.meta
            return wrapped.result
        result = await self._fallback.translate(
            title=title, summary=summary, target_lang=target_lang
        )
        self.last_meta = CallMeta(provider="heuristic", status="fallback", operation="translate")
        return result

    async def detect_language(self, text: str) -> str:
        return await self._fallback.detect_language(text)

    async def analyze_message(self, text: str, *, source_count: int = 1, channel_title: str | None = None):
        return await self.analyze_post(text, source_count=source_count, channel_title=channel_title)

    async def answer_search(self, query: str, contexts: Sequence[tuple[int, str, str]]):
        return await self.answer_question(query, contexts)

    async def translate_news(self, *, title: str, summary: str, target_lang: str):
        return await self.translate(title=title, summary=summary, target_lang=target_lang)

    async def merge_news(
        self, query: str, contexts: Sequence[tuple[int, str, str]]
    ) -> SearchAnswer:
        wrapped = await self._run_heavy("merge", lambda p: p.merge_news(query, contexts))
        if wrapped is not None:
            self.last_meta = wrapped.meta
            return wrapped.result
        return await self.answer_question(query, contexts)

    async def analyze_relations(
        self, query: str, contexts: Sequence[tuple[int, str, str]]
    ) -> SearchAnswer:
        wrapped = await self._run_heavy(
            "relations", lambda p: p.analyze_relations(query, contexts)
        )
        if wrapped is not None:
            self.last_meta = wrapped.meta
            return wrapped.result
        return await self.answer_question(query, contexts)

    async def _run_fast(self, op: str, call):
        # Prefer Groq, then Kimi, then None
        order = [self._groq, self._kimi]
        return await self._try_pools(order, call)

    async def _run_heavy(self, op: str, call):
        # Prefer Kimi, then Groq
        order = [self._kimi, self._groq]
        return await self._try_pools(order, call)

    async def _try_pools(self, pools: list[list[_KeySlot]], call):
        self.keys_exhausted = False
        tried = 0
        for pool in pools:
            if not pool:
                continue
            n = len(pool)
            start = self._rr_groq if pool is self._groq else self._rr_kimi
            for i in range(n):
                idx = (start + i) % n
                slot = pool[idx]
                if not slot.available:
                    continue
                tried += 1
                try:
                    result = await call(slot.provider)
                    slot.failures = 0
                    if pool is self._groq:
                        self._rr_groq = (idx + 1) % n
                    else:
                        self._rr_kimi = (idx + 1) % n
                    return result
                except AIProviderError as exc:
                    if exc.retryable:
                        # Cool down this key (429 → 30s, 5xx → 10s)
                        cool = 30.0 if exc.status_code == 429 else 10.0
                        slot.cooldown_until = time.monotonic() + cool
                        slot.failures += 1
                        logger.warning(
                            "AI key cooldown provider=%s err=%s cool=%.0fs",
                            getattr(slot.provider, "provider_name", "?"),
                            exc.error_code,
                            cool,
                        )
                        continue
                    logger.exception("AI non-retryable error")
                    break
                except Exception:
                    logger.exception("AI provider unexpected failure")
                    slot.cooldown_until = time.monotonic() + 5.0
                    continue
        if tried == 0 or all(
            (not s.available) for pool in pools for s in pool
        ):
            self.keys_exhausted = bool(any(pools))
        return None

    async def close(self) -> None:
        for slot in self._groq + self._kimi:
            try:
                await slot.provider.close()
            except Exception:
                pass


def build_manager_from_settings(settings) -> AIManager:
    from app.services.ai.openai_compat import OpenAICompatClient, parse_key_list

    groq_keys = parse_key_list(
        getattr(settings, "groq_api_keys", "") or "",
        getattr(settings, "groq_api_key", "") or "",
    )
    kimi_keys = parse_key_list(getattr(settings, "kimi_api_keys", "") or "")

    groq_slots: list[_KeySlot] = []
    for key in groq_keys:
        client = OpenAICompatClient(
            api_key=key,
            model=settings.groq_model,
            base_url=settings.groq_base_url,
            timeout=settings.groq_timeout_seconds,
            provider_name="groq",
        )
        groq_slots.append(_KeySlot(GroqProvider(client)))

    kimi_slots: list[_KeySlot] = []
    kimi_base = getattr(settings, "kimi_base_url", "") or "https://api.moonshot.ai/v1"
    kimi_model = getattr(settings, "kimi_model", "") or "moonshot-v1-8k"
    kimi_timeout = float(getattr(settings, "kimi_timeout_seconds", 60.0) or 60.0)
    for key in kimi_keys:
        client = OpenAICompatClient(
            api_key=key,
            model=kimi_model,
            base_url=kimi_base,
            timeout=kimi_timeout,
            provider_name="kimi",
        )
        kimi_slots.append(_KeySlot(KimiProvider(client)))

    return AIManager(groq_slots=groq_slots, kimi_slots=kimi_slots)
