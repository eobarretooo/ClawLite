from __future__ import annotations

import asyncio

from clawlite.providers.litellm import LiteLLMProvider
from clawlite.providers.registry import build_provider, resolve_litellm_provider


def test_resolve_gemini_uses_provider_defaults(monkeypatch) -> None:
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test-key")

    resolved = resolve_litellm_provider(
        model="gemini/gemini-2.5-flash",
        api_key="",
        base_url="https://api.openai.com/v1",
    )

    assert resolved.name == "gemini"
    assert resolved.model == "gemini-2.5-flash"
    assert resolved.api_key == "AIza-test-key"
    assert resolved.base_url == "https://generativelanguage.googleapis.com/v1beta/openai"


def test_resolve_gateway_from_openrouter_key(monkeypatch) -> None:
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)

    resolved = resolve_litellm_provider(
        model="anthropic/claude-3-7-sonnet",
        api_key="sk-or-test",
        base_url="",
    )

    assert resolved.name == "openrouter"
    assert resolved.model == "anthropic/claude-3-7-sonnet"
    assert resolved.base_url == "https://openrouter.ai/api/v1"


def test_provider_returns_missing_key_error_before_http() -> None:
    async def _scenario() -> None:
        provider = LiteLLMProvider(
            base_url="https://api.openai.com/v1",
            api_key="",
            model="gpt-4o-mini",
            provider_name="openai",
            openai_compatible=True,
        )
        try:
            await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])
        except RuntimeError as exc:
            assert str(exc) == "provider_auth_error:missing_api_key:openai"
            return
        raise AssertionError("expected missing key error")

    asyncio.run(_scenario())


def test_build_provider_uses_groq_env_key(monkeypatch) -> None:
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")

    provider = build_provider(
        {
            "model": "groq/llama-3.3-70b-versatile",
            "providers": {"litellm": {"api_key": "", "base_url": ""}},
        }
    )
    assert isinstance(provider, LiteLLMProvider)
    assert provider.provider_name == "groq"
    assert provider.api_key == "gsk_test"
    assert provider.base_url == "https://api.groq.com/openai/v1"
