from __future__ import annotations

from clawlite.providers.catalog import ONBOARDING_PROVIDER_ORDER, default_provider_model, provider_profile


def test_catalog_lists_known_providers() -> None:
    assert "openai" in ONBOARDING_PROVIDER_ORDER
    assert "anthropic" in ONBOARDING_PROVIDER_ORDER

    profile = provider_profile("openrouter")

    assert profile.family == "gateway"
    assert profile.recommended_models
    assert "Gateway" in profile.onboarding_hint


def test_catalog_model_lookup() -> None:
    profile = provider_profile("kimi-coding")

    assert profile.family == "anthropic_compatible"
    assert profile.recommended_models == ("kimi-coding/k2p5",)
    assert default_provider_model("kimi-coding") == "kimi-coding/k2p5"


def test_catalog_unknown_model() -> None:
    profile = provider_profile("unknown-provider")

    assert profile.family == "custom"
    assert profile.recommended_models == ()
    assert default_provider_model("unknown-provider") == ""
