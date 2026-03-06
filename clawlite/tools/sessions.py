from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from typing import Any, Awaitable, Callable

from clawlite.core.subagent import SubagentLimitError, SubagentManager, SubagentRun
from clawlite.session.store import SessionStore
from clawlite.tools.base import Tool, ToolContext


Runner = Callable[[str, str], Awaitable[Any]]


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _preview(role: str, content: str, *, max_chars: int = 120) -> str:
    clean_role = str(role or "").strip().lower() or "unknown"
    clean_text = " ".join(str(content or "").strip().split())
    if len(clean_text) > max_chars:
        clean_text = f"{clean_text[:max_chars]}..."
    return f"{clean_role}: {clean_text}" if clean_text else clean_role


def _resolve_session_id(arguments: dict[str, Any], *, required: bool) -> str:
    value = (
        arguments.get("session_id")
        or arguments.get("sessionId")
        or arguments.get("sessionKey")
        or ""
    )
    out = str(value).strip()
    if required and not out:
        raise ValueError("session_id/sessionId/sessionKey is required")
    return out


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _coerce_limit(value: Any, *, default: int, minimum: int = 1, maximum: int = 200) -> int:
    try:
        number = int(value)
    except Exception:
        number = default
    if number < minimum:
        return minimum
    if number > maximum:
        return maximum
    return number


def _coerce_timeout(value: Any, *, default: float, minimum: float = 0.1, maximum: float = 3600.0) -> float:
    try:
        timeout = float(value)
    except Exception:
        timeout = default
    if timeout < minimum:
        return minimum
    if timeout > maximum:
        return maximum
    return timeout


def _session_file_path(sessions: SessionStore, session_id: str) -> Path:
    return sessions.root / f"{sessions._safe_session_id(session_id)}.jsonl"


def _count_session_messages(sessions: SessionStore, session_id: str) -> int:
    try:
        path = _session_file_path(sessions, session_id)
        if not path.exists():
            return 0
        count = 0
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            role = str(payload.get("role", "")).strip()
            content = str(payload.get("content", "")).strip()
            if role and content:
                count += 1
        return count
    except Exception:
        return 0


def _last_message_preview(sessions: SessionStore, session_id: str) -> dict[str, str] | None:
    rows = sessions.read(session_id, limit=1)
    if not rows:
        return None
    last = rows[-1]
    role = str(last.get("role", "")).strip()
    content = str(last.get("content", "")).strip()
    return {
        "role": role,
        "content": content,
        "preview": _preview(role, content),
    }


def _run_to_payload(run: SubagentRun) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "session_id": run.session_id,
        "task": run.task,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


class SessionsListTool(Tool):
    name = "sessions_list"
    description = "List persisted sessions with last-message preview."

    def __init__(self, sessions: SessionStore) -> None:
        self.sessions = sessions

    def args_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1},
            },
        }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        del ctx
        limit = _coerce_limit(arguments.get("limit"), default=20, minimum=1, maximum=500)
        ids = self.sessions.list_sessions()[:limit]
        rows: list[dict[str, Any]] = []
        for session_id in ids:
            preview = _last_message_preview(self.sessions, session_id)
            rows.append(
                {
                    "session_id": session_id,
                    "last_message": preview,
                }
            )
        return _json(
            {
                "status": "ok",
                "count": len(rows),
                "sessions": rows,
            }
        )


class SessionsHistoryTool(Tool):
    name = "sessions_history"
    description = "Read history for a specific session."

    def __init__(self, sessions: SessionStore) -> None:
        self.sessions = sessions

    def args_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "sessionId": {"type": "string"},
                "sessionKey": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1},
                "include_tools": {"type": "boolean"},
                "includeTools": {"type": "boolean"},
            },
        }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        del ctx
        try:
            session_id = _resolve_session_id(arguments, required=True)
        except ValueError as exc:
            return _json({"status": "failed", "error": str(exc)})

        limit = _coerce_limit(arguments.get("limit"), default=50, minimum=1, maximum=1000)
        include_tools = _coerce_bool(
            arguments.get("include_tools", arguments.get("includeTools")),
            default=False,
        )
        rows = self.sessions.read(session_id, limit=limit)
        if not include_tools:
            rows = [row for row in rows if str(row.get("role", "")).strip().lower() != "tool"]
        return _json(
            {
                "status": "ok",
                "session_id": session_id,
                "count": len(rows),
                "messages": rows,
            }
        )


