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
                tools=[{"name": "echo", "description": "echo", "arguments": {"type": "object", "properties": {}}}],
            )

        assert out.text == "hello"
        assert len(out.tool_calls) == 1
        assert out.tool_calls[0].name == "echo"

    asyncio.run(_scenario())
