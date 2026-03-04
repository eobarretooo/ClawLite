from __future__ import annotations

import asyncio

from clawlite.config.schema import ToolSafetyPolicyConfig
from clawlite.tools.base import Tool, ToolContext
from clawlite.tools.registry import ToolRegistry


class EchoTool(Tool):
    name = "echo"
    description = "echo"

    def args_schema(self) -> dict:
        return {"type": "object", "properties": {"text": {"type": "string"}}}

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        return str(arguments.get("text", ""))


class ExecLikeTool(Tool):
    name = "exec"
    description = "exec"

    def args_schema(self) -> dict:
        return {"type": "object", "properties": {"command": {"type": "string"}}}

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        return f"channel={ctx.channel};user={ctx.user_id}"


def test_tool_registry_execute() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(EchoTool())
        out = await reg.execute("echo", {"text": "ok"}, session_id="s")
        assert out == "ok"

    asyncio.run(_scenario())


def test_tool_registry_blocks_risky_tools_for_blocked_channels() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=["exec"],
                blocked_channels=["telegram"],
                allowed_channels=[],
            )
        )
        reg.register(ExecLikeTool())
        try:
            await reg.execute("exec", {"command": "id"}, session_id="telegram:1", channel="telegram", user_id="1")
            raise AssertionError("expected safety policy block")
        except RuntimeError as exc:
            assert str(exc) == "tool_blocked_by_safety_policy:exec:telegram"

    asyncio.run(_scenario())


def test_tool_registry_allows_risky_tools_for_cli_channel() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(ExecLikeTool())
        out = await reg.execute("exec", {"command": "id"}, session_id="cli:1", channel="cli", user_id="1")
        assert out == "channel=cli;user=1"

    asyncio.run(_scenario())