class SessionsSendTool(Tool):
    name = "sessions_send"
    description = "Run a message against a target session."

    def __init__(self, runner: Runner, *, runner_timeout_s: float = 60.0) -> None:
        self.runner = runner
        self.runner_timeout_s = max(0.1, float(runner_timeout_s or 60.0))

    def args_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "sessionId": {"type": "string"},
                "sessionKey": {"type": "string"},
                "message": {"type": "string"},
                "timeout": {"type": "number", "minimum": 0.1},
                "timeout_s": {"type": "number", "minimum": 0.1},
            },
            "required": ["message"],
        }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        session_id = _resolve_session_id(arguments, required=True)
        message = str(arguments.get("message", "")).strip()
        if not message:
            return _json({"status": "failed", "error": "message is required"})
        if session_id == ctx.session_id:
            return _json(
                {
                    "status": "failed",
                    "session_id": session_id,
                    "error": "same_session_not_allowed",
                }
            )
        timeout_s = _coerce_timeout(
            arguments.get(
                "timeout_s",
                arguments.get("timeout", self.runner_timeout_s),
            ),
            default=self.runner_timeout_s,
        )
        try:
            result = await asyncio.wait_for(self.runner(session_id, message), timeout=timeout_s)
        except asyncio.TimeoutError:
            return _json(
                {
                    "status": "failed",
                    "session_id": session_id,
                    "error": "runner_timeout",
                }
            )
        except Exception as exc:
            return _json(
                {
                    "status": "failed",
                    "session_id": session_id,
                    "error": str(exc),
                }
            )

        text = str(getattr(result, "text", result) or "")
        model = str(getattr(result, "model", "") or "")
        return _json(
            {
                "status": "ok",
                "session_id": session_id,
                "text": text,
                "model": model,
            }
        )


class SessionsSpawnTool(Tool):
    name = "sessions_spawn"
    description = "Spawn delegated execution routed to target session."

    def __init__(self, manager: SubagentManager, runner: Runner) -> None:
        self.manager = manager
        self.runner = runner

    def args_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "session_id": {"type": "string"},
                "sessionId": {"type": "string"},
                "sessionKey": {"type": "string"},
            },
            "required": ["task"],
        }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        task = str(arguments.get("task", "")).strip()
        if not task:
            return _json({"status": "failed", "error": "task is required"})

        requested_target = _resolve_session_id(arguments, required=False)
        target_session_id = requested_target or f"{ctx.session_id}:subagent"

        async def _target_runner(_owner_session_id: str, delegated_task: str) -> str:
            result = self.runner(target_session_id, delegated_task)
            if inspect.isawaitable(result):
                result = await result
            return str(getattr(result, "text", result) or "")

        try:
            run = await self.manager.spawn(
                session_id=ctx.session_id,
                task=task,
                runner=_target_runner,
            )
        except SubagentLimitError as exc:
            return _json(
                {
                    "status": "failed",
                    "session_id": ctx.session_id,
                    "target_session_id": target_session_id,
                    "error": str(exc),
                }
            )

        return _json(
            {
                "status": "ok",
                "run_id": run.run_id,
                "session_id": run.session_id,
                "target_session_id": target_session_id,
                "state": run.status,
            }
        )


class SubagentsTool(Tool):
    name = "subagents"
    description = "List or cancel subagent runs."

    def __init__(self, manager: SubagentManager) -> None:
        self.manager = manager

    def args_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "kill"], "default": "list"},
                "session_id": {"type": "string"},
                "sessionId": {"type": "string"},
                "sessionKey": {"type": "string"},
                "run_id": {"type": "string"},
                "runId": {"type": "string"},
                "all": {"type": "boolean"},
            },
        }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        action = str(arguments.get("action", "list") or "list").strip().lower()
        session_id = _resolve_session_id(arguments, required=False) or ctx.session_id

        if action == "list":
            rows = self.manager.list_runs(session_id=session_id)
            return _json(
                {
                    "status": "ok",
                    "action": "list",
                    "session_id": session_id,
                    "count": len(rows),
                    "runs": [_run_to_payload(run) for run in rows],
                }
            )

        if action == "kill":
            run_id = str(arguments.get("run_id") or arguments.get("runId") or "").strip()
            kill_all = _coerce_bool(arguments.get("all"), default=False)
            if kill_all:
                cancelled = int(self.manager.cancel_session(session_id) or 0)
                return _json(
                    {
                        "status": "ok",
                        "action": "kill",
                        "session_id": session_id,
                        "all": True,
                        "cancelled": cancelled,
                    }
                )

            if not run_id:
                return _json(
                    {
                        "status": "failed",
                        "action": "kill",
                        "error": "run_id/runId is required when all=false",
                    }
                )
            cancelled = bool(self.manager.cancel(run_id))
            return _json(
                {
                    "status": "ok" if cancelled else "failed",
                    "action": "kill",
                    "run_id": run_id,
                    "cancelled": cancelled,
                }
            )

        return _json(
            {
                "status": "failed",
                "error": "unsupported action",
                "action": action,
            }
        )


class SessionStatusTool(Tool):
    name = "session_status"
    description = "Return status card data for a session."

    def __init__(self, sessions: SessionStore, manager: SubagentManager) -> None:
        self.sessions = sessions
        self.manager = manager

    def args_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "sessionId": {"type": "string"},
                "sessionKey": {"type": "string"},
            },
        }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        session_id = _resolve_session_id(arguments, required=False) or ctx.session_id
        path = _session_file_path(self.sessions, session_id)
        exists = path.exists()
        message_count = _count_session_messages(self.sessions, session_id) if exists else 0
        last_message = _last_message_preview(self.sessions, session_id)
        active_subagents = len(self.manager.list_runs(session_id=session_id, active_only=True))
        return _json(
            {
                "status": "ok",
                "session_id": session_id,
                "exists": exists,
                "message_count": message_count,
                "last_message": last_message,
                "active_subagents": active_subagents,
            }
        )
