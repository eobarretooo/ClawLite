from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx

from clawlite.providers.litellm import LiteLLMProvider


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = ""
        self.headers = dict(headers or {})

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://api.example/v1/chat/completions")
            response = httpx.Response(self.status_code, request=request, json=self._payload, headers=self.headers)
            raise httpx.HTTPStatusError("err", request=request, response=response)

    def json(self) -> dict:
        return self._payload


def test_litellm_provider_retries_transient_5xx_then_success() -> None:
    async def _scenario() -> None:
        provider = LiteLLMProvider(
            base_url="https://api.example/v1",
            api_key="k",
            model="gpt-test",
            retry_max_attempts=3,
            retry_initial_backoff_s=0,
            retry_max_backoff_s=0,
            retry_jitter_s=0,
        )

        responses = [
            _FakeResponse(502, {"error": {"message": "bad gateway"}}),
            _FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]}),
        ]
        post_mock = AsyncMock(side_effect=responses)
        with patch("httpx.AsyncClient.post", new=post_mock):
            out = await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])

        assert out.text == "ok"
        assert post_mock.call_count == 2
        diag = provider.diagnostics()
        assert diag["retries"] == 1
        assert diag["http_errors"] == 1
        assert diag["successes"] == 1

    asyncio.run(_scenario())


def test_litellm_provider_retry_after_header_overrides_backoff() -> None:
    async def _scenario() -> None:
        provider = LiteLLMProvider(
            base_url="https://api.example/v1",
            api_key="k",
            model="gpt-test",
            retry_max_attempts=2,
            retry_initial_backoff_s=0.01,
            retry_max_backoff_s=0.01,
            retry_jitter_s=0,
        )

        responses = [
            _FakeResponse(429, {"error": {"message": "rate limited"}}, headers={"retry-after": "0.25"}),
            _FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]}),
        ]

        post_mock = AsyncMock(side_effect=responses)
        sleep_mock = AsyncMock()
        with patch("httpx.AsyncClient.post", new=post_mock), patch("asyncio.sleep", new=sleep_mock):
            out = await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])

        assert out.text == "ok"
        assert sleep_mock.await_count == 1
        assert sleep_mock.await_args.args[0] == 0.25

    asyncio.run(_scenario())


def test_litellm_provider_quota_429_fails_fast_without_retry() -> None:
    async def _scenario() -> None:
        provider = LiteLLMProvider(base_url="https://api.example/v1", api_key="k", model="gpt-test", retry_max_attempts=5)
        post_mock = AsyncMock(
            side_effect=[
                _FakeResponse(
                    429,
                    {
                        "error": {
                            "message": "You exceeded your current quota, please check your plan and billing details.",
                            "code": "insufficient_quota",
                        }
                    },
                )
            ]
        )
        sleep_mock = AsyncMock()
        with patch("httpx.AsyncClient.post", new=post_mock), patch("asyncio.sleep", new=sleep_mock):
            try:
                await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])
            except RuntimeError as exc:
                message = str(exc)
                assert message.startswith("provider_http_error:429:")
                assert "quota" in message.lower()
            else:
                raise AssertionError("expected provider error")

        assert post_mock.call_count == 1
        sleep_mock.assert_not_called()

    asyncio.run(_scenario())


def test_litellm_provider_circuit_opens_then_closes_after_cooldown() -> None:
    async def _scenario() -> None:
        provider = LiteLLMProvider(
            base_url="https://api.example/v1",
            api_key="k",
            model="gpt-test",
            retry_max_attempts=1,
            circuit_failure_threshold=2,
            circuit_cooldown_s=30.0,
        )
        post_mock = AsyncMock(side_effect=[_FakeResponse(500, {"error": {"message": "boom"}}), _FakeResponse(500, {"error": {"message": "boom"}})])

        now = [1.0]
        with patch("httpx.AsyncClient.post", new=post_mock), patch("time.monotonic", side_effect=lambda: now[0]):
            for _ in range(2):
                try:
                    await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])
                except RuntimeError:
                    pass

            try:
                await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])
            except RuntimeError as exc:
                assert str(exc) == "provider_circuit_open:litellm:30.0"
            else:
                raise AssertionError("expected circuit-open error")

            now[0] = 100.0
            post_mock.side_effect = [_FakeResponse(200, {"choices": [{"message": {"content": "recovered"}}]})]
            out = await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])
            assert out.text == "recovered"

        diag = provider.diagnostics()
        assert diag["circuit_open_count"] == 1
        assert diag["circuit_close_count"] == 1

    asyncio.run(_scenario())


def test_litellm_provider_parses_tool_calls() -> None:
    async def _scenario() -> None:
        provider = LiteLLMProvider(base_url="https://api.example/v1", api_key="k", model="gpt-test", retry_max_attempts=1)

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


def test_litellm_provider_passes_reasoning_effort_for_openai() -> None:
    async def _scenario() -> None:
        provider = LiteLLMProvider(base_url="https://api.example/v1", api_key="k", model="gpt-test", provider_name="openai", retry_max_attempts=1)

        post_mock = AsyncMock(side_effect=[_FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]})])
        with patch("httpx.AsyncClient.post", new=post_mock):
            await provider.complete(
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                reasoning_effort="high",
            )

        payload = post_mock.call_args.kwargs["json"]
        assert payload["reasoning_effort"] == "high"

    asyncio.run(_scenario())


def test_litellm_provider_diagnostics_contract_and_secret_safety() -> None:
    provider = LiteLLMProvider(
        base_url="https://api.example/v1",
        api_key="test_api_key_value",
        model="gpt-test",
        provider_name="openai",
    )
    diag = provider.diagnostics()
    assert diag["provider"] == "litellm"
    assert diag["provider_name"] == "openai"
    assert diag["model"] == "gpt-test"
    assert isinstance(diag["counters"], dict)
    assert "requests" in diag["counters"]
    encoded = json.dumps(diag).lower()
    assert "api_key" not in encoded
    assert "access_token" not in encoded
    assert "test_api_key_value" not in encoded
