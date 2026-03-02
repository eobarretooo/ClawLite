from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx
from json_repair import loads as json_repair_loads

from clawlite.providers.base import LLMProvider, LLMResult, ToolCall


class LiteLLMProvider(LLMProvider):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        provider_name: str = "litellm",
        openai_compatible: bool = True,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.provider_name = provider_name
        self.openai_compatible = openai_compatible
        self.timeout = timeout

    @staticmethod
    def _max_attempts() -> int:
        raw = os.getenv("CLAWLITE_PROVIDER_429_MAX_ATTEMPTS", "3").strip()
        try:
            value = int(raw)
        except ValueError:
            value = 3
        return max(1, value)

    @staticmethod
    def _wait_seconds() -> float:
        raw = os.getenv("CLAWLITE_PROVIDER_429_WAIT_SECONDS", "60").strip()
        try:
            value = float(raw)
        except ValueError:
            value = 60.0
        return max(0.0, value)

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

    async def complete(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResult:
        if not self.openai_compatible:
            raise RuntimeError(
                f"provider_config_error:provider '{self.provider_name}' is not OpenAI-compatible in ClawLite. "
                "Use an OpenAI-compatible gateway/base_url."
            )

        if not self.api_key.strip():
            raise RuntimeError(f"provider_auth_error:missing_api_key:{self.provider_name}")

        if not self.base_url.strip():
            raise RuntimeError(f"provider_config_error:missing_base_url:{self.provider_name}")

        url = f"{self.base_url}/chat/completions"
        headers = {"content-type": "application/json"}
        headers["authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": row} for row in tools]
            payload["tool_choice"] = "auto"

        attempts = self._max_attempts()
        wait_seconds = self._wait_seconds()

        def _error_detail(resp: httpx.Response | None) -> str:
            if resp is None:
                return ""
            detail = ""
            try:
                payload = resp.json()
            except Exception:
                payload = None

            if isinstance(payload, dict):
                if isinstance(payload.get("error"), dict):
                    detail = str(payload["error"].get("message", "")).strip()
                if not detail:
                    detail = str(payload.get("message", "") or payload.get("detail", "")).strip()

            if not detail:
                detail = (resp.text or "").strip()

            detail = " ".join(detail.split())
            return detail[:300]

        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                message = data.get("choices", [{}])[0].get("message", {})
                text = self._extract_text(message.get("content", ""))
                tool_calls = self._parse_tool_calls(message)
                return LLMResult(text=text, model=self.model, tool_calls=tool_calls, metadata={"provider": "litellm"})
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status == 429 and attempt < attempts:
                    await asyncio.sleep(wait_seconds)
                    continue
                detail = _error_detail(exc.response)
                if detail:
                    raise RuntimeError(f"provider_http_error:{status}:{detail}") from exc
                raise RuntimeError(f"provider_http_error:{status}") from exc
            except httpx.RequestError as exc:
                raise RuntimeError(f"provider_network_error:{exc}") from exc

        raise RuntimeError("provider_429_exhausted")
