from __future__ import annotations

import inspect
from typing import Protocol

from clawlite.tools.base import Tool, ToolContext


class CronAPI(Protocol):
    async def add_job(self, *, session_id: str, expression: str, prompt: str) -> str: ...
    def list_jobs(self, *, session_id: str) -> list[dict]: ...


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
            maybe_rows = self.api.list_jobs(session_id=ctx.session_id)
            rows = await maybe_rows if inspect.isawaitable(maybe_rows) else maybe_rows
            if not rows:
                return "empty"
            lines: list[str] = []
            for row in rows:
                schedule = row.get("schedule", {})
                expression = row.get("expression")
                if not expression and isinstance(schedule, dict):
                    kind = schedule.get("kind", "")
                    if kind == "every":
                        expression = f"every {schedule.get('every_seconds', 0)}"
                    elif kind == "at":
                        expression = f"at {schedule.get('run_at_iso', '')}"
                    else:
                        expression = str(schedule.get("cron_expr", ""))
                lines.append(f"{row.get('id')} {expression}")
            return "\n".join(lines)
        raise ValueError("invalid cron action")
