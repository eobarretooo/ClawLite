from __future__ import annotations

import os
import time
from typing import Any

import httpx

from clawlite.providers.base import LLMProvider, LLMResult


class CodexProvider(LLMProvider):
    def __init__(self, *, model: str, access_token: str, account_id: str, timeout: float = 30.0) -> None:
        self.model = model
        self.access_token = access_token
        self.account_id = account_id
        self.timeout = timeout
        self.base_url = os.getenv("CLAWLITE_CODEX_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    @staticmethod
    def _max_attempts() -> int:
        raw = os.getenv("CLAWLITE_CODEX_429_MAX_ATTEMPTS", "3").strip()
        try:
            value = int(raw)
        except ValueError:
            value = 3
        return max(1, value)

    @staticmethod
    def _wait_seconds() -> float:
        raw = os.getenv("CLAWLITE_CODEX_429_WAIT_SECONDS", "60").strip()
        try:
            value = float(raw)
        except ValueError:
            value = 60.0
        return max(0.0, value)

    async def complete(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResult:
        headers = {"content-type": "application/json"}
        if self.access_token:
            headers["authorization"] = f"Bearer {self.access_token}"
        if self.account_id:
            headers["openai-organization"] = self.account_id

        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = [{"type": "function", "function": row} for row in tools]
            payload["tool_choice"] = "auto"

        attempts = self._max_attempts()
        wait_seconds = self._wait_seconds()
        url = f"{self.base_url}/chat/completions"

        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                message = data.get("choices", [{}])[0].get("message", {})
                text = str(message.get("content", "")).strip()
                return LLMResult(text=text, model=self.model, tool_calls=[], metadata={"provider": "codex"})
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status == 429 and attempt < attempts:
                    time.sleep(wait_seconds)
                    continue
                raise RuntimeError(f"codex_http_error:{status}") from exc
            except httpx.RequestError as exc:
                raise RuntimeError(f"codex_network_error:{exc}") from exc

        raise RuntimeError("codex_429_exhausted")
