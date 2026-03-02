from __future__ import annotations

import asyncio

from clawlite.tools.base import Tool, ToolContext
from clawlite.tools.registry import ToolRegistry


class EchoTool(Tool):
    name = "echo"
    description = "echo"

    def args_schema(self) -> dict:
        return {"type": "object", "properties": {"text": {"type": "string"}}}

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        return str(arguments.get("text", ""))


def test_tool_registry_execute() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(EchoTool())
        out = await reg.execute("echo", {"text": "ok"}, session_id="s")
        assert out == "ok"

    asyncio.run(_scenario())
