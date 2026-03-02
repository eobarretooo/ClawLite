from __future__ import annotations

import asyncio
import os
import shlex
from pathlib import Path

from clawlite.tools.base import Tool, ToolContext


class ExecTool(Tool):
    name = "exec"
    description = "Run shell command safely (no shell=True)."

    def __init__(
        self,
        *,
        workspace_path: str | Path | None = None,
        restrict_to_workspace: bool = False,
        path_append: str = "",
    ) -> None:
        self.workspace_path = (Path(workspace_path).expanduser().resolve() if workspace_path else Path.cwd().resolve())
        self.restrict_to_workspace = bool(restrict_to_workspace)
        self.path_append = str(path_append or "")

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "number", "default": 30},
            },
            "required": ["command"],
        }

    def _workspace_guard(self, argv: list[str]) -> str | None:
        if not self.restrict_to_workspace:
            return None

        workspace = self.workspace_path
        for token in argv:
            value = token.strip()
            if not value:
                continue
            if value == ".." or value.startswith("../") or value.startswith("..\\"):
                return f"blocked_by_workspace_guard:path_traversal:{value}"
            if value.startswith("/"):
                candidate = Path(value).expanduser().resolve()
                if candidate != workspace and workspace not in candidate.parents:
                    return f"blocked_by_workspace_guard:path_outside_workspace:{value}"
        return None

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        command = str(arguments.get("command", "")).strip()
        if not command:
            raise ValueError("command is required")

        timeout = float(arguments.get("timeout", 30) or 30)
        argv = shlex.split(command)
        guard_error = self._workspace_guard(argv)
        if guard_error:
            return f"exit=-1\nstdout=\nstderr={guard_error}"

        env = os.environ.copy()
        if self.path_append:
            current = env.get("PATH", "")
            env["PATH"] = f"{current}{os.pathsep}{self.path_append}" if current else self.path_append

        cwd = str(self.workspace_path) if self.restrict_to_workspace else None

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
        except OSError as exc:
            return f"exit=-1\nstdout=\nstderr={exc}"
        try:
            out, err = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return f"exit=-1\nstdout=\nstderr=timeout after {timeout}s"

        stdout = out.decode("utf-8", errors="ignore").strip()
        stderr = err.decode("utf-8", errors="ignore").strip()
        return f"exit={process.returncode}\nstdout={stdout}\nstderr={stderr}"
