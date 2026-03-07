from __future__ import annotations

import asyncio
from dataclasses import dataclass
import inspect
import json
from pathlib import Path
from typing import Any, Awaitable, Callable

from clawlite.core.subagent import SubagentLimitError, SubagentManager, SubagentRun
from clawlite.session.store import SessionStore
from clawlite.tools.base import Tool, ToolContext


Runner = Callable[[str, str], Awaitable[Any]]
ResumeRunnerFactory = Callable[[SubagentRun], Runner]


@dataclass(slots=True)
class _ContinuationContext:
    summary: str = ""
    session_id: str = ""
    count: int = 0
    query: str = ""

    @property
    def applied(self) -> bool:
        return bool(self.summary)


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _preview(role: str, content: str, *, max_chars: int = 120) -> str:
    clean_role = str(role or "").strip().lower() or "unknown"
    clean_text = " ".join(str(content or "").strip().split())
    if len(clean_text) > max_chars:
        clean_text = f"{clean_text[:max_chars]}..."
    return f"{clean_role}: {clean_text}" if clean_text else clean_role


def _compact(value: Any, *, max_chars: int) -> str:
    clean = " ".join(str(value or "").strip().split())
    if len(clean) <= max_chars:
        return clean
    keep = max(1, max_chars - 3)
    return f"{clean[:keep]}..."


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


def _accepts_parameter(func: Any, parameter: str) -> bool:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return False
    if parameter in signature.parameters:
        return True
    return any(item.kind == inspect.Parameter.VAR_KEYWORD for item in signature.parameters.values())


async def _lookup_continuation_context(
    memory: Any | None,
    *,
    session_id: str,
    user_id: str,
    message: str,
) -> _ContinuationContext:
    retrieve_fn = getattr(memory, "retrieve", None)
    if not callable(retrieve_fn):
        return _ContinuationContext()

    query = _compact(message, max_chars=240)
    if not query:
        return _ContinuationContext()

    kwargs: dict[str, Any] = {"limit": 3, "method": "rag"}
    if _accepts_parameter(retrieve_fn, "session_id"):
        kwargs["session_id"] = session_id
    if user_id and _accepts_parameter(retrieve_fn, "user_id"):
        kwargs["user_id"] = user_id
    if _accepts_parameter(retrieve_fn, "include_shared"):
        kwargs["include_shared"] = True

    try:
        payload = retrieve_fn(query, **kwargs)
        if inspect.isawaitable(payload):
            payload = await payload
    except TypeError:
        try:
            payload = retrieve_fn(query, limit=3, method="rag")
            if inspect.isawaitable(payload):
                payload = await payload
        except Exception:
            return _ContinuationContext()
    except Exception:
        return _ContinuationContext()

    if not isinstance(payload, dict):
        return _ContinuationContext()

    episodic_digest = payload.get("episodic_digest")
    if not isinstance(episodic_digest, dict):
        return _ContinuationContext()

    summary = _compact(episodic_digest.get("summary", ""), max_chars=240)
    if not summary:
        return _ContinuationContext()

    digest_session_id = _compact(episodic_digest.get("session_id", session_id), max_chars=96) or session_id
    try:
        count = int(episodic_digest.get("count", 0) or 0)
    except Exception:
        count = 0
    return _ContinuationContext(
        summary=summary,
        session_id=digest_session_id,
        count=max(0, count),
        query=query,
    )


def _apply_continuation_context(message: str, continuation: _ContinuationContext) -> str:
    clean_message = str(message or "").strip()
    if not continuation.applied or not clean_message:
        return clean_message
    if clean_message.startswith("[Continuation Context]"):
        return clean_message
    lines = ["[Continuation Context]"]
    if continuation.session_id:
        lines.append(f"Session: {continuation.session_id}")
    lines.append(f"Summary: {continuation.summary}")
    lines.extend(["", "[Task]", clean_message])
    return "\n".join(lines).strip()


def _continuation_payload(continuation: _ContinuationContext) -> dict[str, Any]:
    if not continuation.applied:
        return {}
    payload: dict[str, Any] = {
        "continuation_context_applied": True,
        "continuation_digest_summary": continuation.summary,
    }
    if continuation.session_id:
        payload["continuation_digest_session_id"] = continuation.session_id
    if continuation.count > 0:
        payload["continuation_digest_count"] = continuation.count
    return payload


def _continuation_from_metadata(metadata: dict[str, Any] | None) -> _ContinuationContext:
    payload = metadata if isinstance(metadata, dict) else {}
    summary = _compact(payload.get("continuation_digest_summary", ""), max_chars=240)
    if not summary:
        return _ContinuationContext()
    session_id = _compact(payload.get("continuation_digest_session_id", ""), max_chars=96)
    try:
        count = int(payload.get("continuation_digest_count", 0) or 0)
    except Exception:
        count = 0
    return _ContinuationContext(summary=summary, session_id=session_id, count=max(0, count))


