from __future__ import annotations

import asyncio
import json
import os
import shlex
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from clawlite.tools.base import Tool, ToolContext
from clawlite.tools.exec import ExecTool


MAX_POLL_WAIT_MS = 120_000
DEFAULT_LOG_LIMIT = 4000


@dataclass(slots=True)
class ProcessSession:
    session_id: str
    command: str
    process: asyncio.subprocess.Process
    started_at: float
    output: str = ""
    exit_code: int | None = None
    ended_at: float | None = None
    status: str = "running"
    output_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    done_event: asyncio.Event = field(default_factory=asyncio.Event)


class ProcessTool(Tool):
    name = "process"
    description = "Manage background process sessions (start/list/poll/log/write/kill/remove/clear)."

    def __init__(
        self,
        *,
        workspace_path: str | Path | None = None,
        restrict_to_workspace: bool = False,
        path_append: str = "",
        deny_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        deny_path_patterns: list[str] | None = None,
        allow_path_patterns: list[str] | None = None,
    ) -> None:
        self._guard = ExecTool(
            workspace_path=workspace_path,
            restrict_to_workspace=restrict_to_workspace,
            path_append=path_append,
            deny_patterns=deny_patterns,
            allow_patterns=allow_patterns,
            deny_path_patterns=deny_path_patterns,
            allow_path_patterns=allow_path_patterns,
        )
        self._sessions: dict[str, ProcessSession] = {}

    def args_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "sessionId": {"type": "string"},
                "session_id": {"type": "string"},
                "command": {"type": "string"},
                "data": {"type": "string"},
                "eof": {"type": "boolean"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
                "timeout": {"type": "number"},
            },
            "required": ["action"],
        }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        del ctx
        action = str(arguments.get("action", "")).strip().lower()
        if not action:
            return self._json({"status": "failed", "error": "action_required"})

        if action == "start":
            return await self._start(arguments)
        if action == "list":
            return self._list()
        if action == "poll":
            return await self._poll(arguments)
        if action == "log":
            return await self._log(arguments)
        if action == "write":
            return await self._write(arguments)
        if action == "kill":
            return await self._kill(arguments)
        if action == "remove":
            return self._remove(arguments)
        if action == "clear":
            return await self._clear(arguments)

        return self._json({"status": "failed", "error": "unknown_action", "action": action})

    async def _start(self, arguments: dict[str, Any]) -> str:
        command = str(arguments.get("command", "")).strip()
        if not command:
            return self._json({"status": "failed", "error": "command_required"})

        try:
            argv = shlex.split(command)
        except ValueError:
            return self._json({"status": "failed", "error": "invalid_command_syntax"})

        cwd_path = self._guard.workspace_path if self._guard.restrict_to_workspace else Path.cwd().resolve()
        guard_error = self._guard._guard_command(command, argv, cwd_path)
        if guard_error:
            return self._json({"status": "failed", "error": guard_error})

        env = os.environ.copy()
        if self._guard.path_append:
            current = env.get("PATH", "")
            env["PATH"] = f"{current}{os.pathsep}{self._guard.path_append}" if current else self._guard.path_append

        cwd = str(self._guard.workspace_path) if self._guard.restrict_to_workspace else None

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
        except OSError as exc:
            return self._json({"status": "failed", "error": "spawn_failed", "message": str(exc)})

        session_id = f"proc_{uuid.uuid4().hex[:12]}"
        session = ProcessSession(
            session_id=session_id,
            command=command,
            process=process,
            started_at=asyncio.get_running_loop().time(),
        )
        self._sessions[session_id] = session
        asyncio.create_task(self._capture_stream(session, process.stdout))
        asyncio.create_task(self._capture_stream(session, process.stderr))
        asyncio.create_task(self._watch_process(session))

        return self._json({"status": "running", "sessionId": session_id, "pid": process.pid})

    def _list(self) -> str:
        sessions: list[dict[str, Any]] = []
        for session_id in sorted(self._sessions.keys()):
            session = self._sessions[session_id]
            sessions.append(
                {
                    "sessionId": session.session_id,
                    "status": session.status,
                    "pid": session.process.pid,
                    "command": session.command,
                    "exitCode": session.exit_code,
                }
            )
        return self._json({"status": "ok", "sessions": sessions})

    async def _poll(self, arguments: dict[str, Any]) -> str:
        session = self._get_session(arguments)
        if session is None:
            return self._missing_session_response(arguments)

        wait_ms = self._clamp_timeout_ms(arguments.get("timeout"))
        if session.status == "running" and wait_ms > 0:
            try:
                await asyncio.wait_for(session.done_event.wait(), timeout=wait_ms / 1000.0)
            except asyncio.TimeoutError:
                pass

        payload = {
            "status": session.status,
            "sessionId": session.session_id,
            "pid": session.process.pid,
            "exitCode": session.exit_code,
            "outputLength": len(session.output),
        }
        return self._json(payload)

    async def _log(self, arguments: dict[str, Any]) -> str:
        session = self._get_session(arguments)
        if session is None:
            return self._missing_session_response(arguments)

        offset = int(arguments.get("offset", 0) or 0)
        if offset < 0:
            offset = 0
        limit_raw = arguments.get("limit", DEFAULT_LOG_LIMIT)
        try:
            limit = int(limit_raw if limit_raw is not None else DEFAULT_LOG_LIMIT)
        except (TypeError, ValueError):
            limit = DEFAULT_LOG_LIMIT
        if limit < 0:
            limit = 0
        if limit > 100_000:
            limit = 100_000

        async with session.output_lock:
            total = len(session.output)
            chunk = session.output[offset : offset + limit]

        return self._json(
            {
                "status": "ok",
                "sessionId": session.session_id,
                "offset": offset,
                "limit": limit,
                "total": total,
                "log": chunk,
            }
        )

    async def _write(self, arguments: dict[str, Any]) -> str:
        session = self._get_session(arguments)
        if session is None:
            return self._missing_session_response(arguments)
        if session.status != "running":
            return self._json({"status": "failed", "error": "session_not_running", "sessionId": session.session_id})

        stdin = session.process.stdin
        if stdin is None or stdin.is_closing():
            return self._json({"status": "failed", "error": "stdin_unavailable", "sessionId": session.session_id})

        data = str(arguments.get("data", ""))
        if data:
            stdin.write(data.encode("utf-8"))
            await stdin.drain()
        if bool(arguments.get("eof", False)):
            stdin.close()

        return self._json({"status": "ok", "sessionId": session.session_id, "written": len(data)})

    async def _kill(self, arguments: dict[str, Any]) -> str:
        session = self._get_session(arguments)
        if session is None:
            return self._missing_session_response(arguments)
        if session.status != "running":
            return self._json({"status": "ok", "sessionId": session.session_id, "alreadyStopped": True})

        session.process.terminate()
        try:
            await asyncio.wait_for(session.done_event.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            session.process.kill()
            await session.done_event.wait()

        return self._json({"status": "ok", "sessionId": session.session_id, "killed": True})

    def _remove(self, arguments: dict[str, Any]) -> str:
        session_id = self._resolve_session_id(arguments)
        if not session_id:
            return self._json({"status": "failed", "error": "session_id_required"})
        session = self._sessions.get(session_id)
        if session is None:
            return self._json({"status": "failed", "error": "session_not_found", "sessionId": session_id})
        if session.status == "running":
            return self._json({"status": "failed", "error": "session_not_finished", "sessionId": session_id})
        del self._sessions[session_id]
        return self._json({"status": "ok", "sessionId": session_id, "removed": True})

    async def _clear(self, arguments: dict[str, Any]) -> str:
        session = self._get_session(arguments)
        if session is None:
            return self._missing_session_response(arguments)
        async with session.output_lock:
            session.output = ""
        return self._json({"status": "ok", "sessionId": session.session_id, "cleared": True})

    async def _capture_stream(
        self,
        session: ProcessSession,
        stream: asyncio.StreamReader | None,
    ) -> None:
        if stream is None:
            return
        while True:
            chunk = await stream.read(4096)
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="ignore")
            async with session.output_lock:
                session.output += text

    async def _watch_process(self, session: ProcessSession) -> None:
        return_code = await session.process.wait()
        session.exit_code = return_code
        session.ended_at = asyncio.get_running_loop().time()
        session.status = "completed" if return_code == 0 else "failed"
        session.done_event.set()

    @staticmethod
    def _resolve_session_id(arguments: dict[str, Any]) -> str:
        value = arguments.get("sessionId", arguments.get("session_id", ""))
        return str(value or "").strip()

    def _get_session(self, arguments: dict[str, Any]) -> ProcessSession | None:
        session_id = self._resolve_session_id(arguments)
        if not session_id:
            return None
        return self._sessions.get(session_id)

    def _missing_session_response(self, arguments: dict[str, Any]) -> str:
        session_id = self._resolve_session_id(arguments)
        if not session_id:
            return self._json({"status": "failed", "error": "session_id_required"})
        return self._json({"status": "failed", "error": "session_not_found", "sessionId": session_id})

    @staticmethod
    def _clamp_timeout_ms(value: Any) -> int:
        try:
            timeout = int(float(value))
        except (TypeError, ValueError):
            timeout = 0
        if timeout < 0:
            return 0
        return min(timeout, MAX_POLL_WAIT_MS)

    @staticmethod
    def _json(payload: dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True)
