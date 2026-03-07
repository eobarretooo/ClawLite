from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from clawlite.providers.litellm import LiteLLMProvider


class _AnthropicResponse:
    status_code = 200
    text = ""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "tool_use", "id": "tu_1", "name": "echo", "input": {"text": "ok"}},
            ]
        }


def test_litellm_provider_supports_anthropic_direct() -> None:
    async def _scenario() -> None:
        provider = LiteLLMProvider(
            base_url="https://api.anthropic.com/v1",
            api_key="sk-ant-1",
            model="claude-3-7-sonnet",
            provider_name="anthropic",
            openai_compatible=False,
        )

        post_mock = AsyncMock(side_effect=[_AnthropicResponse()])
        with patch("httpx.AsyncClient.post", new=post_mock):
            out = await provider.complete(
                messages=[
                    {"role": "system", "content": "be concise"},
                    {"role": "user", "content": "hi"},
                ],
                tools=[
                    {
                        "name": "echo",
                        "description": "echo",
                        "parameters": {
                            "type": "object",
                            "properties": {"text": {"type": "string"}},
                            "required": ["text"],
                        },
                        "arguments": {"type": "object", "properties": {}},
                    }
                ],
            )

        assert out.text == "hello"
        assert len(out.tool_calls) == 1
        assert out.tool_calls[0].name == "echo"
        sent_payload = post_mock.call_args.kwargs["json"]
        assert sent_payload["tools"][0]["input_schema"] == {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

    asyncio.run(_scenario())


def test_litellm_provider_supports_anthropic_compatible_provider() -> None:
    async def _scenario() -> None:
        provider = LiteLLMProvider(
            base_url="https://api.minimax.io/anthropic",
            api_key="mini-key",
            model="MiniMax-M2.5",
            provider_name="minimax",
            openai_compatible=False,
            native_transport="anthropic",
        )

        post_mock = AsyncMock(side_effect=[_AnthropicResponse()])
        with patch("httpx.AsyncClient.post", new=post_mock):
            out = await provider.complete(
                messages=[
                    {"role": "system", "content": "be concise"},
                    {"role": "user", "content": "hi"},
                ],
                tools=[],
            )

        assert out.text == "hello"
        assert out.metadata["provider"] == "minimax"
        assert post_mock.call_args.args[0] == "https://api.minimax.io/anthropic/messages"
        assert post_mock.call_args.kwargs["headers"]["x-api-key"] == "mini-key"

    asyncio.run(_scenario())


def test_litellm_provider_anthropic_invalid_content_returns_controlled_error() -> None:
    async def _scenario() -> None:
        provider = LiteLLMProvider(
            base_url="https://api.anthropic.com/v1",
            api_key="sk-ant-1",
            model="claude-3-7-sonnet",
            provider_name="anthropic",
            openai_compatible=False,
        )

        class _BadAnthropicResponse:
            status_code = 200
            text = ""

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"content": None}

        post_mock = AsyncMock(side_effect=[_BadAnthropicResponse()])
        with patch("httpx.AsyncClient.post", new=post_mock):
            try:
                await provider.complete(
                    messages=[{"role": "user", "content": "hi"}],
                    tools=[],
                )
            except RuntimeError as exc:
                assert str(exc) == "provider_response_invalid:missing_content"
            else:
                raise AssertionError("expected controlled provider error")

        diag = provider.diagnostics()
        assert diag["last_error"] == "provider_response_invalid:missing_content"
        assert diag["error_class_counts"]["unknown"] == 1

    asyncio.run(_scenario())
