from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from clawlite.providers.base import LLMResult
from clawlite.providers.failover import FailoverCandidate, FailoverCooldownError, FailoverProvider
from clawlite.providers.telemetry import TelemetryRegistry


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
            "token": "test_token_value",
            "counters": {"requests": self.calls},
        }


class _SequenceProvider:
    def __init__(self, outcomes: list[str]) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    async def complete(self, *, messages, tools, max_tokens=None, temperature=None, reasoning_effort=None):
        self.calls += 1
        outcome = self.outcomes.pop(0) if self.outcomes else "ok:default"
        if outcome.startswith("err:"):
            raise RuntimeError(outcome.removeprefix("err:"))
        return LLMResult(text=outcome.removeprefix("ok:"), model="test/model", tool_calls=[], metadata={"provider": "test"})

    def get_default_model(self) -> str:
        return "test/model"


class _HealthProvider(_Provider):
    def __init__(self, *, model: str, result: str = "", error: str = "", diagnostics_payload: dict[str, object] | None = None) -> None:
        super().__init__(result=result, error=error)
        self.model = model
        self.diagnostics_payload = dict(diagnostics_payload or {})

    def get_default_model(self) -> str:
        return self.model

    def diagnostics(self) -> dict[str, object]:
        payload = {
            "provider": "test",
            "provider_name": "test",
            "model": self.model,
            "counters": {},
        }
        payload.update(self.diagnostics_payload)
        return payload


class _Clock:
    def __init__(self, start: float = 1000.0) -> None:
        self.value = start

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += float(seconds)


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
        assert diag["last_primary_error_class"] == "http_transient"
        assert diag["primary_retryable_failures"] == 1
        assert diag["primary_non_retryable_failures"] == 0

    asyncio.run(_scenario())


def test_failover_provider_does_not_use_fallback_for_non_retryable_error() -> None:
    async def _scenario() -> None:
        primary = _Provider(error="provider_auth_error:missing_api_key:openai")
        fallback = _Provider(result="from fallback")
        provider = FailoverProvider(primary=primary, fallback=fallback, fallback_model="openai/gpt-4.1-mini")

        out = await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])

        assert out.text == "from fallback"
        assert out.metadata["fallback_used"] is True
        assert fallback.calls == 1
        diag = provider.diagnostics()
        assert diag["last_primary_error_class"] == "auth"
        assert diag["auth_unavailable_activations"] == 1
        assert diag["primary_retryable_failures"] == 0
        assert diag["primary_non_retryable_failures"] == 0
        assert diag["fallback_success"] == 1

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
        assert diag["last_primary_error_class"] == "network"
        assert diag["last_fallback_error_class"] == "http_transient"

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
    assert "last_primary_error_class" in diag["counters"]
    assert "last_fallback_error_class" in diag["counters"]
    assert "primary" in diag
    assert "fallback" in diag
    assert "token" not in diag["primary"]
    assert "token" not in diag["fallback"]
    encoded = json.dumps(diag).lower()
    assert "test_token_value" not in encoded
    assert "fallback_health_order" in diag
    assert "health_score" in diag["candidates"][0]
    assert "health_state" in diag["candidates"][0]


def test_failover_provider_primary_cooldown_skips_primary_and_uses_fallback() -> None:
    async def _scenario() -> None:
        clock = _Clock()
        primary = _SequenceProvider(["err:provider_network_error:timeout", "ok:from primary"])
        fallback = _SequenceProvider(["ok:from fallback", "ok:from fallback again"])
        provider = FailoverProvider(
            primary=primary,
            fallback=fallback,
            fallback_model="openai/gpt-4.1-mini",
            cooldown_seconds=30.0,
            now_fn=clock.now,
        )

        out1 = await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])
        assert out1.text == "from fallback"
        assert primary.calls == 1
        assert fallback.calls == 1

        out2 = await provider.complete(messages=[{"role": "user", "content": "hi again"}], tools=[])
        assert out2.text == "from fallback again"
        assert primary.calls == 1
        assert fallback.calls == 2

        diag = provider.diagnostics()
        assert diag["primary_skipped_due_cooldown"] == 1
        assert diag["fallback_attempts"] == 2
        assert diag["primary_in_cooldown"] is True
        assert diag["primary_cooldown_remaining_s"] > 0

    asyncio.run(_scenario())


