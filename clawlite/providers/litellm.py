from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any

import httpx
from json_repair import loads as json_repair_loads

from clawlite.providers.base import LLMProvider, LLMResult, ToolCall
from clawlite.providers.reliability import QUOTA_429_SIGNALS, ReliabilitySettings, classify_provider_error, parse_retry_after_seconds


class LiteLLMProvider(LLMProvider):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        provider_name: str = "litellm",
        openai_compatible: bool = True,
        native_transport: str = "",
        allow_empty_api_key: bool = False,
        timeout: float = 30.0,
        extra_headers: dict[str, str] | None = None,
        retry_max_attempts: int = 3,
        retry_initial_backoff_s: float = 0.5,
        retry_max_backoff_s: float = 8.0,
        retry_jitter_s: float = 0.2,
        circuit_failure_threshold: int = 3,
        circuit_cooldown_s: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.provider_name = provider_name
        self.openai_compatible = openai_compatible
        resolved_transport = str(native_transport or "").strip().lower()
        if not openai_compatible and not resolved_transport and provider_name == "anthropic":
            resolved_transport = "anthropic"
        self.native_transport = resolved_transport
        self.allow_empty_api_key = bool(allow_empty_api_key)
        self.timeout = timeout
        self.extra_headers = dict(extra_headers or {})
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
            "provider": "litellm",
            "provider_name": self.provider_name,
            "model": self.model,
            "transport": "openai_compatible" if self.openai_compatible else (self.native_transport or "native"),
            "auth_optional": self.allow_empty_api_key,
            "counters": counters,
            **counters,
        }

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
        if status_code in {401, 403} or str(error).startswith("provider_auth_error:"):
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
        return f"provider_circuit_open:{self.provider_name}:{self.reliability.circuit_cooldown_s}"

    def _retry_delay(self, attempt: int, *, retry_after_s: float | None = None) -> float:
        if retry_after_s is not None:
            return max(0.0, float(retry_after_s))
        base = self.reliability.retry_initial_backoff_s * (2 ** max(0, attempt - 1))
        capped = min(base, self.reliability.retry_max_backoff_s)
        return max(0.0, capped + random.uniform(0.0, self.reliability.retry_jitter_s))

    @staticmethod
    def _extract_text(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            return "\n".join(parts).strip()
        return str(content or "").strip()

    @staticmethod
    def _error_payload(resp: httpx.Response | None) -> dict[str, Any] | None:
        if resp is None:
            return None
        try:
            payload = resp.json()
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    @classmethod
    def _error_detail(cls, resp: httpx.Response | None) -> str:
        if resp is None:
            return ""
        detail = ""
        payload = cls._error_payload(resp)

        if isinstance(payload, dict):
            if isinstance(payload.get("error"), dict):
                detail = str(payload["error"].get("message", "")).strip()
            if not detail:
                detail = str(payload.get("message", "") or payload.get("detail", "")).strip()

        if not detail:
            detail = (resp.text or "").strip()

        detail = " ".join(detail.split())
        return detail[:300]

    @classmethod
    def _is_hard_quota_429(cls, *, detail: str, resp: httpx.Response | None) -> bool:
        pieces: list[str] = []
        if detail:
            pieces.append(detail)

        payload = cls._error_payload(resp)
        if isinstance(payload, dict):
            error_obj = payload.get("error")
            if isinstance(error_obj, dict):
                for key in ("code", "type", "message"):
                    value = error_obj.get(key)
                    if value is not None:
                        pieces.append(str(value))
            for key in ("message", "detail", "code", "type"):
                value = payload.get(key)
                if value is not None:
                    pieces.append(str(value))

        haystack = " ".join(pieces).lower()
        if not haystack:
            return False
        return any(signal in haystack for signal in QUOTA_429_SIGNALS)

    @staticmethod
    def _parse_arguments(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                return {}
            try:
                payload = json_repair_loads(text)
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

    @staticmethod
    def _anthropic_messages(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        system_parts: list[str] = []
        converted: list[dict[str, Any]] = []

        for row in messages:
            role = str(row.get("role", "")).strip()
            content = row.get("content", "")

            if role == "system":
                text = LiteLLMProvider._extract_text(content)
                if text:
                    system_parts.append(text)
                continue

            if role == "assistant":
                assistant_blocks: list[dict[str, Any]] = []
                text = LiteLLMProvider._extract_text(content)
                if text:
                    assistant_blocks.append({"type": "text", "text": text})

                tool_calls = row.get("tool_calls")
                if isinstance(tool_calls, list):
                    for idx, call in enumerate(tool_calls):
                        if not isinstance(call, dict):
                            continue
                        fn = call.get("function") if isinstance(call.get("function"), dict) else call
                        name = str(fn.get("name") or "").strip()
                        if not name:
                            continue
                        arguments = LiteLLMProvider._parse_arguments(fn.get("arguments", {}))
                        call_id = str(call.get("id") or f"call_{idx}")
                        assistant_blocks.append(
                            {
                                "type": "tool_use",
                                "id": call_id,
                                "name": name,
                                "input": arguments,
                            }
                        )
                if assistant_blocks:
                    converted.append({"role": "assistant", "content": assistant_blocks})
                continue

            if role == "tool":
                tool_use_id = str(row.get("tool_call_id") or "").strip()
                if tool_use_id:
                    tool_text = LiteLLMProvider._extract_text(content)
                    converted.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tool_use_id,
                                    "content": tool_text,
                                }
                            ],
                        }
                    )
                continue

            user_text = LiteLLMProvider._extract_text(content)
            converted.append({"role": "user", "content": user_text})

        return "\n\n".join(part for part in system_parts if part).strip(), converted

    @staticmethod
    def _anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            name = str(tool.get("name") or "").strip()
            if not name:
                continue
            parameters = tool.get("parameters") if isinstance(tool.get("parameters"), dict) else None
            arguments = tool.get("arguments") if isinstance(tool.get("arguments"), dict) else None
            rows.append(
                {
                    "name": name,
                    "description": str(tool.get("description") or ""),
                    "input_schema": parameters or arguments or {"type": "object", "properties": {}},
                }
            )
        return rows

    async def _complete_anthropic(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        reasoning_effort: str | None = None,
    ) -> LLMResult:
        if not self.api_key.strip():
            error = f"provider_auth_error:missing_api_key:{self.provider_name}"
            self._record_failure(error=error, status_code=401)
            raise RuntimeError(error)

        if not self.base_url.strip():
            error = f"provider_config_error:missing_base_url:{self.provider_name}"
            self._record_failure(error=error)
            raise RuntimeError(error)

        system_text, anthropic_messages = self._anthropic_messages(messages)
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max(1, int(max_tokens)) if max_tokens is not None else 4096,
            "messages": anthropic_messages,
        }
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if system_text:
            payload["system"] = system_text
        anth_tools = self._anthropic_tools(tools or [])
        if anth_tools:
            payload["tools"] = anth_tools

        headers = {
            "content-type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        headers.update(self.extra_headers)

        url = f"{self.base_url}/messages"
        attempts = self.reliability.retry_max_attempts

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(1, attempts + 1):
                try:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()

                    parts = data.get("content")
                    text_parts: list[str] = []
                    tool_calls: list[ToolCall] = []
                    if isinstance(parts, list):
                        for idx, part in enumerate(parts):
                            if not isinstance(part, dict):
                                continue
                            if part.get("type") == "text":
                                text = str(part.get("text") or "").strip()
                                if text:
                                    text_parts.append(text)
                            if part.get("type") == "tool_use":
                                name = str(part.get("name") or "").strip()
                                if not name:
                                    continue
                                tool_calls.append(
                                    ToolCall(
                                        id=str(part.get("id") or f"tool_{idx}"),
                                        name=name,
                                        arguments=part.get("input") if isinstance(part.get("input"), dict) else {},
                                    )
                                )

                    self._record_success()
                    return LLMResult(
                        text="\n".join(text_parts).strip(),
                        model=self.model,
                        tool_calls=tool_calls,
                        metadata={"provider": self.provider_name},
                    )
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code if exc.response is not None else None
                    detail = self._error_detail(exc.response)
                    self._diagnostics["http_errors"] = int(self._diagnostics["http_errors"]) + 1
                    hard_quota = status == 429 and self._is_hard_quota_429(detail=detail, resp=exc.response)
                    retry_after_s = parse_retry_after_seconds(exc.response.headers.get("retry-after") if exc.response is not None else "")
                    should_retry = (
                        status is not None
                        and (status == 429 or 500 <= status <= 599)
                        and not hard_quota
                        and attempt < attempts
                    )
                    if should_retry:
                        self._diagnostics["retries"] = int(self._diagnostics["retries"]) + 1
                        await asyncio.sleep(self._retry_delay(attempt, retry_after_s=retry_after_s if status == 429 else None))
                        continue
                    if detail:
                        error = f"provider_http_error:{status}:{detail}"
                        self._record_failure(error=error, status_code=status)
                        raise RuntimeError(error) from exc
                    error = f"provider_http_error:{status}"
                    self._record_failure(error=error, status_code=status)
                    raise RuntimeError(error) from exc
                except httpx.TimeoutException as exc:
                    self._diagnostics["timeouts"] = int(self._diagnostics["timeouts"]) + 1
                    self._diagnostics["network_errors"] = int(self._diagnostics["network_errors"]) + 1
                    if attempt < attempts:
                        self._diagnostics["retries"] = int(self._diagnostics["retries"]) + 1
                        await asyncio.sleep(self._retry_delay(attempt))
                        continue
                    error = f"provider_network_error:{exc}"
                    self._record_failure(error=error)
                    raise RuntimeError(error) from exc
                except httpx.RequestError as exc:
                    self._diagnostics["network_errors"] = int(self._diagnostics["network_errors"]) + 1
                    if attempt < attempts:
                        self._diagnostics["retries"] = int(self._diagnostics["retries"]) + 1
                        await asyncio.sleep(self._retry_delay(attempt))
                        continue
                    error = f"provider_network_error:{exc}"
                    self._record_failure(error=error)
                    raise RuntimeError(error) from exc

        error = "provider_429_exhausted"
        self._record_failure(error=error, status_code=429)
        raise RuntimeError(error)

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

        if not self.openai_compatible and self.native_transport == "anthropic":
            return await self._complete_anthropic(
                messages=messages,
                tools=tools,
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
            )

        if not self.openai_compatible:
            error = (
                f"provider_config_error:provider '{self.provider_name}' is not OpenAI-compatible in ClawLite. "
                "Use an OpenAI-compatible gateway/base_url."
            )
            self._record_failure(error=error)
            raise RuntimeError(error)

        if not self.api_key.strip() and not self.allow_empty_api_key:
            error = f"provider_auth_error:missing_api_key:{self.provider_name}"
            self._record_failure(error=error, status_code=401)
            raise RuntimeError(error)

        if not self.base_url.strip():
            error = f"provider_config_error:missing_base_url:{self.provider_name}"
            self._record_failure(error=error)
            raise RuntimeError(error)

        url = f"{self.base_url}/chat/completions"
        headers = {"content-type": "application/json"}
        if self.api_key.strip():
            headers["authorization"] = f"Bearer {self.api_key}"
        headers.update(self.extra_headers)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max(1, int(max_tokens))
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if reasoning_effort is not None and self.provider_name in {"openai", "openai_codex"}:
            payload["reasoning_effort"] = reasoning_effort
        if tools:
            payload["tools"] = [{"type": "function", "function": row} for row in tools]
            payload["tool_choice"] = "auto"

        attempts = self.reliability.retry_max_attempts

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(1, attempts + 1):
                try:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    message = data.get("choices", [{}])[0].get("message", {})
                    text = self._extract_text(message.get("content", ""))
                    tool_calls = self._parse_tool_calls(message)
                    self._record_success()
                    return LLMResult(text=text, model=self.model, tool_calls=tool_calls, metadata={"provider": "litellm"})
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code if exc.response is not None else None
                    detail = self._error_detail(exc.response)
                    self._diagnostics["http_errors"] = int(self._diagnostics["http_errors"]) + 1
                    hard_quota = status == 429 and self._is_hard_quota_429(detail=detail, resp=exc.response)
                    retry_after_s = parse_retry_after_seconds(exc.response.headers.get("retry-after") if exc.response is not None else "")
                    should_retry = (
                        status is not None
                        and (status == 429 or 500 <= status <= 599)
                        and not hard_quota
                        and attempt < attempts
                    )
                    if should_retry:
                        self._diagnostics["retries"] = int(self._diagnostics["retries"]) + 1
                        await asyncio.sleep(self._retry_delay(attempt, retry_after_s=retry_after_s if status == 429 else None))
                        continue
                    if detail:
                        error = f"provider_http_error:{status}:{detail}"
                        self._record_failure(error=error, status_code=status)
                        raise RuntimeError(error) from exc
                    error = f"provider_http_error:{status}"
                    self._record_failure(error=error, status_code=status)
                    raise RuntimeError(error) from exc
                except httpx.TimeoutException as exc:
                    self._diagnostics["timeouts"] = int(self._diagnostics["timeouts"]) + 1
                    self._diagnostics["network_errors"] = int(self._diagnostics["network_errors"]) + 1
                    if attempt < attempts:
                        self._diagnostics["retries"] = int(self._diagnostics["retries"]) + 1
                        await asyncio.sleep(self._retry_delay(attempt))
                        continue
                    error = f"provider_network_error:{exc}"
                    self._record_failure(error=error)
                    raise RuntimeError(error) from exc
                except httpx.RequestError as exc:
                    self._diagnostics["network_errors"] = int(self._diagnostics["network_errors"]) + 1
                    if attempt < attempts:
                        self._diagnostics["retries"] = int(self._diagnostics["retries"]) + 1
                        await asyncio.sleep(self._retry_delay(attempt))
                        continue
                    error = f"provider_network_error:{exc}"
                    self._record_failure(error=error)
                    raise RuntimeError(error) from exc

        error = "provider_429_exhausted"
        self._record_failure(error=error, status_code=429)
        raise RuntimeError(error)

    def get_default_model(self) -> str:
        return self.model
