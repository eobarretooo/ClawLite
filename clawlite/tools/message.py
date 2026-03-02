from __future__ import annotations

from typing import Protocol

from clawlite.tools.base import Tool, ToolContext


class MessageAPI(Protocol):
    async def send(self, *, channel: str, target: str, text: str) -> str: ...


class MessageTool(Tool):
    name = "message"
    description = "Send proactive message to a channel target."

    def __init__(self, api: MessageAPI) -> None:
        self.api = api

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "target": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["channel", "target", "text"],
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        channel = str(arguments.get("channel", "")).strip() or ctx.channel
        target = str(arguments.get("target", "")).strip()
        text = str(arguments.get("text", "")).strip()
        if not channel or not target or not text:
            raise ValueError("channel, target and text are required")
        return await self.api.send(channel=channel, target=target, text=text)
