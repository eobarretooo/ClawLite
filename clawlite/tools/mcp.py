from __future__ import annotations

import httpx

from clawlite.tools.base import Tool, ToolContext
from clawlite.utils.logging import bind_event, setup_logging

setup_logging()


class MCPTool(Tool):
    name = "mcp"
    description = "Call a remote MCP-compatible HTTP endpoint."

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "tool": {"type": "string"},
                "arguments": {"type": "object"},
            },
            "required": ["url", "tool"],
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        url = str(arguments.get("url", "")).strip()
        log = bind_event("tool.mcp", session=ctx.session_id, tool=self.name)
        tool = str(arguments.get("tool", "")).strip()
        payload_args = arguments.get("arguments", {})
        if not isinstance(payload_args, dict):
            raise ValueError("arguments must be an object")
        if not url or not tool:
            raise ValueError("url and tool are required")

        payload = {
            "jsonrpc": "2.0",
            "id": "clawlite-mcp",
            "method": "tools/call",
            "params": {"name": tool, "arguments": payload_args},
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
        log.info("mcp call url={} method=tools/call", url)

        if isinstance(data, dict) and data.get("error"):
            return f"mcp_error:{data['error']}"
        return str(data.get("result", data))
