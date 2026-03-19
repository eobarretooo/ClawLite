"""Tests for streaming degraded recovery in LiteLLMProvider."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clawlite.core.engine import ProviderChunk
from clawlite.providers.litellm import LiteLLMProvider


def _make_provider() -> LiteLLMProvider:
    return LiteLLMProvider(
        base_url="http://fake.local",
        api_key="test-key",
        model="test-model",
    )


async def _collect_chunks(gen):
    chunks = []
    async for chunk in gen:
        chunks.append(chunk)
    return chunks


@pytest.mark.asyncio
async def test_stream_degraded_recovery_on_mid_stream_error():
    """Stream that fails after yielding some chunks should return degraded=True chunk."""
    from clawlite.core.engine import ProviderChunk

    provider = _make_provider()

    async def fake_aiter_lines():
        # Yield some real SSE lines then raise mid-stream
        lines = [
            'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":" world"},"finish_reason":null}]}',
        ]
        for line in lines:
            yield line
        raise ConnectionResetError("connection dropped at chunk 2")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.aiter_lines = fake_aiter_lines

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_stream_ctx)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("clawlite.providers.litellm.httpx.AsyncClient", return_value=mock_client):
        chunks = await _collect_chunks(provider.stream(messages=[{"role": "user", "content": "hi"}]))

    # Should have received the partial content chunks + a final degraded chunk
    assert len(chunks) >= 2
    final = chunks[-1]
    assert final.done is True
    assert final.degraded is True
    assert "Hello world" in final.accumulated


@pytest.mark.asyncio
async def test_stream_no_degraded_on_clean_finish():
    """Normal stream completion should not set degraded=True."""
    from clawlite.core.engine import ProviderChunk

    provider = _make_provider()

    async def fake_aiter_lines():
        yield 'data: {"choices":[{"delta":{"content":"OK"},"finish_reason":null}]}'
        yield 'data: {"choices":[{"delta":{"content":""},"finish_reason":"stop"}]}'

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.aiter_lines = fake_aiter_lines

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_stream_ctx)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("clawlite.providers.litellm.httpx.AsyncClient", return_value=mock_client):
        chunks = await _collect_chunks(provider.stream(messages=[{"role": "user", "content": "hi"}]))

    final = chunks[-1]
    assert final.done is True
    assert final.degraded is False


@pytest.mark.asyncio
async def test_stream_emits_full_run_signal_for_pre_text_tool_calls():
    provider = _make_provider()

    async def fake_aiter_lines():
        yield (
            'data: {"choices":[{"delta":{"tool_calls":[{"id":"call_1","type":"function","function":{"name":"web_search","arguments":"{\\"query\\":\\"docs\\"}"}}]},"finish_reason":null}]}'
        )
        yield 'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}'

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.aiter_lines = fake_aiter_lines

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_stream_ctx)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("clawlite.providers.litellm.httpx.AsyncClient", return_value=mock_client):
        chunks = await _collect_chunks(
            provider.stream(
                messages=[{"role": "user", "content": "hi"}],
                tools=[{"name": "web_search", "description": "search", "arguments": {"query": "string"}}],
            )
        )

    assert chunks == [provider_chunk := chunks[0]]
    assert provider_chunk.done is True
    assert provider_chunk.requires_full_run is True
    assert provider_chunk.accumulated == ""


@pytest.mark.asyncio
async def test_stream_emits_full_run_signal_after_whitespace_only_prelude() -> None:
    provider = _make_provider()

    async def fake_aiter_lines():
        yield 'data: {"choices":[{"delta":{"content":" \\n\\t"},"finish_reason":null}]}'
        yield (
            'data: {"choices":[{"delta":{"tool_calls":[{"id":"call_1","type":"function","function":{"name":"web_search","arguments":"{\\"query\\":\\"docs\\"}"}}]},"finish_reason":null}]}'
        )
        yield 'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}'

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.aiter_lines = fake_aiter_lines

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_stream_ctx)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("clawlite.providers.litellm.httpx.AsyncClient", return_value=mock_client):
        chunks = await _collect_chunks(
            provider.stream(
                messages=[{"role": "user", "content": "hi"}],
                tools=[{"name": "web_search", "description": "search", "arguments": {"query": "string"}}],
            )
        )

    assert chunks == [
        ProviderChunk(text=" \n\t", accumulated=" \n\t", done=False),
        ProviderChunk(text="", accumulated="", done=True, requires_full_run=True),
    ]


@pytest.mark.asyncio
async def test_stream_error_before_any_chunks_propagates_as_error_chunk():
    """Error before any content yields error chunk without degraded."""
    provider = _make_provider()

    async def fake_aiter_lines():
        raise ConnectionResetError("immediate failure")
        yield  # make it an async generator

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.aiter_lines = fake_aiter_lines

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_stream_ctx)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("clawlite.providers.litellm.httpx.AsyncClient", return_value=mock_client):
        chunks = await _collect_chunks(provider.stream(messages=[{"role": "user", "content": "hi"}]))

    final = chunks[-1]
    assert final.done is True
    # No content accumulated, so should NOT be degraded — should be error
    assert final.degraded is False
    assert final.error is not None


@pytest.mark.asyncio
async def test_stream_refreshes_oauth_once_on_401_before_emitting_chunks():
    provider = LiteLLMProvider(
        base_url="http://fake.local",
        api_key="stale-token",
        model="test-model",
        provider_name="qwen_oauth",
        oauth_refresh_callback=AsyncMock(return_value={"access_token": "fresh-token"}),
    )

    async def refreshed_aiter_lines():
        yield 'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}'

    unauthorized_response = MagicMock()
    unauthorized_response.status_code = 401
    unauthorized_response.headers = {}
    unauthorized_response.text = "expired"
    request = __import__("httpx").Request("POST", "http://fake.local/chat/completions")
    response = __import__("httpx").Response(401, request=request, json={"error": {"message": "expired"}})
    unauthorized_response.raise_for_status = MagicMock(side_effect=__import__("httpx").HTTPStatusError("err", request=request, response=response))

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.raise_for_status = MagicMock()
    ok_response.aiter_lines = refreshed_aiter_lines

    unauthorized_ctx = MagicMock()
    unauthorized_ctx.__aenter__ = AsyncMock(return_value=unauthorized_response)
    unauthorized_ctx.__aexit__ = AsyncMock(return_value=False)

    ok_ctx = MagicMock()
    ok_ctx.__aenter__ = AsyncMock(return_value=ok_response)
    ok_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(side_effect=[unauthorized_ctx, ok_ctx])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("clawlite.providers.litellm.httpx.AsyncClient", return_value=mock_client):
        chunks = await _collect_chunks(provider.stream(messages=[{"role": "user", "content": "hi"}]))

    assert provider.api_key == "fresh-token"
    assert chunks[-1].done is True
    assert chunks[-1].accumulated == "ok"
