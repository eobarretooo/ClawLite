from __future__ import annotations

import asyncio
import json

from clawlite.providers.codex import CodexProvider
from clawlite.providers.failover import FailoverProvider
from clawlite.providers.litellm import LiteLLMProvider
from clawlite.providers import registry as registry_mod
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


def test_resolve_xai_uses_provider_defaults(monkeypatch) -> None:
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "xai-live-test")

    resolved = resolve_litellm_provider(
        model="xai/grok-4",
        api_key="",
        base_url="https://api.openai.com/v1",
    )

    assert resolved.name == "xai"
    assert resolved.model == "grok-4"
    assert resolved.api_key == "xai-live-test"
    assert resolved.base_url == "https://api.x.ai/v1"


def test_resolve_kilocode_detects_gateway_from_base_url(monkeypatch) -> None:
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)
    monkeypatch.setenv("KILOCODE_API_KEY", "kilo-test")

    resolved = resolve_litellm_provider(
        model="openai/gpt-4.1-mini",
        api_key="",
        base_url="https://api.kilo.ai/api/gateway/",
    )

    assert resolved.name == "kilocode"
    assert resolved.model == "openai/gpt-4.1-mini"
    assert resolved.api_key == "kilo-test"
    assert resolved.base_url == "https://api.kilo.ai/api/gateway"


def test_resolve_zai_accepts_env_aliases(monkeypatch) -> None:
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    monkeypatch.setenv("Z_AI_API_KEY", "zai-test")

    resolved = resolve_litellm_provider(
        model="zai/glm-5",
        api_key="",
        base_url="",
    )

    assert resolved.name == "zai"
    assert resolved.model == "glm-5"
    assert resolved.api_key == "zai-test"
    assert resolved.base_url == "https://api.z.ai/api/paas/v4"


def test_resolve_minimax_uses_anthropic_transport(monkeypatch) -> None:
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)
    monkeypatch.setenv("MINIMAX_API_KEY", "mini-test")

    resolved = resolve_litellm_provider(
        model="minimax/MiniMax-M2.5",
        api_key="",
        base_url="",
    )

    assert resolved.name == "minimax"
    assert resolved.model == "MiniMax-M2.5"
    assert resolved.api_key == "mini-test"
    assert resolved.base_url == "https://api.minimax.io/anthropic"
    assert resolved.openai_compatible is False
    assert resolved.native_transport == "anthropic"


def test_resolve_kimi_coding_uses_anthropic_transport(monkeypatch) -> None:
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)
    monkeypatch.setenv("KIMI_API_KEY", "kimi-test")

    resolved = resolve_litellm_provider(
        model="kimi-coding/k2p5",
        api_key="",
        base_url="",
    )

    assert resolved.name == "kimi_coding"
    assert resolved.model == "k2p5"
    assert resolved.api_key == "kimi-test"
    assert resolved.base_url == "https://api.kimi.com/coding"
    assert resolved.openai_compatible is False
    assert resolved.native_transport == "anthropic"


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


def test_build_provider_uses_dynamic_xai_block(monkeypatch) -> None:
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)

    provider = build_provider(
        {
            "model": "xai/grok-4",
            "providers": {
                "litellm": {"api_key": "", "base_url": ""},
                "xai": {"api_key": "xai-config", "api_base": "https://api.x.ai/v1"},
            },
        }
    )

    assert isinstance(provider, LiteLLMProvider)
    assert provider.provider_name == "xai"
    assert provider.api_key == "xai-config"
    assert provider.base_url == "https://api.x.ai/v1"


def test_build_provider_uses_minimax_anthropic_transport(monkeypatch) -> None:
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)

    provider = build_provider(
        {
            "model": "minimax/MiniMax-M2.5",
            "providers": {
                "litellm": {"api_key": "", "base_url": ""},
                "minimax": {"api_key": "mini-config", "api_base": "https://api.minimax.io/anthropic"},
            },
        }
    )

    assert isinstance(provider, LiteLLMProvider)
    assert provider.provider_name == "minimax"
    assert provider.openai_compatible is False
    assert provider.native_transport == "anthropic"
    assert provider.base_url == "https://api.minimax.io/anthropic"