def test_failover_provider_fallback_cooldown_avoids_repeated_attempts() -> None:
    async def _scenario() -> None:
        clock = _Clock()
        primary = _Provider(error="provider_network_error:timeout")
        fallback = _Provider(error="provider_http_error:503:temporary")
        provider = FailoverProvider(
            primary=primary,
            fallback=fallback,
            fallback_model="openai/gpt-4.1-mini",
            cooldown_seconds=45.0,
            now_fn=clock.now,
        )

        try:
            await provider.complete(messages=[{"role": "user", "content": "first"}], tools=[])
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected first fallback failure")

        try:
            await provider.complete(messages=[{"role": "user", "content": "second"}], tools=[])
        except FailoverCooldownError as exc:
            assert "provider_failover_cooldown:all_candidates_cooling_down" in str(exc)
        else:
            raise AssertionError("expected cooldown fast-fail")

        assert primary.calls == 1
        assert fallback.calls == 1
        diag = provider.diagnostics()
        assert diag["fallback_cooldown_activations"] == 1
        assert diag["fallback_skipped_due_cooldown"] == 1
        assert diag["both_in_cooldown_fail_fast"] == 1
        assert diag["fallback_attempts"] == 1

    asyncio.run(_scenario())


def test_failover_provider_uses_next_available_candidate_in_chain() -> None:
    async def _scenario() -> None:
        primary = _Provider(error="provider_http_error:429:rate limit")
        fallback_a = _Provider(error="provider_http_error:503:temporary")
        fallback_b = _Provider(result="from third candidate")
        provider = FailoverProvider(
            candidates=[
                FailoverCandidate(provider=primary, model="openai/gpt-4.1"),
                FailoverCandidate(provider=fallback_a, model="openrouter/openai/gpt-4o"),
                FailoverCandidate(provider=fallback_b, model="groq/llama-3.3-70b"),
            ]
        )

        out = await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])

        assert out.text == "from third candidate"
        assert out.metadata["fallback_used"] is True
        assert out.metadata["fallback_model"] == "groq/llama-3.3-70b"
        assert out.metadata["fallback_index"] == 2
        diag = provider.diagnostics()
        assert diag["candidate_count"] == 3
        assert diag["fallback_attempts"] == 2
        assert diag["fallback_failures"] == 1
        assert diag["fallback_success"] == 1
        assert diag["last_primary_error_class"] == "rate_limit"
        assert diag["last_fallback_error_class"] == "http_transient"
        assert len(diag["candidates"]) == 3

    asyncio.run(_scenario())


def test_failover_provider_cooldown_expires_and_primary_is_retried() -> None:
    async def _scenario() -> None:
        clock = _Clock()
        primary = _SequenceProvider(["err:provider_network_error:timeout", "ok:from primary"])
        fallback = _Provider(result="from fallback")
        provider = FailoverProvider(
            primary=primary,
            fallback=fallback,
            fallback_model="openai/gpt-4.1-mini",
            cooldown_seconds=5.0,
            now_fn=clock.now,
        )

        out1 = await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])
        assert out1.text == "from fallback"
        assert primary.calls == 1
        assert fallback.calls == 1

        clock.advance(5.1)

        out2 = await provider.complete(messages=[{"role": "user", "content": "hi again"}], tools=[])
        assert out2.text == "from primary"
        assert primary.calls == 2
        assert fallback.calls == 1
        assert "fallback_used" not in out2.metadata

        diag = provider.diagnostics()
        assert diag["primary_in_cooldown"] is False
        assert diag["primary_cooldown_remaining_s"] == 0.0

    asyncio.run(_scenario())


def test_failover_provider_auth_error_applies_hard_suppression_window() -> None:
    async def _scenario() -> None:
        clock = _Clock()
        primary = _Provider(error="provider_auth_error:missing_api_key:openai")
        fallback = _Provider(result="from fallback")
        provider = FailoverProvider(
            primary=primary,
            fallback=fallback,
            fallback_model="openai/gpt-4.1-mini",
            cooldown_seconds=30.0,
            now_fn=clock.now,
        )

        out = await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])

        assert out.text == "from fallback"
        diag = provider.diagnostics()
        assert diag["auth_unavailable_activations"] == 1
        assert diag["primary_in_cooldown"] is True
        assert diag["primary_cooldown_remaining_s"] >= 899.0
        assert diag["candidates"][0]["suppression_reason"] == "auth"

    asyncio.run(_scenario())


def test_failover_provider_quota_error_applies_extended_suppression_window() -> None:
    async def _scenario() -> None:
        clock = _Clock()
        primary = _Provider(error="provider_http_error:429:insufficient_quota")
        fallback = _Provider(result="from fallback")
        provider = FailoverProvider(
            primary=primary,
            fallback=fallback,
            fallback_model="openai/gpt-4.1-mini",
            cooldown_seconds=30.0,
            now_fn=clock.now,
        )

        out = await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])

        assert out.text == "from fallback"
        diag = provider.diagnostics()
        assert diag["quota_unavailable_activations"] == 1
        assert diag["primary_in_cooldown"] is True
        assert diag["primary_cooldown_remaining_s"] >= 1799.0
        assert diag["candidates"][0]["suppression_reason"] == "quota"

    asyncio.run(_scenario())


