"""Tests for AI manager key rotation and backfill progress."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.models.backfill_job import BackfillJob
from app.services.ai.manager import AIManager, _KeySlot
from app.services.ai.openai_compat import AIProviderError, parse_key_list


def test_parse_key_list_merges_legacy_and_pool():
    keys = parse_key_list("a,b", "c", "a")
    assert keys == ["a", "b", "c"]


class _FailOnce:
    provider_name = "mock_fail"

    def __init__(self) -> None:
        self.calls = 0

    async def classify_news(self, text, **kwargs):
        self.calls += 1
        raise AIProviderError("rate", status_code=429, retryable=True, error_code="rate_limit")

    async def close(self):
        return None


class _AlwaysOk:
    provider_name = "mock_ok"

    def __init__(self) -> None:
        self.calls = 0

    async def classify_news(self, text, **kwargs):
        self.calls += 1
        from app.services.ai.base import AnalyzedPost, CallMeta, PostAnalysisResult

        return AnalyzedPost(
            result=PostAnalysisResult(
                is_news=True,
                is_advertisement=False,
                title="ok",
                summary="s",
                category="technology",
                topic="t",
            ),
            meta=CallMeta(provider="mock_ok", status="ok", operation="analyze"),
        )

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_manager_rotates_on_429():
    bad = _FailOnce()
    good = _AlwaysOk()
    mgr = AIManager(
        groq_slots=[_KeySlot(bad), _KeySlot(good)],
        kimi_slots=[],
    )
    result = await mgr.analyze_post("hello world news about chips")
    assert result.title == "ok"
    assert bad.calls == 1
    assert good.calls == 1
    assert mgr.last_meta is not None
    assert mgr.last_meta.provider == "mock_ok"


def test_backfill_percent_stage_weighted():
    job = BackfillJob(
        user_id=1,
        days=2,
        status="analyzing",
        channel_ids=[1, 2],
        done_channel_ids=[1, 2],
        current_stage="ai",
        total_tasks=100,
        completed_tasks=50,
        messages_fetched=100,
        messages_total=100,
    )
    pct = job.percent
    # fetch(25)+clean(10)+dedupe(5)=40 base, ai weight 40 * 0.5 = 20 → ~60
    assert 55 <= pct <= 65
    job.status = "done"
    job.current_stage = "done"
    assert job.percent == 100
