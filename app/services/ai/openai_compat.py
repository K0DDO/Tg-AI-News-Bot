"""Shared OpenAI-compatible chat client with usage metadata + retryable errors."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")


class AIProviderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        error_code: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.error_code = error_code or (f"http_{status_code}" if status_code else "error")


@dataclass(frozen=True, slots=True)
class ChatResult:
    content: str
    model: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int = 0
    key_fingerprint: str = ""
    raw: dict[str, Any] | None = None


def key_fingerprint(api_key: str) -> str:
    """Stable non-reversible id for logs (never store raw keys)."""
    digest = hashlib.sha256((api_key or "").encode("utf-8")).hexdigest()
    return digest[:12]


def parse_key_list(*values: str) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for raw in values:
        if not raw:
            continue
        for part in str(raw).replace("\n", ",").split(","):
            k = part.strip()
            if k and k not in seen:
                seen.add(k)
                keys.append(k)
    return keys


class OpenAICompatClient:
    """Minimal chat client used by Groq and Kimi (Moonshot)."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout: float = 45.0,
        provider_name: str = "openai",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._provider_name = provider_name
        self._fingerprint = key_fingerprint(api_key)
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    @property
    def model(self) -> str:
        return self._model

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    @property
    def provider_name(self) -> str:
        return self._provider_name

    async def chat(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": self._model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        started = time.perf_counter()
        try:
            response = await self._client.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise AIProviderError(
                f"{self._provider_name} timeout",
                retryable=True,
                error_code="timeout",
            ) from exc
        except httpx.TransportError as exc:
            raise AIProviderError(
                f"{self._provider_name} transport error",
                retryable=True,
                error_code="transport",
            ) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            code = response.status_code
            retryable = code == 429 or code >= 500
            err = "rate_limit" if code == 429 else f"http_{code}"
            logger.warning(
                "%s error %s key=%s: %s",
                self._provider_name,
                code,
                self._fingerprint,
                response.text[:300],
            )
            raise AIProviderError(
                f"{self._provider_name} HTTP {code}",
                status_code=code,
                retryable=retryable,
                error_code=err,
            )

        data = response.json()
        content = str(data["choices"][0]["message"]["content"] or "").strip()
        usage = data.get("usage") or {}
        tokens_in = usage.get("prompt_tokens")
        tokens_out = usage.get("completion_tokens")
        try:
            tokens_in = int(tokens_in) if tokens_in is not None else None
        except (TypeError, ValueError):
            tokens_in = None
        try:
            tokens_out = int(tokens_out) if tokens_out is not None else None
        except (TypeError, ValueError):
            tokens_out = None
        return ChatResult(
            content=content,
            model=str(data.get("model") or self._model),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            key_fingerprint=self._fingerprint,
            raw=data,
        )

    async def chat_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
    ) -> tuple[dict[str, Any], ChatResult]:
        result = await self.chat(
            system=system, user=user, temperature=temperature, json_mode=True
        )
        return _parse_json_content(result.content), result

    async def close(self) -> None:
        await self._client.aclose()


def _parse_json_content(content: str) -> dict[str, Any]:
    content = (content or "").strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(content)
        if not match:
            raise
        return json.loads(match.group(0))
