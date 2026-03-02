from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx

from clawlite.providers.codex import CodexProvider


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("err", request=request, response=response)

    def json(self) -> dict:
        return self._payload


def test_codex_provider_retries_429_with_async_sleep(monkeypatch) -> None:
    async def _scenario() -> None:
        monkeypatch.setenv("CLAWLITE_CODEX_429_MAX_ATTEMPTS", "2")
        monkeypatch.setenv("CLAWLITE_CODEX_429_WAIT_SECONDS", "0")
        provider = CodexProvider(model="codex-5.3", access_token="token")

        post_mock = AsyncMock(
            side_effect=[
                _FakeResponse(429, {}),
                _FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]}),
            ]
        )
        with patch("httpx.AsyncClient.post", new=post_mock):
            out = await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])

        assert out.text == "ok"
        assert post_mock.call_count == 2

    asyncio.run(_scenario())


def test_codex_provider_passes_reasoning_effort(monkeypatch) -> None:
    async def _scenario() -> None:
        monkeypatch.setenv("CLAWLITE_CODEX_429_MAX_ATTEMPTS", "1")
        provider = CodexProvider(model="codex-5.3", access_token="token")

        post_mock = AsyncMock(side_effect=[_FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]})])
        with patch("httpx.AsyncClient.post", new=post_mock):
            await provider.complete(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                reasoning_effort="medium",
            )

        payload = post_mock.call_args.kwargs["json"]
        assert payload["reasoning_effort"] == "medium"

    asyncio.run(_scenario())
