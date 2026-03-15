"""Tests for centralized timeout middleware in ToolRegistry."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from clawlite.tools.base import Tool, ToolContext
from clawlite.tools.base import ToolError, ToolTimeoutError
from clawlite.tools.registry import ToolRegistry


class SlowTool(Tool):
    name = "slow_tool"
    description = "Sleeps forever."

    def args_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        await asyncio.sleep(999)
        return "done"


class FastTool(Tool):
    name = "fast_tool"
    description = "Returns immediately."

    def args_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        return "fast_result"


class DefaultTimeoutTool(Tool):
    name = "default_timeout_tool"
    description = "Has class-level default_timeout_s."
    default_timeout_s = 0.05

    def args_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        await asyncio.sleep(999)
        return "never"


@pytest.mark.asyncio
async def test_registry_timeout_raises_tool_timeout_error():
    reg = ToolRegistry(default_timeout_s=0.05)
    reg.register(SlowTool())
    with pytest.raises(ToolTimeoutError) as exc_info:
        await reg.execute("slow_tool", {}, session_id="s1")
    assert "slow_tool" in str(exc_info.value)


@pytest.mark.asyncio
async def test_registry_tool_level_timeout_override():
    """argument-level timeout overrides global default."""
    reg = ToolRegistry(default_timeout_s=10.0)
    reg.register(SlowTool())
    with pytest.raises(ToolTimeoutError) as exc_info:
        await reg.execute("slow_tool", {"timeout": 0.05}, session_id="s1")
    assert exc_info.value.timeout_s == pytest.approx(0.05, abs=0.01)


@pytest.mark.asyncio
async def test_registry_tool_class_default_timeout():
    """tool.default_timeout_s used when no argument override."""
    reg = ToolRegistry(default_timeout_s=10.0)
    reg.register(DefaultTimeoutTool())
    with pytest.raises(ToolTimeoutError) as exc_info:
        await reg.execute("default_timeout_tool", {}, session_id="s1")
    assert exc_info.value.timeout_s == pytest.approx(0.05, abs=0.01)


@pytest.mark.asyncio
async def test_fast_tool_completes_within_timeout():
    reg = ToolRegistry(default_timeout_s=5.0)
    reg.register(FastTool())
    result = await reg.execute("fast_tool", {}, session_id="s1")
    assert result == "fast_result"


@pytest.mark.asyncio
async def test_unknown_tool_raises_tool_error():
    reg = ToolRegistry()
    with pytest.raises(ToolError) as exc_info:
        await reg.execute("nonexistent", {}, session_id="s1")
    assert exc_info.value.code == "not_found"


@pytest.mark.asyncio
async def test_tool_error_has_correct_fields():
    err = ToolTimeoutError("my_tool", 30.0)
    assert err.tool_name == "my_tool"
    assert err.timeout_s == 30.0
    assert err.recoverable is True
    assert "my_tool" in str(err)
    assert "30.0s" in str(err)
