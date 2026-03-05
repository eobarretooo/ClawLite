from __future__ import annotations

import inspect
from typing import Any

from clawlite.core.subagent import SubagentLimitError, SubagentManager
from clawlite.tools.base import Tool, ToolContext


class SpawnTool(Tool):
    name = "spawn"
    description = "Spawn a subagent task in background."

    def __init__(self, manager: SubagentManager, runner, *, memory: Any | None = None):
        self.manager = manager
        self.runner = runner
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
            verdict = policy_fn("subagent", session_id=session_id)
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
        allowed, reason = await self._memory_policy_allows(session_id=ctx.session_id)
        if not allowed:
            raise ValueError(f"subagent_spawn_blocked_by_memory_policy:{reason}")
        try:
            run = await self.manager.spawn(session_id=ctx.session_id, task=task, runner=self.runner)
        except SubagentLimitError as exc:
            raise ValueError(str(exc)) from exc
        return run.run_id
