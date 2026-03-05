from __future__ import annotations

"""Tool bridge for executable SKILL.md entries.

`SkillTool` makes discovered skills runnable at runtime without changing
`registry.py` for each new skill:
- `command:` runs shell commands from SKILL metadata
- `script:` dispatches to built-in tool wrappers or external executables
"""

import asyncio
import inspect
import shlex
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import httpx

from clawlite.core.skills import SkillsLoader
from clawlite.tools.base import Tool, ToolContext
from clawlite.tools.exec import ExecTool
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

    def __init__(self, *, loader: SkillsLoader, registry: ToolRegistry, memory: Any | None = None) -> None:
        self.loader = loader
        self.registry = registry
        self.memory = memory

    @staticmethod
    def _policy_reason(raw: Any) -> str:
        text = str(raw or "").strip()
        if not text:
            return "unspecified"
        return text.replace("\n", " ").replace("\r", " ")

    async def _memory_policy_allows(self, *, session_id: str) -> tuple[bool, str]:
        memory = self.memory
        if memory is None:
            return True, ""

        policy_fn = getattr(memory, "integration_policy", None)
        if not callable(policy_fn):
            return True, ""

        try:
            verdict = policy_fn("skill", session_id=session_id)
            if inspect.isawaitable(verdict):
                verdict = await verdict
        except Exception:
            return True, ""

        if isinstance(verdict, bool):
            return verdict, "" if verdict else "blocked"

        if isinstance(verdict, dict):
            allowed_raw = verdict.get("allowed", verdict.get("allow", verdict.get("ok", True)))
            allowed = bool(allowed_raw)
            reason = self._policy_reason(verdict.get("reason", verdict.get("message", verdict.get("detail", ""))))
            return allowed, reason if not allowed else ""

        allowed_attr = getattr(verdict, "allowed", None)
        if allowed_attr is not None:
            allowed = bool(allowed_attr)
            reason = self._policy_reason(getattr(verdict, "reason", ""))
            return allowed, reason if not allowed else ""

        return True, ""

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

    @staticmethod
    def _join_command(argv: list[str]) -> str:
        if not argv:
            return ""
        return shlex.join(argv)

    async def _run_command_via_exec_tool(self, *, spec_name: str, argv: list[str], timeout: float, ctx: ToolContext) -> str:
        command = self._join_command(argv)
        if not command:
            raise ValueError("empty command")
        try:
            return await self.registry.execute(
                "exec",
                {"command": command, "timeout": timeout},
                session_id=ctx.session_id,
                channel=ctx.channel,
                user_id=ctx.user_id,
            )
        except RuntimeError as exc:
            expected = f"tool_blocked_by_safety_policy:exec:{ctx.channel}"
            if str(exc) == expected:
                return f"skill_blocked:{spec_name}:{expected}"
            raise

    async def _run_command_with_local_fallback(self, *, spec_name: str, argv: list[str], timeout: float) -> str:
        command = self._join_command(argv)
        if not command:
            raise ValueError("empty command")
        guard = ExecTool()._guard_command(command, argv, Path.cwd().resolve())
        if guard:
            return f"skill_blocked:{spec_name}:{guard}"
        return await self._run_command(argv, timeout=timeout)

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

    async def _dispatch_script(self, script_name: str, arguments: dict[str, Any], ctx: ToolContext, *, spec_name: str) -> str:
        if script_name == "weather":
            return await self._run_weather(arguments)

        target_tool = self.registry.get(script_name)
        if target_tool is not None and script_name != self.name:
            tool_arguments = self._script_tool_arguments(script_name, arguments)
            try:
                return await self.registry.execute(
                    script_name,
                    tool_arguments,
                    session_id=ctx.session_id,
                    channel=ctx.channel,
                    user_id=ctx.user_id,
                )
            except RuntimeError as exc:
                if str(exc).startswith(f"tool_blocked_by_safety_policy:{script_name}:"):
                    return f"skill_blocked:{spec_name}:{exc}"
                raise

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

        allowed, reason = await self._memory_policy_allows(session_id=ctx.session_id)
        if not allowed:
            return f"skill_blocked:{spec.name}:memory_policy:{reason}"

        timeout = self._timeout_value(arguments)

        if spec.execution_kind == "command":
            argv = [*spec.execution_argv, *extra_args]
            log.info("running skill command skill={}", spec.name)
            if self.registry.get("exec") is not None:
                return await self._run_command_via_exec_tool(spec_name=spec.name, argv=argv, timeout=timeout, ctx=ctx)
            return await self._run_command_with_local_fallback(spec_name=spec.name, argv=argv, timeout=timeout)

        if spec.execution_kind == "script":
            log.info("running skill script skill={} script={}", spec.name, spec.execution_target)
            return await self._dispatch_script(spec.execution_target, arguments, ctx, spec_name=spec.name)

        if spec.execution_kind == "invalid":
            details = ", ".join(spec.contract_issues)
            return f"skill_invalid_contract:{spec.name}:{details}"

        return f"skill_not_executable:{spec.name}"
