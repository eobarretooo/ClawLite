from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from clawlite.providers.base import LLMProvider, LLMResult
from clawlite.providers.reliability import classify_provider_error, is_retryable_error


class FailoverCooldownError(RuntimeError):
    pass


@dataclass(slots=True)
class FailoverCandidate:
    provider: LLMProvider
    model: str
    cooldown_until: float = 0.0
    last_error_class: str = ""
    suppression_reason: str = ""


class FailoverProvider(LLMProvider):
    _HARD_SUPPRESSION_S: dict[str, float] = {
        "auth": 900.0,
        "config": 900.0,
        "quota": 1800.0,
    }

    def __init__(
        self,
        *,
        primary: LLMProvider | None = None,
        fallback: LLMProvider | None = None,
        fallback_model: str = "",
        candidates: list[FailoverCandidate] | None = None,
        cooldown_seconds: float = 30.0,
        now_fn: Any | None = None,
    ) -> None:
        resolved_candidates = list(candidates or [])
        if not resolved_candidates:
            if primary is None:
                raise ValueError("primary provider is required")
            resolved_candidates.append(FailoverCandidate(provider=primary, model=primary.get_default_model()))
            if fallback is not None:
                label = str(fallback_model).strip() or fallback.get_default_model()
                resolved_candidates.append(FailoverCandidate(provider=fallback, model=label))
        elif primary is not None or fallback is not None:
            raise ValueError("pass either primary/fallback or candidates, not both")

        if not resolved_candidates:
            raise ValueError("at least one provider candidate is required")

        self._candidates = resolved_candidates
        self.cooldown_seconds = max(0.0, float(cooldown_seconds))
        self._now_fn = now_fn or time.monotonic
        self.fallback_model = str(fallback_model).strip() or (
            self._candidates[1].model if len(self._candidates) > 1 else ""
        )
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
            "auth_unavailable_activations": 0,
            "quota_unavailable_activations": 0,
            "config_unavailable_activations": 0,
        }

    @property
    def primary(self) -> LLMProvider:
        return self._candidates[0].provider

    @property
    def fallback(self) -> LLMProvider | None:
        if len(self._candidates) <= 1:
            return None
        return self._candidates[1].provider

    def _now(self) -> float:
        return float(self._now_fn())

    def _cooldown_remaining(self, *, index: int, now: float | None = None) -> float:
        cursor = self._now() if now is None else float(now)
        candidate = self._candidates[index]
        return max(0.0, float(candidate.cooldown_until) - cursor)

    def _cooldown_duration_for_error_class(self, error_class: str) -> float:
        base = max(0.0, float(self.cooldown_seconds))
        hard = float(self._HARD_SUPPRESSION_S.get(str(error_class or "").strip().lower(), 0.0) or 0.0)
        return max(base, hard)

    def _activate_cooldown(self, *, index: int, error_class: str = "", now: float | None = None) -> None:
        duration_s = self._cooldown_duration_for_error_class(error_class)
        if duration_s <= 0:
            return
        cursor = self._now() if now is None else float(now)
        normalized_error_class = str(error_class or "").strip().lower()
        self._candidates[index].last_error_class = normalized_error_class
        self._candidates[index].suppression_reason = normalized_error_class or "cooldown"
        self._candidates[index].cooldown_until = cursor + duration_s
        if index == 0:
            self._diagnostics["primary_cooldown_activations"] = int(self._diagnostics["primary_cooldown_activations"]) + 1
        else:
            self._diagnostics["fallback_cooldown_activations"] = int(self._diagnostics["fallback_cooldown_activations"]) + 1
        if normalized_error_class == "auth":
            self._diagnostics["auth_unavailable_activations"] = int(self._diagnostics["auth_unavailable_activations"]) + 1
        elif normalized_error_class == "quota":
            self._diagnostics["quota_unavailable_activations"] = int(self._diagnostics["quota_unavailable_activations"]) + 1
        elif normalized_error_class == "config":
            self._diagnostics["config_unavailable_activations"] = int(self._diagnostics["config_unavailable_activations"]) + 1

    def _all_in_cooldown_error(self, *, remaining: list[tuple[int, float]]) -> FailoverCooldownError:
        formatted = ",".join(
            f"{self._candidates[index].model}:{seconds:.3f}"
            for index, seconds in remaining
        )
        message = f"provider_failover_cooldown:all_candidates_cooling_down:{formatted}"
        return FailoverCooldownError(message)

    @staticmethod
    def _sanitize(row: dict[str, Any]) -> dict[str, Any]:
        blocked = {"api_key", "access_token", "token", "authorization", "auth", "credential", "credentials"}
        sanitized: dict[str, Any] = {}
        for key, value in row.items():
            key_text = str(key).strip()
            if any(marker in key_text.lower() for marker in blocked):
                continue
            sanitized[key_text] = value
        return sanitized

    def diagnostics(self) -> dict[str, Any]:
        now = self._now()
        counters = dict(self._diagnostics)
        primary_remaining = self._cooldown_remaining(index=0, now=now)
        counters["primary_cooldown_remaining_s"] = round(primary_remaining, 3)
        counters["primary_in_cooldown"] = primary_remaining > 0
        if len(self._candidates) > 1:
            first_fallback_remaining = self._cooldown_remaining(index=1, now=now)
        else:
            first_fallback_remaining = 0.0
        counters["fallback_cooldown_remaining_s"] = round(first_fallback_remaining, 3)
        counters["fallback_in_cooldown"] = first_fallback_remaining > 0

        payload: dict[str, Any] = {
            "provider": "failover",
            "provider_name": "failover",
            "model": self.get_default_model(),
            "fallback_model": self.fallback_model,
            "fallback_models": [candidate.model for candidate in self._candidates[1:]],
            "cooldown_seconds": self.cooldown_seconds,
            "candidate_count": len(self._candidates),
            "counters": counters,
            **counters,
        }

        candidate_rows: list[dict[str, Any]] = []
        for index, candidate in enumerate(self._candidates):
            row: dict[str, Any] = {
                "index": index,
                "role": "primary" if index == 0 else "fallback",
                "model": candidate.model,
                "cooldown_remaining_s": round(self._cooldown_remaining(index=index, now=now), 3),
                "in_cooldown": self._cooldown_remaining(index=index, now=now) > 0,
                "last_error_class": str(candidate.last_error_class or ""),
                "suppression_reason": str(candidate.suppression_reason or ""),
            }
            diag_fn = getattr(candidate.provider, "diagnostics", None)
            if callable(diag_fn):
                try:
                    diag = diag_fn()
                except Exception:
                    diag = None
                if isinstance(diag, dict):
                    row["provider"] = self._sanitize(dict(diag))
            candidate_rows.append(row)
        payload["candidates"] = candidate_rows

        if candidate_rows:
            primary_row = candidate_rows[0].get("provider")
            if isinstance(primary_row, dict):
                payload["primary"] = primary_row
        if len(candidate_rows) > 1:
            fallback_row = candidate_rows[1].get("provider")
            if isinstance(fallback_row, dict):
                payload["fallback"] = fallback_row

        return payload

    def operator_clear_suppression(self, *, role: str = "", model: str = "") -> dict[str, Any]:
        normalized_role = str(role or "").strip().lower()
        normalized_model = str(model or "").strip()
        cleared = 0
        matched = 0
        for index, candidate in enumerate(self._candidates):
            candidate_role = "primary" if index == 0 else "fallback"
            if normalized_role and candidate_role != normalized_role:
                continue
            if normalized_model and candidate.model != normalized_model:
                continue
            matched += 1
            if float(candidate.cooldown_until or 0.0) > 0 or candidate.last_error_class or candidate.suppression_reason:
                candidate.cooldown_until = 0.0
                candidate.last_error_class = ""
                candidate.suppression_reason = ""
                cleared += 1
        return {
            "ok": True,
            "role": normalized_role,
            "model": normalized_model,
            "matched": matched,
            "cleared": cleared,
            "state": self.diagnostics(),
        }

    @staticmethod
    def _should_failover(error_class: str) -> bool:
        return error_class in {
            "auth",
            "quota",
            "rate_limit",
            "http_transient",
            "network",
            "retry_exhausted",
            "circuit_open",
        }

    async def _attempt_candidate(
        self,
        *,
        index: int,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        max_tokens: int | None,
        temperature: float | None,
        reasoning_effort: str | None,
    ) -> LLMResult:
        if index > 0:
            self._diagnostics["fallback_attempts"] = int(self._diagnostics["fallback_attempts"]) + 1
        return await self._candidates[index].provider.complete(
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
        )

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
        ready_indices: list[int] = []
        cooling_indices: list[tuple[int, float]] = []
        for index in range(len(self._candidates)):
            remaining = self._cooldown_remaining(index=index, now=now)
            if remaining > 0:
                if index == 0:
                    self._diagnostics["primary_skipped_due_cooldown"] = int(self._diagnostics["primary_skipped_due_cooldown"]) + 1
                else:
                    self._diagnostics["fallback_skipped_due_cooldown"] = int(self._diagnostics["fallback_skipped_due_cooldown"]) + 1
                cooling_indices.append((index, remaining))
                continue
            ready_indices.append(index)

        if not ready_indices:
            self._diagnostics["both_in_cooldown_fail_fast"] = int(self._diagnostics["both_in_cooldown_fail_fast"]) + 1
            raise self._all_in_cooldown_error(remaining=cooling_indices)

        last_exc: Exception | None = None
        for index in ready_indices:
            try:
                result = await self._attempt_candidate(
                    index=index,
                    messages=messages,
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    reasoning_effort=reasoning_effort,
                )
            except Exception as exc:
                error_text = str(exc)
                error_class = classify_provider_error(error_text)
                self._diagnostics["last_error"] = error_text
                if index == 0:
                    self._diagnostics["last_primary_error_class"] = error_class
                else:
                    self._diagnostics["last_fallback_error_class"] = error_class
                    self._diagnostics["fallback_failures"] = int(self._diagnostics["fallback_failures"]) + 1

                if not self._should_failover(error_class):
                    if index == 0:
                        self._diagnostics["primary_non_retryable_failures"] = int(self._diagnostics["primary_non_retryable_failures"]) + 1
                    last_exc = exc
                    break

                if index == 0 and is_retryable_error(error_text):
                    self._diagnostics["primary_retryable_failures"] = int(self._diagnostics["primary_retryable_failures"]) + 1
                self._activate_cooldown(index=index, error_class=error_class)
                last_exc = exc
                continue

            if index > 0:
                self._diagnostics["fallback_success"] = int(self._diagnostics["fallback_success"]) + 1
                result.metadata = dict(result.metadata)
                result.metadata["fallback_used"] = True
                result.metadata["fallback_model"] = self._candidates[index].model
                result.metadata["fallback_index"] = index
            self._candidates[index].last_error_class = ""
            self._candidates[index].suppression_reason = ""
            return result

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("provider_failover_exhausted:no_candidates_attempted")

    def get_default_model(self) -> str:
        return self._candidates[0].provider.get_default_model()
