from __future__ import annotations

import asyncio
import shlex

from clawlite.tools.base import Tool, ToolContext


class ExecTool(Tool):
    name = "exec"
    description = "Run shell command safely (no shell=True)."

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "number", "default": 30},
            },
            "required": ["command"],
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        command = str(arguments.get("command", "")).strip()
        if not command:
            raise ValueError("command is required")

        timeout = float(arguments.get("timeout", 30) or 30)
        argv = shlex.split(command)

        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return f"exit=-1\nstdout=\nstderr=timeout after {timeout}s"

        stdout = out.decode("utf-8", errors="ignore").strip()
        stderr = err.decode("utf-8", errors="ignore").strip()
        return f"exit={process.returncode}\nstdout={stdout}\nstderr={stderr}"
