"""Tests for ToolResultCache and cacheable tool integration."""
from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from clawlite.tools.base import Tool, ToolContext
from clawlite.tools.registry import ToolRegistry, ToolResultCache


class CacheableTool(Tool):
    name = "cacheable_tool"
    description = "Cacheable."
    cacheable = True

    def __init__(self) -> None:
        self.call_count = 0

    def args_schema(self) -> dict:
        return {"type": "object", "properties": {"key": {"type": "string"}}}

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        self.call_count += 1
        return f"result_{arguments.get('key', '')}"


class NonCacheableTool(Tool):
    name = "non_cacheable_tool"
    description = "Not cacheable."
    cacheable = False

    def __init__(self) -> None:
        self.call_count = 0

    def args_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        self.call_count += 1
        return "result"


@pytest.mark.asyncio
async def test_cacheable_tool_second_call_uses_cache():
    reg = ToolRegistry(default_timeout_s=5.0)
    tool = CacheableTool()
    reg.register(tool)

    r1 = await reg.execute("cacheable_tool", {"key": "x"}, session_id="s1")
    r2 = await reg.execute("cacheable_tool", {"key": "x"}, session_id="s1")

    assert r1 == r2 == "result_x"
    assert tool.call_count == 1  # second call was cached


@pytest.mark.asyncio
async def test_cacheable_tool_different_args_not_cached():
    reg = ToolRegistry(default_timeout_s=5.0)
    tool = CacheableTool()
    reg.register(tool)

    r1 = await reg.execute("cacheable_tool", {"key": "a"}, session_id="s1")
    r2 = await reg.execute("cacheable_tool", {"key": "b"}, session_id="s1")

    assert r1 == "result_a"
    assert r2 == "result_b"
    assert tool.call_count == 2


@pytest.mark.asyncio
async def test_non_cacheable_tool_always_calls_run():
    reg = ToolRegistry(default_timeout_s=5.0)
    tool = NonCacheableTool()
    reg.register(tool)

    await reg.execute("non_cacheable_tool", {}, session_id="s1")
    await reg.execute("non_cacheable_tool", {}, session_id="s1")

    assert tool.call_count == 2


def test_cache_ttl_expiry():
    cache = ToolResultCache()
    cache.TTL_S = 0.01  # type: ignore[attr-defined]
    # Patch TTL on class for this test
    original_ttl = ToolResultCache.TTL_S
    ToolResultCache.TTL_S = 0.01
    try:
        cache.set("tool", {"k": "v"}, "value")
        assert cache.get("tool", {"k": "v"}) == "value"
        time.sleep(0.05)
        assert cache.get("tool", {"k": "v"}) is None
    finally:
        ToolResultCache.TTL_S = original_ttl


def test_cache_lru_eviction():
    cache = ToolResultCache()
    # Temporarily reduce max entries
    original_max = ToolResultCache.MAX_ENTRIES
    ToolResultCache.MAX_ENTRIES = 3
    try:
        cache.set("t", {"k": "1"}, "v1")
        cache.set("t", {"k": "2"}, "v2")
        cache.set("t", {"k": "3"}, "v3")
        cache.set("t", {"k": "4"}, "v4")  # evicts k=1
        assert cache.get("t", {"k": "1"}) is None
        assert cache.get("t", {"k": "4"}) == "v4"
    finally:
        ToolResultCache.MAX_ENTRIES = original_max


def test_cache_key_is_consistent():
    cache = ToolResultCache()
    k1 = cache._key("tool", {"b": 2, "a": 1})
    k2 = cache._key("tool", {"a": 1, "b": 2})
    assert k1 == k2  # dict key order doesn't matter