def build_task_with_continuation_metadata(message: str, metadata: dict[str, Any] | None = None) -> str:
    return _apply_continuation_context(message, _continuation_from_metadata(metadata))


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
    payload = {
        "run_id": run.run_id,
        "session_id": run.session_id,
        "task": run.task,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }
    metadata = dict(getattr(run, "metadata", {}) or {})
    target_session_id = str(metadata.get("target_session_id", "") or "").strip()
    if target_session_id:
        payload["target_session_id"] = target_session_id
    share_scope = str(metadata.get("share_scope", "") or "").strip()
    if share_scope:
        payload["share_scope"] = share_scope
    for key in (
        "resume_attempts",
        "resume_attempts_max",
        "retry_budget_remaining",
        "expires_at",
        "last_status_reason",
        "continuation_digest_summary",
        "continuation_digest_session_id",
        "continuation_digest_count",
    ):
        value = metadata.get(key)
        if value in {"", None}:
            continue
        payload[key] = value
    if "resumable" in metadata:
        payload["resumable"] = bool(metadata.get("resumable"))
    if bool(metadata.get("continuation_context_applied", False)):
        payload["continuation_context_applied"] = True
    return payload


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

    def __init__(self, runner: Runner, *, runner_timeout_s: float = 60.0, memory: Any | None = None) -> None:
        self.runner = runner
        self.runner_timeout_s = max(0.1, float(runner_timeout_s or 60.0))
        self.memory = memory

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
        continuation = await _lookup_continuation_context(
            self.memory,
            session_id=session_id,
            user_id=str(ctx.user_id or "").strip(),
            message=message,
        )
        delegated_message = _apply_continuation_context(message, continuation)
        try:
            result = await asyncio.wait_for(self.runner(session_id, delegated_message), timeout=timeout_s)
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
        payload: dict[str, Any] = {
            "status": "ok",
            "session_id": session_id,
            "text": text,
            "model": model,
        }
        payload.update(_continuation_payload(continuation))
        return _json(payload)


