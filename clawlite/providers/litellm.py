from __future__ import annotations

import os
import time
from typing import Any

import httpx

from clawlite.providers.base import LLMProvider, LLMResult


class LiteLLMProvider(LLMProvider):
    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @staticmethod
    def _max_attempts() -> int:
        raw = os.getenv("CLAWLITE_PROVIDER_429_MAX_ATTEMPTS", "3").strip()
        try:
            value = int(raw)
        except ValueError:
            value = 3
        return max(1, value)

    @staticmethod
    def _wait_seconds() -> float:
        raw = os.getenv("CLAWLITE_PROVIDER_429_WAIT_SECONDS", "60").strip()
        try:
            value = float(raw)
        except ValueError:
            value = 60.0
        return max(0.0, value)

    async def complete(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResult:
        url = f"{self.base_url}/chat/completions"
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": row} for row in tools]
            payload["tool_choice"] = "auto"

        attempts = self._max_attempts()
        wait_seconds = self._wait_seconds()

        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                message = data.get("choices", [{}])[0].get("message", {})
                text = str(message.get("content", "")).strip()
                return LLMResult(text=text, model=self.model, tool_calls=[], metadata={"provider": "litellm"})
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status == 429 and attempt < attempts:
                    time.sleep(wait_seconds)
                    continue
                raise RuntimeError(f"provider_http_error:{status}") from exc
            except httpx.RequestError as exc:
                raise RuntimeError(f"provider_network_error:{exc}") from exc

        raise RuntimeError("provider_429_exhausted")
