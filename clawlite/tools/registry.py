from __future__ import annotations

from typing import Any

from clawlite.tools.base import Tool, ToolContext


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def replace(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schema(self) -> list[dict[str, Any]]:
        return [self._tools[name].export_schema() for name in sorted(self._tools.keys())]

    async def execute(self, name: str, arguments: dict[str, Any], *, session_id: str, channel: str = "", user_id: str = "") -> str:
        tool = self.get(name)
        if tool is None:
            raise KeyError(f"unknown tool: {name}")
        return await tool.run(arguments, ToolContext(session_id=session_id, channel=channel, user_id=user_id))
