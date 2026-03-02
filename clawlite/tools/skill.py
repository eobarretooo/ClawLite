from __future__ import annotations

"""Tool bridge for executable SKILL.md entries.

`SkillTool` makes discovered skills runnable at runtime without changing
`registry.py` for each new skill:
- `command:` runs shell commands from SKILL metadata
- `script:` dispatches to built-in tool wrappers or external executables
"""

import asyncio
import shlex
from typing import Any
from urllib.parse import quote_plus

import httpx

from clawlite.core.skills import SkillsLoader
from clawlite.tools.base import Tool, ToolContext
from clawlite.tools.registry import ToolRegistry


class SkillTool(Tool):
    """Execute skills discovered by `SkillsLoader`.

    This tool is required to turn SKILL.md discovery into actual execution.
    Without it, skills would appear in prompt context but would not be callable.
    """

    name = "run_skill"
    description = "Execute a discovered SKILL.md binding via command or script."

    def __init__(self, *, loader: SkillsLoader, registry: ToolRegistry) -> None:
        self.loader = loader
        self.registry = registry

    def args_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "input": {"type": "string"},
                "args": {"type": "array", "items": {"type": "string"}},
                "timeout": {"type": "number", "default": 30},
                "query": {"type": "string"},
                "location": {"type": "string"},
                "tool_arguments": {"type": "object"},
            },
            "required": ["name"],
        }

    @staticmethod
    def _extra_args(arguments: dict[str, Any]) -> list[str]:
        values = arguments.get("args")
        if isinstance(values, list):
            return [str(item) for item in values if str(item).strip()]
        raw = str(arguments.get("input", "")).strip()
        return shlex.split(raw) if raw else []

    async def _run_command(self, argv: list[str], *, timeout: float) -> str:
        if not argv:
            raise ValueError("empty command")
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
            return f"skill_exec_timeout:{timeout}s"
        stdout = out.decode("utf-8", errors="ignore").strip()
        stderr = err.decode("utf-8", errors="ignore").strip()
        return f"exit={process.returncode}\nstdout={stdout}\nstderr={stderr}"

    async def _run_weather(self, arguments: dict[str, Any]) -> str:
        location = str(arguments.get("location") or arguments.get("input") or "").strip()
        if not location:
            location = "Sao Paulo"
        url = f"https://wttr.in/{quote_plus(location)}?format=3"
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(url)
            response.raise_for_status()
        return response.text.strip()

    async def _dispatch_script(self, script_name: str, arguments: dict[str, Any], ctx: ToolContext) -> str:
        normalized = script_name.replace("-", "_")

        if normalized == "web_search":
            query = str(arguments.get("query") or arguments.get("input") or "").strip()
            if not query:
                raise ValueError("query or input is required for web-search skill")
            limit = int(arguments.get("limit", 5) or 5)
            return await self.registry.execute("web_search", {"query": query, "limit": limit}, session_id=ctx.session_id)

        if normalized == "weather":
            return await self._run_weather(arguments)

        target_tool = self.registry.get(normalized)
        if target_tool is not None and normalized != self.name:
            payload = arguments.get("tool_arguments")
            tool_arguments = payload if isinstance(payload, dict) else {}
            return await self.registry.execute(normalized, tool_arguments, session_id=ctx.session_id)

        return await self._run_command([script_name, *self._extra_args(arguments)], timeout=float(arguments.get("timeout", 30) or 30))

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        name = str(arguments.get("name", "")).strip()
        if not name:
            raise ValueError("skill name is required")

        spec = self.loader.get(name)
        if spec is None:
            raise ValueError(f"skill_not_found:{name}")
        if not spec.available:
            details = ", ".join(spec.missing)
            return f"skill_unavailable:{spec.name}:{details}"

        if spec.command:
            argv = shlex.split(spec.command) + self._extra_args(arguments)
            return await self._run_command(argv, timeout=float(arguments.get("timeout", 30) or 30))

        if spec.script:
            return await self._dispatch_script(spec.script, arguments, ctx)

        return f"skill_not_executable:{spec.name}"
