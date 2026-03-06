from __future__ import annotations

import asyncio
import inspect
import json
from typing import Protocol

from clawlite.tools.base import Tool, ToolContext


class CronAPI(Protocol):
    async def add_job(
        self,
        *,
        session_id: str,
        expression: str,
        prompt: str,
        name: str = "",
        timezone_name: str | None = None,
        channel: str = "",
        target: str = "",
        metadata: dict | None = None,
    ) -> str: ...

    def list_jobs(self, *, session_id: str) -> list[dict]: ...
    def remove_job(self, job_id: str) -> bool: ...
    def enable_job(self, job_id: str, *, enabled: bool) -> bool: ...
    async def run_job(self, job_id: str, *, force: bool) -> str | None: ...


class CronTool(Tool):
    name = "cron"
    description = "Manage scheduled jobs with add/remove/enable/disable/run/list."

    def __init__(self, api: CronAPI) -> None:
        self.api = api

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["add", "remove", "enable", "disable", "run", "list"]},
                "job_id": {"type": "string"},
                "expression": {"type": "string"},
                "every_seconds": {"type": "integer"},
                "cron_expr": {"type": "string"},
                "at": {"type": "string"},
                "timezone": {"type": "string"},
                "tz": {"type": "string"},
                "prompt": {"type": "string"},
                "message": {"type": "string"},
                "name": {"type": "string"},
                "session_id": {"type": "string"},
                "channel": {"type": "string"},
                "target": {"type": "string"},
                "force": {"type": "boolean"},
                "run_once": {
                    "type": "boolean",
                    "description": "If true, runs exactly once and is automatically removed. Use for one-time delays like 'send in 5 minutes'.",
                },
            },
            "required": ["action"],
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        action = str(arguments.get("action", "")).strip().lower()
        session_id = str(arguments.get("session_id", "")).strip() or ctx.session_id

        if action == "add":
            expression = self._resolve_expression(arguments)
            prompt = str(arguments.get("prompt", "")).strip() or str(arguments.get("message", "")).strip()
            name = str(arguments.get("name", "")).strip()
            timezone_name = str(arguments.get("timezone", "")).strip() or str(arguments.get("tz", "")).strip() or None
            channel = str(arguments.get("channel", "")).strip() or ctx.channel
            target = str(arguments.get("target", "")).strip() or ctx.user_id
            run_once = self._coerce_bool(arguments.get("run_once"), default=False)
            if not expression or not prompt:
                raise ValueError("expression and prompt are required for action=add")

            job_id = await self.api.add_job(
                session_id=session_id,
                expression=expression,
                prompt=prompt,
                name=name,
                timezone_name=timezone_name,
                channel=channel,
                target=target,
                metadata={"source": "tool:cron", "run_once": run_once},
            )
            return json.dumps({"ok": True, "action": action, "job_id": job_id})

        if action == "list":
            list_jobs = self.api.list_jobs
            if inspect.iscoroutinefunction(list_jobs):
                maybe_rows = await list_jobs(session_id=session_id)
            else:
                maybe_rows = await asyncio.to_thread(list_jobs, session_id=session_id)
            rows = await maybe_rows if inspect.isawaitable(maybe_rows) else maybe_rows
            return json.dumps({"ok": True, "action": action, "count": len(rows), "jobs": rows})

        if action == "remove":
            job_id = str(arguments.get("job_id", "")).strip()
            if not job_id:
                raise ValueError("job_id is required for action=remove")
            remove_job = self.api.remove_job
            if inspect.iscoroutinefunction(remove_job):
                ok = await remove_job(job_id)
            else:
                maybe_ok = await asyncio.to_thread(remove_job, job_id)
                ok = await maybe_ok if inspect.isawaitable(maybe_ok) else maybe_ok
            return json.dumps({"ok": ok, "action": action, "job_id": job_id})

        if action in {"enable", "disable"}:
            job_id = str(arguments.get("job_id", "")).strip()
            if not job_id:
                raise ValueError("job_id is required for action=enable/disable")
            enabled = action == "enable"
            enable_job = self.api.enable_job
            if inspect.iscoroutinefunction(enable_job):
                ok = await enable_job(job_id, enabled=enabled)
            else:
                maybe_ok = await asyncio.to_thread(enable_job, job_id, enabled=enabled)
                ok = await maybe_ok if inspect.isawaitable(maybe_ok) else maybe_ok
            return json.dumps({"ok": ok, "action": action, "job_id": job_id, "enabled": enabled})

        if action == "run":
            job_id = str(arguments.get("job_id", "")).strip()
            if not job_id:
                raise ValueError("job_id is required for action=run")
            force = self._coerce_bool(arguments.get("force"), default=True)
            try:
                output = await self.api.run_job(job_id, force=force)
            except KeyError:
                return json.dumps({"ok": False, "action": action, "job_id": job_id, "error": "job_not_found"})
            except RuntimeError as exc:
                return json.dumps({"ok": False, "action": action, "job_id": job_id, "error": str(exc)})
            return json.dumps({"ok": True, "action": action, "job_id": job_id, "output": output})

        raise ValueError("invalid cron action")

    @staticmethod
    def _resolve_expression(arguments: dict) -> str:
        explicit = str(arguments.get("expression", "")).strip()
        if explicit:
            return explicit

        every_raw = arguments.get("every_seconds")
        if every_raw is not None and str(every_raw).strip() != "":
            return f"every {int(every_raw)}"

        cron_expr = str(arguments.get("cron_expr", "")).strip()
        if cron_expr:
            return cron_expr

        at = str(arguments.get("at", "")).strip()
        if at:
            return f"at {at}"
        return ""

    @staticmethod
    def _coerce_bool(value: object, *, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"1", "true", "yes", "on"}:
                return True
            if text in {"0", "false", "no", "off"}:
                return False
        return bool(value)
