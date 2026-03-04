from __future__ import annotations

import asyncio
import json

from clawlite.providers.base import LLMResult
from clawlite.providers.failover import FailoverProvider


class _Provider:
    def __init__(self, *, result: str = "", error: str = "") -> None:
        self.result = result
        self.error = error
        self.calls = 0

    async def complete(self, *, messages, tools, max_tokens=None, temperature=None, reasoning_effort=None):
        self.calls += 1
        if self.error:
            raise RuntimeError(self.error)
        return LLMResult(text=self.result, model="test/model", tool_calls=[], metadata={"provider": "test"})

    def get_default_model(self) -> str:
        return "test/model"

    def diagnostics(self) -> dict[str, object]:
        return {
            "provider": "test",
            "model": "test/model",
            "token": "raw-secret-token",
            "counters": {"requests": self.calls},
        }


def test_failover_provider_uses_fallback_for_retryable_primary_failure() -> None:
    async def _scenario() -> None:
        primary = _Provider(error="provider_http_error:503:temporary")
        fallback = _Provider(result="from fallback")
        provider = FailoverProvider(primary=primary, fallback=fallback, fallback_model="openai/gpt-4.1-mini")

        out = await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])

        assert out.text == "from fallback"
        assert out.metadata["fallback_used"] is True
        assert out.metadata["fallback_model"] == "openai/gpt-4.1-mini"
        diag = provider.diagnostics()
        assert diag["fallback_attempts"] == 1
        assert diag["fallback_success"] == 1
        assert diag["fallback_failures"] == 0

    asyncio.run(_scenario())


def test_failover_provider_does_not_use_fallback_for_non_retryable_error() -> None:
    async def _scenario() -> None:
        primary = _Provider(error="provider_auth_error:missing_api_key:openai")
        fallback = _Provider(result="from fallback")
        provider = FailoverProvider(primary=primary, fallback=fallback, fallback_model="openai/gpt-4.1-mini")

        try:
            await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])
        except RuntimeError as exc:
            assert str(exc).startswith("provider_auth_error")
        else:
            raise AssertionError("expected auth error")

        assert fallback.calls == 0

    asyncio.run(_scenario())


def test_failover_provider_tracks_fallback_failures() -> None:
    async def _scenario() -> None:
        primary = _Provider(error="provider_network_error:timeout")
        fallback = _Provider(error="provider_http_error:503")
        provider = FailoverProvider(primary=primary, fallback=fallback, fallback_model="openai/gpt-4.1-mini")

        try:
            await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])
        except RuntimeError as exc:
            assert str(exc).startswith("provider_http_error:503")
        else:
            raise AssertionError("expected fallback failure")

        diag = provider.diagnostics()
        assert diag["fallback_attempts"] == 1
        assert diag["fallback_success"] == 0
        assert diag["fallback_failures"] == 1

    asyncio.run(_scenario())


def test_failover_provider_diagnostics_contract_and_secret_safety() -> None:
    primary = _Provider(result="p")
    fallback = _Provider(result="f")
    provider = FailoverProvider(primary=primary, fallback=fallback, fallback_model="openai/gpt-4.1-mini")
    diag = provider.diagnostics()
    assert diag["provider"] == "failover"
    assert diag["provider_name"] == "failover"
    assert diag["fallback_model"] == "openai/gpt-4.1-mini"
    assert isinstance(diag["counters"], dict)
    assert "primary" in diag
    assert "fallback" in diag
    assert "token" not in diag["primary"]
    assert "token" not in diag["fallback"]
    encoded = json.dumps(diag).lower()
    assert "raw-secret-token" not in encoded
