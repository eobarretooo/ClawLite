from __future__ import annotations

from clawlite.providers.model_probe import evaluate_remote_model_check


def test_evaluate_remote_model_check_matches_provider_prefixed_variants() -> None:
    payload = {
        "data": [
            {"id": "openai/gpt-4o-mini:free"},
            {"id": "anthropic/claude-3-5-sonnet"},
        ]
    }

    result = evaluate_remote_model_check(
        provider="openrouter",
        model="openrouter/openai/gpt-4o-mini",
        payload=payload,
        is_gateway=True,
    )

    assert result["checked"] is True
    assert result["ok"] is True
    assert result["matched_model"] == "openai/gpt-4o-mini:free"


def test_evaluate_remote_model_check_matches_unprefixed_variants() -> None:
    payload = {"data": [{"id": "gpt-4o-mini"}]}

    result = evaluate_remote_model_check(
        provider="openrouter",
        model="openrouter/openai/gpt-4o-mini",
        payload=payload,
        is_gateway=True,
    )

    assert result["checked"] is True
    assert result["ok"] is True
    assert result["matched_model"] == "gpt-4o-mini"
