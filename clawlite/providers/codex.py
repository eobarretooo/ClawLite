from __future__ import annotations

import asyncio
import json
import os
import random
import time
from typing import Any

import httpx
from json_repair import loads as json_repair_loads

from clawlite.providers.base import LLMProvider, LLMResult, ToolCall
from clawlite.providers.reliability import ReliabilitySettings, classify_provider_error, parse_retry_after_seconds


CODEX_DEFAULT_BASE_URL = "https://chatgpt.com/backend-api"
CODEX_DEFAULT_INSTRUCTIONS = "You are a helpful and concise assistant."


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
        self.base_url = (base_url or os.getenv("CLAWLITE_CODEX_BASE_URL", CODEX_DEFAULT_BASE_URL)).rstrip("/")
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
            "transport": "codex_responses" if self._uses_responses_api() else "openai_compatible",
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
                payload = json_repair_loads(text)
            except Exception:
                return {"raw": text}
            return payload if isinstance(payload, dict) else {"value": payload}
        return {}

    @staticmethod
    def _extract_text(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                part_type = str(item.get("type") or "").strip().lower()
                if part_type not in {"text", "input_text", "output_text"}:
                    continue
                text = str(item.get("text") or "").strip()
                if text:
                    parts.append(text)
            return "\n".join(parts).strip()
        return str(content or "").strip()

    @staticmethod
    def _response_error_detail(resp: httpx.Response | None) -> str:
        if resp is None:
            return ""
        detail = ""
        try:
            payload = resp.json()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            error_payload = payload.get("error")
            if isinstance(error_payload, dict):
                detail = str(error_payload.get("message", "") or error_payload.get("detail", "")).strip()
            if not detail:
                detail = str(payload.get("message", "") or payload.get("detail", "") or payload.get("error", "")).strip()
        if not detail:
            detail = (resp.text or "").strip()
        return " ".join(detail.split())[:300]

    @staticmethod
    def _uses_responses_api_base(base_url: str) -> bool:
        normalized = str(base_url or "").strip().rstrip("/").lower()
        return (
            "chatgpt.com/backend-api" in normalized
            or normalized.endswith("/codex/responses")
            or normalized.endswith("/responses")
        )

    def _uses_responses_api(self) -> bool:
        return self._uses_responses_api_base(self.base_url)

    @staticmethod
    def _api_model_name(model: str) -> str:
        normalized = str(model or "").strip()
        if "/" in normalized:
            return normalized.split("/", 1)[1].strip() or normalized
        return normalized

    @staticmethod
    def _responses_url(base_url: str) -> str:
        normalized = str(base_url or "").strip().rstrip("/")
        lowered = normalized.lower()
        if lowered.endswith("/codex/responses") or lowered.endswith("/responses"):
            return normalized
        if "chatgpt.com/backend-api" in lowered:
            return f"{normalized}/codex/responses"
        return f"{normalized}/responses"

    @staticmethod
    def _responses_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw in tools or []:
            if not isinstance(raw, dict):
                continue
            row_type = str(raw.get("type") or "").strip().lower()
            if row_type == "function" and isinstance(raw.get("function"), dict):
                raw = dict(raw.get("function") or {})
                row_type = "function"
            if row_type == "function" and str(raw.get("name") or "").strip():
                item = dict(raw)
                item.setdefault("strict", False)
                rows.append(item)
                continue

            name = str(raw.get("name") or "").strip()
            if not name:
                continue
            parameters = raw.get("parameters")
            if not isinstance(parameters, dict):
                parameters = {"type": "object", "properties": {}}
            rows.append(
                {
                    "type": "function",
                    "name": name,
                    "description": str(raw.get("description") or "").strip(),
                    "strict": False,
                    "parameters": parameters,
                }
            )
        return rows

    @classmethod
    def _responses_input(cls, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in messages:
            role = str(row.get("role", "") or "").strip().lower()
            content = row.get("content", "")
            if role in {"system", "developer"}:
                continue

            if role == "user":
                text = cls._extract_text(content)
                if not text:
                    continue
                rows.append(
                    {
                        "type": "message",
                        "role": role,
                        "content": [{"type": "input_text", "text": text}],
                    }
                )
                continue

            if role == "assistant":
                text = cls._extract_text(content)
                if text:
                    rows.append(
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": text}],
                        }
                    )

                tool_calls = row.get("tool_calls")
                if isinstance(tool_calls, list):
                    for idx, call in enumerate(tool_calls):
                        if not isinstance(call, dict):
                            continue
                        fn = call.get("function") if isinstance(call.get("function"), dict) else call
                        name = str(fn.get("name") or "").strip()
                        if not name:
                            continue
                        call_id = str(call.get("id") or f"call_{idx}")
                        arguments = fn.get("arguments", {})
                        if isinstance(arguments, dict):
                            arguments_raw = json.dumps(arguments)
                        else:
                            arguments_raw = str(arguments or "")
                        rows.append(
                            {
                                "type": "function_call",
                                "call_id": call_id,
                                "name": name,
                                "arguments": arguments_raw,
                            }
                        )
                continue

            if role == "tool":
                call_id = str(row.get("tool_call_id") or "").strip()
                if not call_id:
                    continue
                rows.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": cls._extract_text(content),
                    }
                )
        return rows

    @classmethod
    def _responses_instructions(cls, messages: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for row in messages:
            role = str(row.get("role", "") or "").strip().lower()
            if role not in {"system", "developer"}:
                continue
            text = cls._extract_text(row.get("content", ""))
            if text:
                parts.append(text)
        return "\n\n".join(parts).strip()

    @classmethod
    def _parse_responses_tool_calls(cls, payload: dict[str, Any]) -> list[ToolCall]:
        rows = payload.get("output")
        if not isinstance(rows, list):
            return []

        parsed: list[ToolCall] = []
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            if str(row.get("type") or "").strip().lower() != "function_call":
                continue
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            parsed.append(
                ToolCall(
                    id=str(row.get("call_id") or row.get("id") or f"call_{idx}"),
                    name=name,
                    arguments=cls._parse_arguments(row.get("arguments", {})),
                )
            )
        return parsed

    @classmethod
    def _extract_responses_text(cls, payload: dict[str, Any]) -> str:
        direct = str(payload.get("output_text") or "").strip()
        if direct:
            return direct

        rows = payload.get("output")
        if not isinstance(rows, list):
            return ""

        parts: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_type = str(row.get("type") or "").strip().lower()
            if row_type == "message":
                content = row.get("content")
                if isinstance(content, list):
                    for part in content:
                        if not isinstance(part, dict):
                            continue
                        if str(part.get("type") or "").strip().lower() != "output_text":
                            continue
                        text = str(part.get("text") or "").strip()
                        if text:
                            parts.append(text)
                elif isinstance(content, str) and content.strip():
                    parts.append(content.strip())
            elif row_type == "output_text":
                text = str(row.get("text") or "").strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()

    @staticmethod
    def _responses_event_error_detail(payload: dict[str, Any]) -> str:
        detail = ""
        response = payload.get("response")
        if isinstance(response, dict):
            error_payload = response.get("error")
            if isinstance(error_payload, dict):
                detail = str(
                    error_payload.get("message", "")
                    or error_payload.get("detail", "")
                    or error_payload.get("code", "")
                    or error_payload.get("type", "")
                ).strip()
            if not detail:
                detail = str(response.get("message", "") or response.get("detail", "")).strip()
        if not detail:
            detail = str(payload.get("message", "") or payload.get("detail", "") or payload.get("error", "")).strip()
        return " ".join(detail.split())[:300]

    @classmethod
    def _parse_responses_sse_text(cls, raw_text: str) -> dict[str, Any]:
        output_items: list[dict[str, Any]] = []
        text_deltas: list[str] = []
        event_name = ""
        data_lines: list[str] = []

        def _flush_event(current_event: str, current_lines: list[str]) -> None:
            payload_raw = "\n".join(current_lines).strip()
            if not payload_raw or payload_raw == "[DONE]":
                return
            try:
                payload = json.loads(payload_raw)
            except Exception:
                return
            if not isinstance(payload, dict):
                return
            kind = str(payload.get("type") or current_event or "").strip().lower()
            if kind == "response.output_text.delta":
                delta = str(payload.get("delta") or "")
                if delta:
                    text_deltas.append(delta)
                return
            if kind == "response.output_item.done":
                item = payload.get("item")
                if isinstance(item, dict):
                    output_items.append(item)
                return
            if kind in {"response.failed", "response.incomplete", "error"}:
                detail = cls._responses_event_error_detail(payload) or kind
                raise RuntimeError(f"codex_stream_error:{detail}")

        for line in str(raw_text or "").splitlines():
            current = line.rstrip("\r")
            if not current:
                _flush_event(event_name, data_lines)
                event_name = ""
                data_lines = []
                continue
            if current.startswith(":"):
                continue
            if current.startswith("event:"):
                event_name = current[6:].strip()
                continue
            if current.startswith("data:"):
                data_lines.append(current[5:].lstrip())
        if data_lines:
            _flush_event(event_name, data_lines)

        payload: dict[str, Any] = {"output": output_items}
        if not output_items or not cls._extract_responses_text({"output": output_items}):
            output_text = "".join(text_deltas).strip()
            if output_text:
                payload["output_text"] = output_text
        return payload

    @classmethod
    def _decode_responses_payload(cls, response: httpx.Response) -> dict[str, Any]:
        content_type = str(response.headers.get("content-type", "") or "").lower()
        if "text/event-stream" in content_type:
            return cls._parse_responses_sse_text(response.text)
        data = response.json()
        if isinstance(data, dict):
            return data
        raise RuntimeError("codex_response_invalid:malformed_payload")

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

        headers = {"Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        if self.account_id and not self._uses_responses_api():
            headers["OpenAI-Organization"] = self.account_id

        attempts = self.reliability.retry_max_attempts
        use_responses_api = self._uses_responses_api()
        api_model = self._api_model_name(self.model)
        if use_responses_api:
            instructions = self._responses_instructions(messages) or CODEX_DEFAULT_INSTRUCTIONS
            payload = {
                "model": api_model,
                "input": self._responses_input(messages),
                "instructions": instructions,
                "tools": self._responses_tools(tools),
                "tool_choice": "auto",
                "parallel_tool_calls": bool(tools),
                "store": False,
                "stream": True,
            }
            if max_tokens is not None:
                payload["max_output_tokens"] = max(1, int(max_tokens))
            if temperature is not None:
                payload["temperature"] = float(temperature)
            if reasoning_effort is not None:
                payload["reasoning"] = {"effort": reasoning_effort}
            headers["Accept"] = "text/event-stream"
            url = self._responses_url(self.base_url)
        else:
            payload = {"model": api_model, "messages": messages}
            if max_tokens is not None:
                payload["max_tokens"] = max(1, int(max_tokens))
            if temperature is not None:
                payload["temperature"] = float(temperature)
            if reasoning_effort is not None:
                payload["reasoning_effort"] = reasoning_effort
            if tools:
                payload["tools"] = [{"type": "function", "function": row} for row in tools]
                payload["tool_choice"] = "auto"
            url = f"{self.base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(1, attempts + 1):
                try:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    if use_responses_api:
                        data = self._decode_responses_payload(response)
                        text = self._extract_responses_text(data)
                        tool_calls = self._parse_responses_tool_calls(data)
                    else:
                        data = response.json()
                        if not isinstance(data, dict):
                            raise RuntimeError("codex_response_invalid:malformed_payload")
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
                    detail = self._response_error_detail(exc.response)
                    error = f"codex_http_error:{status}"
                    if detail:
                        error = f"{error}:{detail}"
                    self._record_failure(error=error, status_code=status)
                    raise RuntimeError(error) from exc
                except RuntimeError as exc:
                    self._record_failure(error=str(exc))
                    raise
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
