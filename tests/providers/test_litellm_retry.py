from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx

from clawlite.providers.litellm import LiteLLMProvider


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://api.example/v1/chat/completions")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("err", request=request, response=response)

    def json(self) -> dict:
        return self._payload


def test_litellm_provider_retries_429_then_success(monkeypatch) -> None:
    async def _scenario() -> None:
        provider = LiteLLMProvider(base_url="https://api.example/v1", api_key="k", model="gpt-test")
        monkeypatch.setenv("CLAWLITE_PROVIDER_429_MAX_ATTEMPTS", "3")
        monkeypatch.setenv("CLAWLITE_PROVIDER_429_WAIT_SECONDS", "0")

        responses = [
            _FakeResponse(429, {}),
            _FakeResponse(429, {}),
            _FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]}),
        ]

        post_mock = AsyncMock(side_effect=responses)
        with patch("httpx.AsyncClient.post", new=post_mock):
            out = await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])

        assert out.text == "ok"
        assert post_mock.call_count == 3

    asyncio.run(_scenario())


def test_litellm_provider_http_error_keeps_provider_message(monkeypatch) -> None:
    async def _scenario() -> None:
        provider = LiteLLMProvider(base_url="https://api.example/v1", api_key="k", model="gpt-test")
        monkeypatch.setenv("CLAWLITE_PROVIDER_429_MAX_ATTEMPTS", "1")

        class _BadResponse(_FakeResponse):
            def __init__(self) -> None:
                super().__init__(400, {"error": {"message": "invalid model"}})

            def raise_for_status(self) -> None:
                request = httpx.Request("POST", "https://api.example/v1/chat/completions")
                response = httpx.Response(400, request=request, json={"error": {"message": "invalid model"}})
                raise httpx.HTTPStatusError("err", request=request, response=response)

        post_mock = AsyncMock(side_effect=[_BadResponse()])
        with patch("httpx.AsyncClient.post", new=post_mock):
            try:
                await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])
            except RuntimeError as exc:
                message = str(exc)
                assert message.startswith("provider_http_error:400:")
                assert "invalid model" in message
                return
            raise AssertionError("expected provider error")

    asyncio.run(_scenario())


def test_litellm_provider_parses_tool_calls(monkeypatch) -> None:
    async def _scenario() -> None:
        provider = LiteLLMProvider(base_url="https://api.example/v1", api_key="k", model="gpt-test")
        monkeypatch.setenv("CLAWLITE_PROVIDER_429_MAX_ATTEMPTS", "1")

        payload = {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_123",
                                "type": "function",
                                "function": {
                                    "name": "cron",
                                    "arguments": "{\"action\":\"add\",\"expression\":\"every 60\",\"prompt\":\"ping\"}",
                                },
                            }
                        ],
                    }
                }
            ]
        }

        post_mock = AsyncMock(side_effect=[_FakeResponse(200, payload)])
        with patch("httpx.AsyncClient.post", new=post_mock):
            out = await provider.complete(messages=[{"role": "user", "content": "agende"}], tools=[])

        assert len(out.tool_calls) == 1
        call = out.tool_calls[0]
        assert call.id == "call_123"
        assert call.name == "cron"
        assert call.arguments == {"action": "add", "expression": "every 60", "prompt": "ping"}

    asyncio.run(_scenario())
