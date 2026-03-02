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
from clawlite.utils.logging import bind_event, setup_logging

setup_logging()


class SkillTool(Tool):
    """Execute skills discovered by `SkillsLoader`.

    This tool is required to turn SKILL.md discovery into actual execution.
    Without it, skills would appear in prompt context but would not be callable.
    """

    name = "run_skill"
    description = "Execute a discovered SKILL.md binding with deterministic contracts."

    MAX_TIMEOUT_SECONDS = 120.0
    MAX_SKILL_ARGS = 32
    MAX_ARG_CHARS = 4000

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

    @classmethod
    def _guard_extra_args(cls, values: list[str]) -> str | None:
        if len(values) > cls.MAX_SKILL_ARGS:
            return f"skill_args_exceeded:max={cls.MAX_SKILL_ARGS}"
        for value in values:
            if len(value) > cls.MAX_ARG_CHARS:
                return f"skill_arg_too_large:max_chars={cls.MAX_ARG_CHARS}"
            if "\x00" in value or "\n" in value or "\r" in value:
                return "skill_arg_invalid_character"
        return None

    @classmethod
    def _timeout_value(cls, arguments: dict[str, Any]) -> float:
        raw = float(arguments.get("timeout", 30) or 30)
        if raw < 1:
            return 1.0
        if raw > cls.MAX_TIMEOUT_SECONDS:
            return cls.MAX_TIMEOUT_SECONDS
        return raw

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

    @staticmethod
    def _script_tool_arguments(script_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        payload = arguments.get("tool_arguments")
        if isinstance(payload, dict):
            return payload

        if script_name == "web_search":
            query = str(arguments.get("query") or arguments.get("input") or "").strip()
            if not query:
                raise ValueError("query or input is required for web-search skill")
            limit = int(arguments.get("limit", 5) or 5)
            return {"query": query, "limit": limit}

        return {}

    async def _dispatch_script(self, script_name: str, arguments: dict[str, Any], ctx: ToolContext) -> str:
        if script_name == "weather":
            return await self._run_weather(arguments)

        target_tool = self.registry.get(script_name)
        if target_tool is not None and script_name != self.name:
            tool_arguments = self._script_tool_arguments(script_name, arguments)
            return await self.registry.execute(script_name, tool_arguments, session_id=ctx.session_id)

        return f"skill_script_unavailable:{script_name}"

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        name = str(arguments.get("name", "")).strip()
        log = bind_event("tool.skill", session=ctx.session_id, tool=self.name)
        if not name:
            raise ValueError("skill name is required")

        spec = self.loader.get(name)
        if spec is None:
            raise ValueError(f"skill_not_found:{name}")
        if not spec.available:
            details = ", ".join([*spec.missing, *spec.contract_issues])
            return f"skill_unavailable:{spec.name}:{details}"

        extra_args = self._extra_args(arguments)
        args_guard_error = self._guard_extra_args(extra_args)
        if args_guard_error:
            return f"skill_blocked:{spec.name}:{args_guard_error}"

        timeout = self._timeout_value(arguments)

        if spec.execution_kind == "command":
            argv = [*spec.execution_argv, *extra_args]
            log.info("running skill command skill={}", spec.name)
            return await self._run_command(argv, timeout=timeout)

        if spec.execution_kind == "script":
            log.info("running skill script skill={} script={}", spec.name, spec.execution_target)
            return await self._dispatch_script(spec.execution_target, arguments, ctx)

        if spec.execution_kind == "invalid":
            details = ", ".join(spec.contract_issues)
            return f"skill_invalid_contract:{spec.name}:{details}"

        return f"skill_not_executable:{spec.name}"
