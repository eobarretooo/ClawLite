from __future__ import annotations

import time
from typing import Any

from clawlite.providers.base import LLMProvider, LLMResult
from clawlite.providers.reliability import classify_provider_error, is_retryable_error


class FailoverCooldownError(RuntimeError):
    pass


class FailoverProvider(LLMProvider):
    def __init__(
        self,
        *,
        primary: LLMProvider,
        fallback: LLMProvider,
        fallback_model: str,
        cooldown_seconds: float = 30.0,
        now_fn: Any | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.fallback_model = str(fallback_model).strip()
        self.cooldown_seconds = max(0.0, float(cooldown_seconds))
        self._now_fn = now_fn or time.monotonic
        self._primary_cooldown_until = 0.0
        self._fallback_cooldown_until = 0.0
        self._diagnostics: dict[str, Any] = {
            "fallback_attempts": 0,
            "fallback_success": 0,
            "fallback_failures": 0,
            "last_error": "",
            "last_primary_error_class": "",
            "last_fallback_error_class": "",
            "primary_retryable_failures": 0,
            "primary_non_retryable_failures": 0,
            "primary_cooldown_activations": 0,
            "fallback_cooldown_activations": 0,
            "primary_skipped_due_cooldown": 0,
            "fallback_skipped_due_cooldown": 0,
            "both_in_cooldown_fail_fast": 0,
        }

    def _now(self) -> float:
        return float(self._now_fn())

    def _cooldown_remaining(self, *, target: str, now: float | None = None) -> float:
        cursor = self._now() if now is None else float(now)
        if target == "primary":
            until = self._primary_cooldown_until
        else:
            until = self._fallback_cooldown_until
        return max(0.0, float(until) - cursor)

    def _activate_cooldown(self, *, target: str, now: float | None = None) -> None:
        if self.cooldown_seconds <= 0:
            return
        cursor = self._now() if now is None else float(now)
        until = cursor + self.cooldown_seconds
        if target == "primary":
            self._primary_cooldown_until = until
            self._diagnostics["primary_cooldown_activations"] = int(self._diagnostics["primary_cooldown_activations"]) + 1
            return
        self._fallback_cooldown_until = until
        self._diagnostics["fallback_cooldown_activations"] = int(self._diagnostics["fallback_cooldown_activations"]) + 1

    def _both_cooling_error(self, *, primary_remaining: float, fallback_remaining: float) -> FailoverCooldownError:
        message = (
            "provider_failover_cooldown:both_providers_cooling_down:"
            f"primary_remaining_s={primary_remaining:.3f}:"
            f"fallback_remaining_s={fallback_remaining:.3f}"
        )
        return FailoverCooldownError(message)

    def diagnostics(self) -> dict[str, Any]:
        now = self._now()
        primary_remaining = self._cooldown_remaining(target="primary", now=now)
        fallback_remaining = self._cooldown_remaining(target="fallback", now=now)
        counters = dict(self._diagnostics)
        counters["primary_cooldown_remaining_s"] = round(primary_remaining, 3)
        counters["fallback_cooldown_remaining_s"] = round(fallback_remaining, 3)
        counters["primary_in_cooldown"] = primary_remaining > 0
        counters["fallback_in_cooldown"] = fallback_remaining > 0
        payload = {
            "provider": "failover",
            "provider_name": "failover",
            "model": self.get_default_model(),
            "fallback_model": self.fallback_model,
            "cooldown_seconds": self.cooldown_seconds,
            "counters": counters,
            **counters,
        }

        def _sanitize(row: dict[str, Any]) -> dict[str, Any]:
            blocked = {"api_key", "access_token", "token", "authorization", "auth", "credential", "credentials"}
            sanitized: dict[str, Any] = {}
            for key, value in row.items():
                key_text = str(key).strip()
                if any(marker in key_text.lower() for marker in blocked):
                    continue
                sanitized[key_text] = value
            return sanitized

        primary_diag = getattr(self.primary, "diagnostics", None)
        if callable(primary_diag):
            try:
                row = primary_diag()
                if isinstance(row, dict):
                    payload["primary"] = _sanitize(dict(row))
            except Exception:
                pass
        fallback_diag = getattr(self.fallback, "diagnostics", None)
        if callable(fallback_diag):
            try:
                row = fallback_diag()
                if isinstance(row, dict):
                    payload["fallback"] = _sanitize(dict(row))
            except Exception:
                pass
        return payload

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        reasoning_effort: str | None = None,
    ) -> LLMResult:
        now = self._now()
        primary_remaining = self._cooldown_remaining(target="primary", now=now)
        fallback_remaining = self._cooldown_remaining(target="fallback", now=now)
        if primary_remaining > 0:
            self._diagnostics["primary_skipped_due_cooldown"] = int(self._diagnostics["primary_skipped_due_cooldown"]) + 1
            if fallback_remaining > 0:
                self._diagnostics["fallback_skipped_due_cooldown"] = int(self._diagnostics["fallback_skipped_due_cooldown"]) + 1
                self._diagnostics["both_in_cooldown_fail_fast"] = int(self._diagnostics["both_in_cooldown_fail_fast"]) + 1
                raise self._both_cooling_error(primary_remaining=primary_remaining, fallback_remaining=fallback_remaining)
            return await self._attempt_fallback(
                messages=messages,
                tools=tools,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
            )

        try:
            return await self.primary.complete(
                messages=messages,
                tools=tools,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
            )
        except Exception as exc:
            primary_error = str(exc)
            self._diagnostics["last_error"] = primary_error
            primary_error_class = classify_provider_error(primary_error)
            self._diagnostics["last_primary_error_class"] = primary_error_class
            if not is_retryable_error(primary_error):
                self._diagnostics["primary_non_retryable_failures"] = int(self._diagnostics["primary_non_retryable_failures"]) + 1
                raise
            self._diagnostics["primary_retryable_failures"] = int(self._diagnostics["primary_retryable_failures"]) + 1
            self._activate_cooldown(target="primary")

        fallback_remaining = self._cooldown_remaining(target="fallback")
        if fallback_remaining > 0:
            self._diagnostics["fallback_skipped_due_cooldown"] = int(self._diagnostics["fallback_skipped_due_cooldown"]) + 1
            self._diagnostics["both_in_cooldown_fail_fast"] = int(self._diagnostics["both_in_cooldown_fail_fast"]) + 1
            raise self._both_cooling_error(
                primary_remaining=self._cooldown_remaining(target="primary"),
                fallback_remaining=fallback_remaining,
            )
        return await self._attempt_fallback(
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
        )

    async def _attempt_fallback(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int | None,
        temperature: float | None,
        reasoning_effort: str | None,
    ) -> LLMResult:
        self._diagnostics["fallback_attempts"] = int(self._diagnostics["fallback_attempts"]) + 1
        try:
            result = await self.fallback.complete(
                messages=messages,
                tools=tools,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
            )
        except Exception as exc:
            self._diagnostics["fallback_failures"] = int(self._diagnostics["fallback_failures"]) + 1
            fallback_error = str(exc)
            self._diagnostics["last_error"] = fallback_error
            self._diagnostics["last_fallback_error_class"] = classify_provider_error(fallback_error)
            if is_retryable_error(fallback_error):
                self._activate_cooldown(target="fallback")
            raise

        self._diagnostics["fallback_success"] = int(self._diagnostics["fallback_success"]) + 1
        result.metadata = dict(result.metadata)
        result.metadata["fallback_used"] = True
        result.metadata["fallback_model"] = self.fallback_model
        return result

    def get_default_model(self) -> str:
        return self.primary.get_default_model()