def test_failover_provider_operator_clear_suppression_resets_candidate_state() -> None:
    async def _scenario() -> None:
        clock = _Clock()
        primary = _Provider(error="provider_auth_error:missing_api_key:openai")
        fallback = _Provider(result="from fallback")
        provider = FailoverProvider(
            primary=primary,
            fallback=fallback,
            fallback_model="openai/gpt-4.1-mini",
            cooldown_seconds=30.0,
            now_fn=clock.now,
        )

        out = await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])
        assert out.text == "from fallback"
        before = provider.diagnostics()
        assert before["primary_in_cooldown"] is True

        summary = provider.operator_clear_suppression(role="primary")

        assert summary["ok"] is True
        assert summary["cleared"] == 1
        after = provider.diagnostics()
        assert after["primary_in_cooldown"] is False
        assert after["primary_cooldown_remaining_s"] == 0.0
        assert after["candidates"][0]["suppression_reason"] == ""

    asyncio.run(_scenario())


def test_failover_provider_prefers_healthier_ready_fallback_candidate() -> None:
    async def _scenario() -> None:
        telemetry = TelemetryRegistry()
        primary = _Provider(error="provider_network_error:timeout")
        fallback_a = _HealthProvider(
            model="openrouter/openai/gpt-4o-mini-health-a",
            result="from fallback a",
            diagnostics_payload={
                "counters": {
                    "requests": 12,
                    "consecutive_failures": 2,
                    "error_class_counts": {"rate_limit": 4},
                }
            },
        )
        fallback_b = _HealthProvider(
            model="groq/llama-3.3-70b-health-b",
            result="from fallback b",
            diagnostics_payload={
                "counters": {
                    "requests": 12,
                    "consecutive_failures": 0,
                    "error_class_counts": {"rate_limit": 1},
                }
            },
        )
        telemetry.record("openrouter/openai/gpt-4o-mini-health-a", latency_ms=2400.0, error=True)
        telemetry.record("openrouter/openai/gpt-4o-mini-health-a", latency_ms=2100.0)
        telemetry.record("groq/llama-3.3-70b-health-b", latency_ms=140.0)
        telemetry.record("groq/llama-3.3-70b-health-b", latency_ms=120.0)

        provider = FailoverProvider(
            candidates=[
                FailoverCandidate(provider=primary, model="openai/gpt-4.1"),
                FailoverCandidate(provider=fallback_a, model="openrouter/openai/gpt-4o-mini-health-a"),
                FailoverCandidate(provider=fallback_b, model="groq/llama-3.3-70b-health-b"),
            ]
        )

        with patch("clawlite.providers.failover.get_telemetry_registry", return_value=telemetry):
            out = await provider.complete(messages=[{"role": "user", "content": "hi"}], tools=[])
            diag = provider.diagnostics()

        assert out.text == "from fallback b"
        assert fallback_a.calls == 0
        assert fallback_b.calls == 1
        assert diag["fallback_health_reorders"] == 1
        assert diag["fallback_health_order"][0]["model"] == "groq/llama-3.3-70b-health-b"
        assert diag["fallback_health_order"][1]["model"] == "openrouter/openai/gpt-4o-mini-health-a"

    asyncio.run(_scenario())


def test_failover_provider_diagnostics_surface_candidate_health_details() -> None:
    telemetry = TelemetryRegistry()
    telemetry.record("openrouter/openai/gpt-4o-mini-health-diag", latency_ms=500.0)
    provider = FailoverProvider(
        candidates=[
            FailoverCandidate(provider=_Provider(result="p"), model="openai/gpt-4.1"),
            FailoverCandidate(
                provider=_HealthProvider(
                    model="openrouter/openai/gpt-4o-mini-health-diag",
                    result="f",
                    diagnostics_payload={
                        "counters": {
                            "requests": 10,
                            "consecutive_failures": 1,
                            "error_class_counts": {"network": 2},
                        }
                    },
                ),
                model="openrouter/openai/gpt-4o-mini-health-diag",
            ),
        ]
    )

    with patch("clawlite.providers.failover.get_telemetry_registry", return_value=telemetry):
        diag = provider.diagnostics()

    fallback_row = diag["candidates"][1]
    assert fallback_row["health_state"] in {"degraded", "unstable", "healthy"}
    assert fallback_row["health_score"] < 100.0
    assert fallback_row["latency_p50_ms"] == 500.0
    assert fallback_row["error_count"] == 2
    assert diag["fallback_health_order"][0]["health_score"] == fallback_row["health_score"]
