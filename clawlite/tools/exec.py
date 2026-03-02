from __future__ import annotations

import asyncio
import os
import shlex
from pathlib import Path

from clawlite.tools.base import Tool, ToolContext
from clawlite.utils.logging import bind_event, setup_logging

setup_logging()


class ExecTool(Tool):
    name = "exec"
    description = "Run shell command safely (no shell=True)."

    def __init__(
        self,
        *,
        workspace_path: str | Path | None = None,
        restrict_to_workspace: bool = False,
        path_append: str = "",
        timeout_seconds: int = 60,
    ) -> None:
        self.workspace_path = (Path(workspace_path).expanduser().resolve() if workspace_path else Path.cwd().resolve())
        self.restrict_to_workspace = bool(restrict_to_workspace)
        self.path_append = str(path_append or "")
        self.timeout_seconds = max(1, int(timeout_seconds))

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "number", "default": self.timeout_seconds},
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
        log = bind_event("tool.exec", session=ctx.session_id, tool=self.name)
        if not command:
            raise ValueError("command is required")

        timeout = float(arguments.get("timeout", self.timeout_seconds) or self.timeout_seconds)
        argv = shlex.split(command)
        guard_error = self._workspace_guard(argv)
        if guard_error:
            log.warning("command blocked by workspace guard error={}", guard_error)
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
            log.error("spawn failed error={}", exc)
            return f"exit=-1\nstdout=\nstderr={exc}"
        try:
            out, err = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            log.warning("command timeout timeout_s={}", timeout)
            return f"exit=-1\nstdout=\nstderr=timeout after {timeout}s"

        stdout = out.decode("utf-8", errors="ignore").strip()
        log.debug("command finished exit_code={}", process.returncode)
        stderr = err.decode("utf-8", errors="ignore").strip()
        return f"exit={process.returncode}\nstdout={stdout}\nstderr={stderr}"