def test_build_provider_prefers_single_configured_vendor_for_generic_model(monkeypatch) -> None:
    monkeypatch.delenv("CLAWLITE_LITELLM_API_KEY", raising=False)

    provider = build_provider(
        {
            "model": "claude-3.5-sonnet",
            "providers": {
                "litellm": {"api_key": "", "base_url": ""},
                "minimax": {"api_key": "mini-config", "api_base": "https://api.minimax.io/anthropic"},
            },
        }
    )

    assert isinstance(provider, LiteLLMProvider)
    assert provider.provider_name == "minimax"
    assert provider.model == "claude-3.5-sonnet"
    assert provider.base_url == "https://api.minimax.io/anthropic"
    assert provider.openai_compatible is False
    assert provider.native_transport == "anthropic"


def test_build_provider_openai_codex_is_deterministic_even_without_codex_auth(monkeypatch) -> None:
    monkeypatch.delenv("CLAWLITE_CODEX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("CLAWLITE_CODEX_ACCOUNT_ID", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")

    provider = build_provider(
        {
            "model": "openai-codex/codex-5.3",
            "providers": {"litellm": {"api_key": "", "base_url": ""}},
        }
    )

    assert isinstance(provider, CodexProvider)
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


def test_build_provider_openai_codex_reads_auth_file_when_env_missing(tmp_path, monkeypatch) -> None:
    auth_path = tmp_path / "auth.json"
    auth_path.write_text(
        json.dumps(
            {
                "auth_mode": "login",
                "tokens": {
                    "access_token": "codex-file-token",
                    "account_id": "org-file",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("CLAWLITE_CODEX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("CLAWLITE_CODEX_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("OPENAI_CODEX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_ORG_ID", raising=False)
    monkeypatch.setenv("CLAWLITE_CODEX_AUTH_PATH", str(auth_path))

    provider = build_provider({"model": "openai-codex/codex-5.3"})

    assert isinstance(provider, CodexProvider)
    assert provider.access_token == "codex-file-token"
    assert provider.account_id == "org-file"


def test_build_provider_detects_ollama_from_local_base_url_without_api_key() -> None:
    provider = build_provider(
        {
            "model": "openai/llama3.2",
            "providers": {
                "litellm": {"api_key": "", "base_url": "http://127.0.0.1:11434"},
            },
        }
    )

    assert isinstance(provider, LiteLLMProvider)
    assert provider.provider_name == "ollama"
    assert provider.base_url == "http://127.0.0.1:11434/v1"
    assert provider.allow_empty_api_key is True


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


def test_build_provider_wraps_with_failover_when_fallback_model_is_configured() -> None:
    provider = build_provider(
        {
            "model": "openai/gpt-4.1-mini",
            "fallback_model": "openai/gpt-4o-mini",
            "providers": {"litellm": {"api_key": "sk-test", "base_url": "https://api.openai.com/v1"}},
        }
    )
    assert isinstance(provider, FailoverProvider)
    assert provider.diagnostics()["fallback_models"] == ["openai/gpt-4o-mini"]


def test_build_provider_wraps_with_multi_hop_failover_when_fallback_models_are_configured() -> None:
    provider = build_provider(
        {
            "model": "openai/gpt-4.1-mini",
            "fallback_models": [
                "openrouter/openai/gpt-4o-mini",
                "groq/llama-3.3-70b-versatile",
                "openai/gpt-4.1-mini",
            ],
            "providers": {
                "litellm": {"api_key": "sk-test", "base_url": "https://api.openai.com/v1"},
                "openrouter": {"api_key": "sk-or-test", "api_base": "https://openrouter.ai/api/v1"},
                "groq": {"api_key": "gsk_test", "api_base": "https://api.groq.com/openai/v1"},
            },
        }
    )
    assert isinstance(provider, FailoverProvider)
    diag = provider.diagnostics()
    assert diag["candidate_count"] == 3
    assert diag["fallback_models"] == [
        "openrouter/openai/gpt-4o-mini",
        "groq/llama-3.3-70b-versatile",
    ]


def test_build_provider_does_not_wrap_with_failover_when_same_model() -> None:
    provider = build_provider(
        {
            "model": "openai/gpt-4.1-mini",
            "fallback_model": "openai/gpt-4.1-mini",
            "providers": {"litellm": {"api_key": "sk-test", "base_url": "https://api.openai.com/v1"}},
        }
    )
    assert isinstance(provider, LiteLLMProvider)


def test_resolve_litellm_provider_raises_explicit_error_without_specs(monkeypatch) -> None:
    monkeypatch.setattr(registry_mod, "SPECS", ())
    try:
        resolve_litellm_provider(model="openai/gpt-4.1-mini", api_key="", base_url="")
    except RuntimeError as exc:
        assert str(exc) == "provider_registry_error:missing_default_spec:openai"
    else:
        raise AssertionError("expected explicit provider registry error")
