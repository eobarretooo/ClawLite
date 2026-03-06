from __future__ import annotations

import asyncio
import json
import os
import random
import time
from typing import Any

import httpx

from clawlite.providers.base import LLMProvider, LLMResult, ToolCall
from clawlite.providers.reliability import ReliabilitySettings, classify_provider_error, parse_retry_after_seconds


class CodexProvider(LLMProvider):
    def __init__(
        self,
        *,
        model: str,
        access_token: str,
        account_id: str = "",
        timeout: float = 30.0,
        base_url: str = "",
        retry_max_attempts: int = 3,
        retry_initial_backoff_s: float = 0.5,
        retry_max_backoff_s: float = 8.0,
        retry_jitter_s: float = 0.2,
        circuit_failure_threshold: int = 3,
        circuit_cooldown_s: float = 30.0,
    ) -> None:
        self.model = model
        self.access_token = access_token
        self.account_id = account_id
        self.timeout = timeout
        self.base_url = (base_url or os.getenv("CLAWLITE_CODEX_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.reliability = ReliabilitySettings(
            retry_max_attempts=max(1, int(retry_max_attempts)),
            retry_initial_backoff_s=max(0.0, float(retry_initial_backoff_s)),
            retry_max_backoff_s=max(float(retry_initial_backoff_s), float(retry_max_backoff_s)),
            retry_jitter_s=max(0.0, float(retry_jitter_s)),
            circuit_failure_threshold=max(1, int(circuit_failure_threshold)),
            circuit_cooldown_s=max(0.0, float(circuit_cooldown_s)),
        )
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0
        self._diagnostics: dict[str, Any] = {
            "requests": 0,
            "successes": 0,
            "retries": 0,
            "timeouts": 0,
            "network_errors": 0,
            "http_errors": 0,
            "auth_errors": 0,
            "rate_limit_errors": 0,
            "server_errors": 0,
            "circuit_open": False,
            "circuit_open_count": 0,
            "circuit_close_count": 0,
            "consecutive_failures": 0,
            "last_error": "",
            "last_error_class": "",
            "error_class_counts": {},
            "last_status_code": 0,
        }

    def diagnostics(self) -> dict[str, Any]:
        counters = dict(self._diagnostics)
        counters["consecutive_failures"] = int(self._consecutive_failures)
        counters["circuit_open"] = bool(self._circuit_open_until > time.monotonic())
        return {
            "provider": "codex",
            "provider_name": "openai_codex",
            "model": self.model,
            "transport": "openai_compatible",
            "counters": counters,
            **counters,
        }

    def _check_circuit(self) -> str | None:
        now = time.monotonic()
        if self._circuit_open_until <= 0:
            self._diagnostics["circuit_open"] = False
            return None
        if now >= self._circuit_open_until:
            self._circuit_open_until = 0.0
            self._consecutive_failures = 0
            self._diagnostics["consecutive_failures"] = 0
            self._diagnostics["circuit_open"] = False
            self._diagnostics["circuit_close_count"] = int(self._diagnostics["circuit_close_count"]) + 1
            return None
        self._diagnostics["circuit_open"] = True
        return f"provider_circuit_open:codex:{self.reliability.circuit_cooldown_s}"

    def _record_success(self) -> None:
        self._diagnostics["successes"] = int(self._diagnostics["successes"]) + 1
        self._consecutive_failures = 0
        self._diagnostics["consecutive_failures"] = 0
        self._diagnostics["last_error"] = ""
        self._diagnostics["last_error_class"] = ""
        self._diagnostics["last_status_code"] = 0

    def _record_failure(self, *, error: str, status_code: int | None = None) -> None:
        self._diagnostics["last_error"] = str(error)
        error_class = classify_provider_error(str(error))
        self._diagnostics["last_error_class"] = error_class
        counts = self._diagnostics.get("error_class_counts")
        if not isinstance(counts, dict):
            counts = {}
            self._diagnostics["error_class_counts"] = counts
        counts[error_class] = int(counts.get(error_class, 0)) + 1
        self._diagnostics["last_status_code"] = int(status_code or 0)
        self._consecutive_failures += 1
        self._diagnostics["consecutive_failures"] = self._consecutive_failures
        if status_code in {401, 403} or str(error).startswith("codex_auth_error:"):
            self._diagnostics["auth_errors"] = int(self._diagnostics["auth_errors"]) + 1
        if status_code == 429:
            self._diagnostics["rate_limit_errors"] = int(self._diagnostics["rate_limit_errors"]) + 1
        if status_code is not None and 500 <= status_code <= 599:
            self._diagnostics["server_errors"] = int(self._diagnostics["server_errors"]) + 1
        if self._consecutive_failures >= self.reliability.circuit_failure_threshold:
            was_open = self._circuit_open_until > time.monotonic()
            self._circuit_open_until = time.monotonic() + self.reliability.circuit_cooldown_s
            if not was_open:
                self._diagnostics["circuit_open_count"] = int(self._diagnostics["circuit_open_count"]) + 1
            self._diagnostics["circuit_open"] = True

    def _retry_delay(self, attempt: int, *, retry_after_s: float | None = None) -> float:
        if retry_after_s is not None:
            return max(0.0, float(retry_after_s))
        base = self.reliability.retry_initial_backoff_s * (2 ** max(0, attempt - 1))
        capped = min(base, self.reliability.retry_max_backoff_s)
        return max(0.0, capped + random.uniform(0.0, self.reliability.retry_jitter_s))

    @staticmethod
    def _parse_arguments(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                return {}
            try:
                payload = json.loads(text)
            except Exception:
                return {"raw": text}
            return payload if isinstance(payload, dict) else {"value": payload}
        return {}

    @classmethod
    def _parse_tool_calls(cls, message: dict[str, Any]) -> list[ToolCall]:
        rows = message.get("tool_calls")
        if not isinstance(rows, list):
            return []

        parsed: list[ToolCall] = []
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            fn = row.get("function")
            fn_payload = fn if isinstance(fn, dict) else {}
            name = str(fn_payload.get("name") or row.get("name") or "").strip()
            if not name:
                continue
            call_id = str(row.get("id") or f"call_{idx}")
            arguments = cls._parse_arguments(fn_payload.get("arguments", row.get("arguments", {})))
            parsed.append(ToolCall(id=call_id, name=name, arguments=arguments))
        return parsed

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        reasoning_effort: str | None = None,
    ) -> LLMResult:
        self._diagnostics["requests"] = int(self._diagnostics["requests"]) + 1
        if circuit_error := self._check_circuit():
            self._record_failure(error=circuit_error)
            raise RuntimeError(circuit_error)

        if not self.access_token.strip():
            error = "codex_auth_error:missing_access_token"
            self._record_failure(error=error, status_code=401)
            raise RuntimeError(error)

        headers = {"content-type": "application/json"}
        if self.access_token:
            headers["authorization"] = f"Bearer {self.access_token}"
        if self.account_id:
            headers["openai-organization"] = self.account_id

        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if max_tokens is not None:
            payload["max_tokens"] = max(1, int(max_tokens))
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if reasoning_effort is not None:
            payload["reasoning_effort"] = reasoning_effort
        if tools:
            payload["tools"] = [{"type": "function", "function": row} for row in tools]
            payload["tool_choice"] = "auto"

        attempts = self.reliability.retry_max_attempts
        url = f"{self.base_url}/chat/completions"

        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                message = data.get("choices", [{}])[0].get("message", {})
                text = str(message.get("content", "")).strip()
                tool_calls = self._parse_tool_calls(message)
                self._record_success()
                return LLMResult(text=text, model=self.model, tool_calls=tool_calls, metadata={"provider": "codex"})
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else None
                self._diagnostics["http_errors"] = int(self._diagnostics["http_errors"]) + 1
                should_retry = status is not None and (status == 429 or 500 <= status <= 599) and attempt < attempts
                retry_after_s = parse_retry_after_seconds(exc.response.headers.get("retry-after") if exc.response is not None else "")
                if should_retry:
                    self._diagnostics["retries"] = int(self._diagnostics["retries"]) + 1
                    await asyncio.sleep(self._retry_delay(attempt, retry_after_s=retry_after_s if status == 429 else None))
                    continue
                error = f"codex_http_error:{status}"
                self._record_failure(error=error, status_code=status)
                raise RuntimeError(error) from exc
            except httpx.TimeoutException as exc:
                self._diagnostics["timeouts"] = int(self._diagnostics["timeouts"]) + 1
                self._diagnostics["network_errors"] = int(self._diagnostics["network_errors"]) + 1
                if attempt < attempts:
                    self._diagnostics["retries"] = int(self._diagnostics["retries"]) + 1
                    await asyncio.sleep(self._retry_delay(attempt))
                    continue
                error = f"codex_network_error:{exc}"
                self._record_failure(error=error)
                raise RuntimeError(error) from exc
            except httpx.RequestError as exc:
                self._diagnostics["network_errors"] = int(self._diagnostics["network_errors"]) + 1
                if attempt < attempts:
                    self._diagnostics["retries"] = int(self._diagnostics["retries"]) + 1
                    await asyncio.sleep(self._retry_delay(attempt))
                    continue
                error = f"codex_network_error:{exc}"
                self._record_failure(error=error)
                raise RuntimeError(error) from exc

        error = "codex_429_exhausted"
        self._record_failure(error=error, status_code=429)
        raise RuntimeError(error)

    def get_default_model(self) -> str:
        return self.model
