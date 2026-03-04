from __future__ import annotations

from typing import Any

from clawlite.providers.base import LLMProvider, LLMResult
from clawlite.providers.reliability import is_retryable_error


class FailoverProvider(LLMProvider):
    def __init__(self, *, primary: LLMProvider, fallback: LLMProvider, fallback_model: str) -> None:
        self.primary = primary
        self.fallback = fallback
        self.fallback_model = str(fallback_model).strip()
        self._diagnostics: dict[str, Any] = {
            "fallback_attempts": 0,
            "fallback_success": 0,
            "fallback_failures": 0,
            "last_error": "",
        }

    def diagnostics(self) -> dict[str, Any]:
        payload = {
            "provider": "failover",
            "provider_name": "failover",
            "model": self.get_default_model(),
            "fallback_model": self.fallback_model,
            "counters": dict(self._diagnostics),
            **dict(self._diagnostics),
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
            if not is_retryable_error(primary_error):
                raise

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
            self._diagnostics["last_error"] = str(exc)
            raise

        self._diagnostics["fallback_success"] = int(self._diagnostics["fallback_success"]) + 1
        result.metadata = dict(result.metadata)
        result.metadata["fallback_used"] = True
        result.metadata["fallback_model"] = self.fallback_model
        return result

    def get_default_model(self) -> str:
        return self.primary.get_default_model()
