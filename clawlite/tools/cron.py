from __future__ import annotations

from typing import Protocol

from clawlite.tools.base import Tool, ToolContext


class CronAPI(Protocol):
    async def add_job(self, *, session_id: str, expression: str, prompt: str) -> str: ...
    async def list_jobs(self, *, session_id: str) -> list[dict]: ...


class CronTool(Tool):
    name = "cron"
    description = "Add/list scheduled jobs."

    def __init__(self, api: CronAPI) -> None:
        self.api = api

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["add", "list"]},
                "expression": {"type": "string"},
                "prompt": {"type": "string"},
            },
            "required": ["action"],
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        action = str(arguments.get("action", "")).strip().lower()
        if action == "add":
            expression = str(arguments.get("expression", "")).strip()
            prompt = str(arguments.get("prompt", "")).strip()
            if not expression or not prompt:
                raise ValueError("expression and prompt are required for action=add")
            return await self.api.add_job(session_id=ctx.session_id, expression=expression, prompt=prompt)
        if action == "list":
            rows = await self.api.list_jobs(session_id=ctx.session_id)
            return "\n".join(f"{row.get('id')} {row.get('expression')}" for row in rows) if rows else "empty"
        raise ValueError("invalid cron action")
