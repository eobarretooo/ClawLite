from __future__ import annotations

import asyncio

from clawlite.providers.codex import CodexProvider
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


def test_build_provider_openai_codex_falls_back_to_litellm_without_codex_auth(monkeypatch) -> None:
    monkeypatch.delenv("CLAWLITE_CODEX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("CLAWLITE_CODEX_ACCOUNT_ID", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")

    provider = build_provider(
        {
            "model": "openai-codex/codex-5.3",
            "providers": {"litellm": {"api_key": "", "base_url": ""}},
        }
    )

    assert isinstance(provider, LiteLLMProvider)
    assert provider.provider_name == "openai"
    assert provider.model == "codex-5.3"


def test_build_provider_openai_codex_prefers_codex_provider_when_auth_present(monkeypatch) -> None:
    monkeypatch.setenv("CLAWLITE_CODEX_ACCESS_TOKEN", "codex-token")
    monkeypatch.setenv("CLAWLITE_CODEX_ACCOUNT_ID", "org-id")

    provider = build_provider({"model": "openai-codex/codex-5.3"})

    assert isinstance(provider, CodexProvider)


def test_build_provider_openai_codex_accepts_auth_provider_alias_and_token_only(monkeypatch) -> None:
    monkeypatch.delenv("CLAWLITE_CODEX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("CLAWLITE_CODEX_ACCOUNT_ID", raising=False)

    provider = build_provider(
        {
            "model": "openai-codex/codex-5.3",
            "auth": {
                "providers": {
                    "openai_codex": {
                        "access_token": "oauth-token",
                    }
                }
            },
        }
    )

    assert isinstance(provider, CodexProvider)


def test_resolve_openai_ignores_incompatible_generic_key_prefix(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CLAWLITE_LITELLM_API_KEY", "AIza-test-key")

    resolved = resolve_litellm_provider(
        model="openai/codex-5.3",
        api_key="",
        base_url="",
    )

    assert resolved.name == "openai"
    assert resolved.api_key == ""


def test_resolve_openai_ignores_incompatible_configured_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)

    resolved = resolve_litellm_provider(
        model="openai/codex-5.3",
        api_key="AIza-test-key",
        base_url="",
    )

    assert resolved.name == "openai"
    assert resolved.api_key == ""


def test_build_provider_prefers_provider_specific_block_over_legacy(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    provider = build_provider(
        {
            "model": "openrouter/openai/gpt-4o-mini",
            "providers": {
                "litellm": {"api_key": "legacy-key", "base_url": "https://legacy.example/v1"},
                "openrouter": {"api_key": "sk-or-specific", "api_base": "https://openrouter.ai/api/v1"},
            },
        }
    )
    assert isinstance(provider, LiteLLMProvider)
    assert provider.provider_name == "openrouter"
    assert provider.api_key == "sk-or-specific"
    assert provider.base_url == "https://openrouter.ai/api/v1"


def test_build_provider_custom_accepts_extra_headers() -> None:
    provider = build_provider(
        {
            "model": "custom/my-model",
            "providers": {
                "custom": {
                    "api_key": "c-key",
                    "api_base": "http://127.0.0.1:5000/v1",
                    "extra_headers": {"X-App": "claw"},
                }
            },
        }
    )

    assert isinstance(provider, LiteLLMProvider)
    assert provider.base_url == "http://127.0.0.1:5000/v1"
    assert provider.api_key == "c-key"
    assert provider.extra_headers == {"X-App": "claw"}
