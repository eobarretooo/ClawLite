from __future__ import annotations

from typing import Any

from clawlite.config.schema import ToolSafetyPolicyConfig
from clawlite.tools.base import Tool, ToolContext


class ToolRegistry:
    def __init__(self, *, safety: ToolSafetyPolicyConfig | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        self._safety = safety or ToolSafetyPolicyConfig()

    def _is_blocked_by_safety(self, *, tool_name: str, channel: str) -> bool:
        if not self._safety.enabled:
            return False
        normalized_tool = str(tool_name or "").strip().lower()
        if normalized_tool not in self._safety.risky_tools:
            return False
        normalized_channel = str(channel or "").strip().lower()
        if not normalized_channel:
            return False
        if normalized_channel in self._safety.allowed_channels:
            return False
        return normalized_channel in self._safety.blocked_channels

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
        if self._is_blocked_by_safety(tool_name=name, channel=channel):
            raise RuntimeError(f"tool_blocked_by_safety_policy:{name}:{channel}")
        return await tool.run(arguments, ToolContext(session_id=session_id, channel=channel, user_id=user_id))
