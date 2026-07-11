"""Groq OpenAI-compatible chat completions client."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")


class GroqClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.groq.com/openai/v1",
        timeout: float = 45.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
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

    async def chat_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        payload = {
            "model": self._model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        response = await self._client.post("/chat/completions", json=payload)
        if response.status_code >= 400:
            logger.error("Groq error %s: %s", response.status_code, response.text[:500])
            response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return _parse_json_content(content)

    async def chat_text(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.3,
    ) -> str:
        payload = {
            "model": self._model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        response = await self._client.post("/chat/completions", json=payload)
        if response.status_code >= 400:
            logger.error("Groq error %s: %s", response.status_code, response.text[:500])
            response.raise_for_status()
        data = response.json()
        return str(data["choices"][0]["message"]["content"]).strip()

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
