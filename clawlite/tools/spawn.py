from __future__ import annotations

from clawlite.core.subagent import SubagentManager
from clawlite.tools.base import Tool, ToolContext


class SpawnTool(Tool):
    name = "spawn"
    description = "Spawn a subagent task in background."

    def __init__(self, manager: SubagentManager, runner):
        self.manager = manager
        self.runner = runner

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
            },
            "required": ["task"],
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        task = str(arguments.get("task", "")).strip()
        if not task:
            raise ValueError("task is required")
        run = await self.manager.spawn(session_id=ctx.session_id, task=task, runner=self.runner)
        return run.run_id
