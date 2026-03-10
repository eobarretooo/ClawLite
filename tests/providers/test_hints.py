from __future__ import annotations

from clawlite.providers.hints import provider_probe_hints
from clawlite.providers.hints import provider_telemetry_summary


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


def test_hint_openai_codex_transport_mentions_responses_backend() -> None:
    hints = provider_probe_hints(
        provider="openai_codex",
        transport="oauth_codex_responses",
    )

    assert any("/codex/responses" in hint for hint in hints)


def test_hints_empty_for_unknown_error() -> None:
    hints = provider_probe_hints(
        provider="custom",
        error="mystery_failure",
        transport="",
    )

    assert hints == []


def test_provider_telemetry_summary_surfaces_suppressed_failover_candidates() -> None:
    summary = provider_telemetry_summary(
        {
            "provider": "failover",
            "provider_name": "failover",
            "model": "openai/gpt-4o-mini",
            "transport": "openai_compatible",
            "counters": {"fallback_attempts": 1, "last_error_class": "auth"},
            "candidates": [
                {
                    "role": "primary",
                    "model": "openai/gpt-4o-mini",
                    "in_cooldown": True,
                    "cooldown_remaining_s": 900.0,
                    "suppression_reason": "auth",
                },
                {
                    "role": "fallback",
                    "model": "groq/llama-3.1-8b-instant",
                    "in_cooldown": False,
                    "cooldown_remaining_s": 0.0,
                    "suppression_reason": "",
                },
            ],
        }
    )

    assert summary["state"] == "cooldown"
    assert summary["suppression_reason"] == "auth"
    assert summary["suppressed_candidates"][0]["model"] == "openai/gpt-4o-mini"
    assert any("autenticacao" in hint.lower() for hint in summary["hints"])
