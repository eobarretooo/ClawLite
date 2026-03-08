from __future__ import annotations

from clawlite.providers.hints import provider_probe_hints


def test_hint_401_message() -> None:
    hints = provider_probe_hints(
        provider="openai",
        error="http_status:401",
        status_code=401,
        transport="openai_compatible",
    )

    assert any("autenticacao foi rejeitada" in hint.lower() for hint in hints)


def test_hint_429_message() -> None:
    hints = provider_probe_hints(
        provider="openrouter",
        error="http_status:429",
        status_code=429,
        transport="openai_compatible",
    )

    assert any("rate limit" in hint.lower() for hint in hints)


def test_hint_unknown_model() -> None:
    hints = provider_probe_hints(
        provider="openai",
        error="http_status:400",
        error_detail="The model does not exist.",
        status_code=400,
        transport="openai_compatible",
        model="openai/gpt-missing",
    )

    assert any("openai/gpt-missing" in hint for hint in hints)


def test_hints_empty_for_unknown_error() -> None:
    hints = provider_probe_hints(
        provider="custom",
        error="mystery_failure",
        transport="",
    )

    assert hints == []
