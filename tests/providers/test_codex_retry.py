from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx

from clawlite.providers.codex import CodexProvider


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = dict(headers or {})

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
            response = httpx.Response(self.status_code, request=request, headers=self.headers)
            raise httpx.HTTPStatusError("err", request=request, response=response)

    def json(self) -> dict:
        return self._payload


def test_codex_provider_retries_5xx_then_success() -> None:
    async def _scenario() -> None:
        provider = CodexProvider(
            model="codex-5.3",
            access_token="token",
            retry_max_attempts=3,
            retry_initial_backoff_s=0,
            retry_max_backoff_s=0,
            retry_jitter_s=0,
        )

        post_mock = AsyncMock(
            side_effect=[
                _FakeResponse(503, {}),
                _FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]}),
            ]
        )
        with patch("httpx.AsyncClient.post", new=post_mock):
            out = await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])

        assert out.text == "ok"
        assert post_mock.call_count == 2
        diag = provider.diagnostics()
        assert diag["retries"] == 1
        assert diag["http_errors"] == 1

    asyncio.run(_scenario())


def test_codex_provider_retries_429_with_retry_after() -> None:
    async def _scenario() -> None:
        provider = CodexProvider(model="codex-5.3", access_token="token", retry_max_attempts=2)

        post_mock = AsyncMock(
            side_effect=[
                _FakeResponse(429, {}, headers={"retry-after": "0.4"}),
                _FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]}),
            ]
        )
        sleep_mock = AsyncMock()
        with patch("httpx.AsyncClient.post", new=post_mock), patch("asyncio.sleep", new=sleep_mock):
            out = await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])

        assert out.text == "ok"
        assert sleep_mock.await_count == 1
        assert sleep_mock.await_args.args[0] == 0.4

    asyncio.run(_scenario())


def test_codex_provider_circuit_opens_then_cooldown_closes() -> None:
    async def _scenario() -> None:
        provider = CodexProvider(
            model="codex-5.3",
            access_token="token",
            retry_max_attempts=1,
            circuit_failure_threshold=2,
            circuit_cooldown_s=30.0,
        )
        post_mock = AsyncMock(side_effect=[_FakeResponse(500, {}), _FakeResponse(500, {})])

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
                assert str(exc) == "provider_circuit_open:codex:30.0"
            else:
                raise AssertionError("expected circuit-open error")

            now[0] = 100.0
            post_mock.side_effect = [_FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]})]
            out = await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])
            assert out.text == "ok"

        diag = provider.diagnostics()
        assert diag["circuit_open_count"] == 1
        assert diag["circuit_close_count"] == 1

    asyncio.run(_scenario())


def test_codex_provider_passes_reasoning_effort() -> None:
    async def _scenario() -> None:
        provider = CodexProvider(model="codex-5.3", access_token="token", retry_max_attempts=1)

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


def test_codex_provider_parses_tool_calls_from_response() -> None:
    async def _scenario() -> None:
        provider = CodexProvider(model="codex-5.3", access_token="token", retry_max_attempts=1)

        post_mock = AsyncMock(
            side_effect=[
                _FakeResponse(
                    200,
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": "",
                                    "tool_calls": [
                                        {
                                            "id": "call_123",
                                            "type": "function",
                                            "function": {
                                                "name": "lookup_user",
                                                "arguments": '{"user_id": 42}',
                                            },
                                        }
                                    ],
                                }
                            }
                        ]
                    },
                )
            ]
        )
        with patch("httpx.AsyncClient.post", new=post_mock):
            out = await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])

        assert len(out.tool_calls) == 1
        assert out.tool_calls[0].id == "call_123"
        assert out.tool_calls[0].name == "lookup_user"
        assert out.tool_calls[0].arguments == {"user_id": 42}

    asyncio.run(_scenario())


def test_codex_provider_classifies_auth_failure() -> None:
    async def _scenario() -> None:
        provider = CodexProvider(model="codex-5.3", access_token="", retry_max_attempts=1)
        try:
            await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])
        except RuntimeError as exc:
            assert str(exc) == "codex_auth_error:missing_access_token"
        else:
            raise AssertionError("expected auth error")

        diag = provider.diagnostics()
        assert diag["last_error_class"] == "auth"
        assert diag["error_class_counts"]["auth"] == 1

    asyncio.run(_scenario())


def test_codex_provider_diagnostics_contract_and_secret_safety() -> None:
    provider = CodexProvider(model="codex-5.3", access_token="test_access_token_value", account_id="org-abc")
    diag = provider.diagnostics()
    assert diag["provider"] == "codex"
    assert diag["provider_name"] == "openai_codex"
    assert diag["model"] == "codex-5.3"
    assert isinstance(diag["counters"], dict)
    assert "requests" in diag["counters"]
    assert "last_error_class" in diag["counters"]
    assert isinstance(diag["counters"]["error_class_counts"], dict)
    encoded = json.dumps(diag).lower()
    assert "access_token" not in encoded
    assert "test_access_token_value" not in encoded