class SessionsSpawnTool(Tool):
    name = "sessions_spawn"
    description = "Spawn delegated execution routed to target session."

    def __init__(self, manager: SubagentManager, runner: Runner, memory: Any | None = None) -> None:
        self.manager = manager
        self.runner = runner
        self.memory = memory

    def args_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "session_id": {"type": "string"},
                "sessionId": {"type": "string"},
                "sessionKey": {"type": "string"},
                "share_scope": {"type": "string", "enum": ["private", "parent", "family"]},
                "shareScope": {"type": "string", "enum": ["private", "parent", "family"]},
            },
            "required": ["task"],
        }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        task = str(arguments.get("task", "")).strip()
        if not task:
            return _json({"status": "failed", "error": "task is required"})

        requested_target = _resolve_session_id(arguments, required=False)
        target_session_id = requested_target or f"{ctx.session_id}:subagent"
        share_scope = str(arguments.get("share_scope", arguments.get("shareScope", "")) or "").strip().lower()
        if share_scope and share_scope not in {"private", "parent", "family"}:
            return _json({"status": "failed", "error": "share_scope must be one of private|parent|family"})
        policy_fn = None
        if share_scope:
            policy_fn = getattr(self.memory, "set_working_memory_share_scope", None)
            if not callable(policy_fn):
                return _json(
                    {
                        "status": "failed",
                        "session_id": ctx.session_id,
                        "target_session_id": target_session_id,
                        "error": "share_scope_unsupported",
                    }
                )
            try:
                payload = policy_fn(target_session_id, share_scope)
                if inspect.isawaitable(payload):
                    await payload
            except Exception as exc:
                return _json(
                    {
                        "status": "failed",
                        "session_id": ctx.session_id,
                        "target_session_id": target_session_id,
                        "error": str(exc),
                    }
                )

        continuation = await _lookup_continuation_context(
            self.memory,
            session_id=target_session_id,
            user_id=str(ctx.user_id or "").strip(),
            message=task,
        )

        async def _target_runner(_owner_session_id: str, delegated_task: str) -> str:
            result = self.runner(
                target_session_id,
                _apply_continuation_context(delegated_task, continuation),
            )
            if inspect.isawaitable(result):
                result = await result
            return str(getattr(result, "text", result) or "")

        spawn_metadata: dict[str, str | int | bool] = {
            "target_session_id": target_session_id,
        }
        if share_scope:
            spawn_metadata["share_scope"] = share_scope
        if str(ctx.user_id or "").strip():
            spawn_metadata["target_user_id"] = str(ctx.user_id).strip()
        if continuation.applied:
            spawn_metadata["continuation_context_applied"] = True
            spawn_metadata["continuation_digest_summary"] = continuation.summary
            if continuation.session_id:
                spawn_metadata["continuation_digest_session_id"] = continuation.session_id
            if continuation.count > 0:
                spawn_metadata["continuation_digest_count"] = continuation.count

        try:
            run = await self.manager.spawn(
                session_id=ctx.session_id,
                task=task,
                runner=_target_runner,
                metadata=spawn_metadata,
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

        payload: dict[str, Any] = {
            "status": "ok",
            "run_id": run.run_id,
            "session_id": run.session_id,
            "target_session_id": target_session_id,
            "share_scope": share_scope or "",
            "state": run.status,
        }
        payload.update(_continuation_payload(continuation))
        return _json(payload)


class SubagentsTool(Tool):
    name = "subagents"
    description = "List or cancel subagent runs."

    def __init__(self, manager: SubagentManager, *, resume_runner_factory: ResumeRunnerFactory | None = None) -> None:
        self.manager = manager
        self.resume_runner_factory = resume_runner_factory

    def args_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "kill", "sweep", "resume"], "default": "list"},
                "session_id": {"type": "string"},
                "sessionId": {"type": "string"},
                "sessionKey": {"type": "string"},
                "run_id": {"type": "string"},
                "runId": {"type": "string"},
                "all": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1},
            },
        }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        action = str(arguments.get("action", "list") or "list").strip().lower()
        session_id = _resolve_session_id(arguments, required=False) or ctx.session_id

        if action == "list":
            maintenance = await self.manager.sweep_async()
            rows = self.manager.list_runs(session_id=session_id)
            return _json(
                {
                    "status": "ok",
                    "action": "list",
                    "session_id": session_id,
                    "maintenance": maintenance,
                    "count": len(rows),
                    "runs": [_run_to_payload(run) for run in rows],
                }
            )

        if action == "sweep":
            maintenance = await self.manager.sweep_async()
            return _json(
                {
                    "status": "ok",
                    "action": "sweep",
                    "session_id": session_id,
                    "maintenance": maintenance,
                }
            )

        if action == "resume":
            if self.resume_runner_factory is None:
                return _json(
                    {
                        "status": "failed",
                        "action": "resume",
                        "error": "resume_unsupported",
                    }
                )
            run_id = str(arguments.get("run_id") or arguments.get("runId") or "").strip()
            resume_all = _coerce_bool(arguments.get("all"), default=False)
            limit = _coerce_limit(arguments.get("limit"), default=20, minimum=1, maximum=200)
            target_runs: list[SubagentRun] = []
            if run_id:
                run = self.manager.get_run(run_id)
                if run is None:
                    return _json(
                        {
                            "status": "failed",
                            "action": "resume",
                            "run_id": run_id,
                            "error": "run_not_found",
                        }
                    )
                target_runs = [run]
            elif resume_all:
                target_runs = self.manager.list_resumable_runs(session_id=session_id, limit=limit)
            else:
                return _json(
                    {
                        "status": "failed",
                        "action": "resume",
                        "error": "run_id/runId is required when all=false",
                    }
                )

            resumed: list[dict[str, Any]] = []
            failed: list[dict[str, str]] = []
            for run in target_runs:
                try:
                    updated = await self.manager.resume(
                        run_id=run.run_id,
                        runner=self.resume_runner_factory(run),
                    )
                except Exception as exc:
                    failed.append({"run_id": run.run_id, "error": str(exc)})
                    continue
                resumed.append(_run_to_payload(updated))
            status = "ok" if resumed or not failed else "failed"
            return _json(
                {
                    "status": status,
                    "action": "resume",
                    "session_id": session_id,
                    "requested": len(target_runs),
                    "resumed": len(resumed),
                    "failed": failed,
                    "runs": resumed,
                }
            )

        if action == "kill":
            run_id = str(arguments.get("run_id") or arguments.get("runId") or "").strip()
            kill_all = _coerce_bool(arguments.get("all"), default=False)
            if kill_all:
                cancelled = int(await self.manager.cancel_session_async(session_id) or 0)
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
            cancelled = bool(await self.manager.cancel_async(run_id))
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
        maintenance = await self.manager.sweep_async()
        runs = self.manager.list_runs(session_id=session_id)
        active_subagents = sum(1 for run in runs if run.status in {"running", "queued"})
        subagent_counts: dict[str, int] = {}
        resumable_subagents = 0
        exhausted_retry_budget = 0
        for run in runs:
            subagent_counts[run.status] = subagent_counts.get(run.status, 0) + 1
            metadata = dict(getattr(run, "metadata", {}) or {})
            if bool(metadata.get("resumable", False)):
                resumable_subagents += 1
            try:
                remaining = int(metadata.get("retry_budget_remaining", 0) or 0)
            except Exception:
                remaining = 0
            if remaining <= 0 and run.status in {"error", "cancelled", "interrupted", "expired"}:
                exhausted_retry_budget += 1
        return _json(
            {
                "status": "ok",
                "session_id": session_id,
                "exists": exists,
                "message_count": message_count,
                "last_message": last_message,
                "active_subagents": active_subagents,
                "subagent_counts": subagent_counts,
                "resumable_subagents": resumable_subagents,
                "exhausted_retry_budget": exhausted_retry_budget,
                "maintenance": maintenance,
            }
        )
