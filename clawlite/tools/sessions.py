from __future__ import annotations

import asyncio
from dataclasses import dataclass
import inspect
import json
from pathlib import Path
from typing import Any, Awaitable, Callable
import uuid

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


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = [value]
    out: list[str] = []
    for item in items:
        clean = str(item or "").strip()
        if clean:
            out.append(clean)
    return out


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


def _read_session_messages(
    sessions: SessionStore,
    session_id: str,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    path = _session_file_path(sessions, session_id)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    valid_lines: list[str] = []
    corrupt_lines = 0
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            corrupt_lines += 1
            continue
        valid_lines.append(raw)
        role = str(payload.get("role", "")).strip()
        content = str(payload.get("content", "")).strip()
        if not role or not content:
            continue
        row: dict[str, Any] = {
            "role": role,
            "content": content,
        }
        ts = str(payload.get("ts", "") or "").strip()
        if ts:
            row["ts"] = ts
        metadata = payload.get("metadata", {})
        if isinstance(metadata, dict) and metadata:
            row["metadata"] = dict(metadata)
        rows.append(row)

    if corrupt_lines:
        repair = getattr(sessions, "_repair_file", None)
        if callable(repair):
            try:
                repair(path, valid_lines)
            except Exception:
                pass

    return rows[-max(1, int(limit or 1)) :]


def _last_message_preview(sessions: SessionStore, session_id: str) -> dict[str, str] | None:
    rows = _read_session_messages(sessions, session_id, limit=1)
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


def _subagent_status_counts(runs: list[SubagentRun]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for run in runs:
        counts[run.status] = counts.get(run.status, 0) + 1
    return counts


def _recent_subagent_runs(runs: list[SubagentRun], *, limit: int = 3) -> list[dict[str, Any]]:
    return [_run_to_payload(run) for run in runs[: max(1, int(limit or 1))]]


def _parallel_group_summaries(
    runs: list[SubagentRun],
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for run in runs:
        metadata = dict(getattr(run, "metadata", {}) or {})
        group_id = str(metadata.get("parallel_group_id", "") or "").strip()
        if not group_id:
            continue
        row = groups.get(group_id)
        if row is None:
            row = {
                "group_id": group_id,
                "session_id": run.session_id,
                "requested": int(metadata.get("parallel_group_size", 0) or 0),
                "run_count": 0,
                "active_subagents": 0,
                "resumable_subagents": 0,
                "status_counts": {},
                "target_session_ids": [],
                "run_ids": [],
                "last_updated_at": "",
            }
            groups[group_id] = row
        row["run_count"] += 1
        if run.status in {"running", "queued"}:
            row["active_subagents"] += 1
        if bool(metadata.get("resumable", False)):
            row["resumable_subagents"] += 1
        status_counts = row["status_counts"]
        status_counts[run.status] = status_counts.get(run.status, 0) + 1
        target_session_id = str(metadata.get("target_session_id", "") or "").strip()
        if target_session_id and target_session_id not in row["target_session_ids"]:
            row["target_session_ids"].append(target_session_id)
        row["run_ids"].append(run.run_id)
        updated_at = str(run.updated_at or run.finished_at or run.started_at or "").strip()
        if updated_at and updated_at >= str(row["last_updated_at"] or ""):
            row["last_updated_at"] = updated_at
    ordered = sorted(
        groups.values(),
        key=lambda row: (str(row.get("last_updated_at", "") or ""), str(row.get("group_id", "") or "")),
        reverse=True,
    )
    return ordered[: max(1, int(limit or 1))]


def _default_target_session_ids(
    owner_session_id: str,
    *,
    requested_target: str,
    count: int,
) -> list[str]:
    if count <= 1:
        return [requested_target or f"{owner_session_id}:subagent"]
    base = requested_target or f"{owner_session_id}:subagent"
    return [f"{base}:{idx}" for idx in range(1, count + 1)]


def _timeline_timestamp(payload: dict[str, Any]) -> str:
    for key in ("ts", "at", "finished_at", "updated_at", "started_at"):
        value = str(payload.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _message_timeline_event(session_id: str, row: dict[str, Any]) -> dict[str, Any]:
    role = str(row.get("role", "") or "").strip()
    content = str(row.get("content", "") or "").strip()
    payload: dict[str, Any] = {
        "kind": "message",
        "session_id": session_id,
        "role": role,
        "content": content,
        "preview": _preview(role, content),
    }
    ts = str(row.get("ts", "") or "").strip()
    if ts:
        payload["ts"] = ts
    metadata = row.get("metadata")
    if isinstance(metadata, dict) and metadata:
        payload["metadata"] = dict(metadata)
    return payload


def _subagent_timeline_event(session_id: str, run: SubagentRun) -> dict[str, Any]:
    payload = _run_to_payload(run)
    payload["kind"] = "subagent_run"
    payload["session_id"] = session_id
    payload["at"] = str(run.finished_at or run.updated_at or run.started_at or "").strip()
    excerpt = str(run.error or run.result or run.task or "").strip()
    if excerpt:
        payload["preview"] = _preview("subagent", excerpt)
    return payload


def _merge_session_timeline(
    session_id: str,
    messages: list[dict[str, Any]],
    runs: list[SubagentRun],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    events.extend(_message_timeline_event(session_id, row) for row in messages)
    events.extend(_subagent_timeline_event(session_id, run) for run in runs)
    events.sort(key=lambda row: (_timeline_timestamp(row), row.get("kind", "")))
    return events[-max(1, int(limit or 1)) :]


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
        "target_user_id",
        "parallel_group_id",
        "parallel_group_index",
        "parallel_group_size",
        "resume_attempts",
        "resume_attempts_max",
        "retry_budget_remaining",
        "expires_at",
        "last_status_reason",
        "last_status_at",
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

    def __init__(self, sessions: SessionStore, manager: SubagentManager | None = None) -> None:
        self.sessions = sessions
        self.manager = manager

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
        maintenance = (
            await self.manager.sweep_async()
            if self.manager is not None
            else {"expired": 0, "orphaned_running": 0, "orphaned_queued": 0}
        )
        ids = self.sessions.list_sessions()[:limit]
        rows: list[dict[str, Any]] = []
        for session_id in ids:
            preview = _last_message_preview(self.sessions, session_id)
            payload: dict[str, Any] = {
                "session_id": session_id,
                "last_message": preview,
                "message_count": _count_session_messages(self.sessions, session_id),
            }
            if self.manager is not None:
                runs = self.manager.list_runs(session_id=session_id)
                payload["active_subagents"] = sum(1 for run in runs if run.status in {"running", "queued"})
                payload["resumable_subagents"] = sum(
                    1
                    for run in runs
                    if bool(dict(getattr(run, "metadata", {}) or {}).get("resumable", False))
                )
                payload["subagent_counts"] = _subagent_status_counts(runs)
                payload["recent_subagents"] = _recent_subagent_runs(runs, limit=2)
            rows.append(payload)
        return _json(
            {
                "status": "ok",
                "maintenance": maintenance,
                "count": len(rows),
                "sessions": rows,
            }
        )


class SessionsHistoryTool(Tool):
    name = "sessions_history"
    description = "Read history for a specific session."

    def __init__(self, sessions: SessionStore, manager: SubagentManager | None = None) -> None:
        self.sessions = sessions
        self.manager = manager

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
                "include_subagents": {"type": "boolean"},
                "includeSubagents": {"type": "boolean"},
                "subagent_limit": {"type": "integer", "minimum": 1},
                "subagentLimit": {"type": "integer", "minimum": 1},
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
        include_subagents = _coerce_bool(
            arguments.get("include_subagents", arguments.get("includeSubagents")),
            default=True,
        )
        subagent_limit = _coerce_limit(
            arguments.get("subagent_limit", arguments.get("subagentLimit")),
            default=min(limit, 20),
            minimum=1,
            maximum=200,
        )
        rows = _read_session_messages(self.sessions, session_id, limit=limit)
        if not include_tools:
            rows = [row for row in rows if str(row.get("role", "")).strip().lower() != "tool"]
        runs: list[SubagentRun] = []
        if include_subagents and self.manager is not None:
            runs = self.manager.list_runs(session_id=session_id)[:subagent_limit]
        timeline = _merge_session_timeline(session_id, rows, runs, limit=max(limit, subagent_limit))
        return _json(
            {
                "status": "ok",
                "session_id": session_id,
                "count": len(rows),
                "messages": rows,
                "subagent_count": len(runs),
                "subagent_runs": [_run_to_payload(run) for run in runs],
                "timeline_count": len(timeline),
                "timeline": timeline,
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
                "tasks": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "session_id": {"type": "string"},
                "sessionId": {"type": "string"},
                "sessionKey": {"type": "string"},
                "target_sessions": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "targetSessions": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "share_scope": {"type": "string", "enum": ["private", "parent", "family"]},
                "shareScope": {"type": "string", "enum": ["private", "parent", "family"]},
            },
            "required": [],
        }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        tasks = _coerce_string_list(arguments.get("tasks"))
        if not tasks:
            task = str(arguments.get("task", "")).strip()
            if task:
                tasks = [task]
        if not tasks:
            return _json({"status": "failed", "error": "task or tasks is required"})

        requested_target = _resolve_session_id(arguments, required=False)
        requested_targets = _coerce_string_list(arguments.get("target_sessions", arguments.get("targetSessions")))
        if requested_targets and len(requested_targets) != len(tasks):
            return _json({"status": "failed", "error": "target_sessions length must match tasks"})
        if len(tasks) > 1 and requested_target and not requested_targets:
            requested_targets = _default_target_session_ids(
                ctx.session_id,
                requested_target=requested_target,
                count=len(tasks),
            )
        if len(tasks) == 1 and requested_targets:
            requested_target = requested_targets[0]
        target_session_id = requested_target or f"{ctx.session_id}:subagent"
        share_scope = str(arguments.get("share_scope", arguments.get("shareScope", "")) or "").strip().lower()
        if share_scope and share_scope not in {"private", "parent", "family"}:
            return _json({"status": "failed", "error": "share_scope must be one of private|parent|family"})
        policy_fn = getattr(self.memory, "set_working_memory_share_scope", None) if share_scope else None
        if share_scope and not callable(policy_fn):
            return _json(
                {
                    "status": "failed",
                    "session_id": ctx.session_id,
                    "target_session_id": target_session_id,
                    "error": "share_scope_unsupported",
                }
            )

        target_session_ids = requested_targets or _default_target_session_ids(
            ctx.session_id,
            requested_target=requested_target,
            count=len(tasks),
        )
        if len(tasks) == 1:
            task = tasks[0]
            target_session_id = target_session_ids[0]
            if share_scope and callable(policy_fn):
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

        group_id = uuid.uuid4().hex[:12]
        spawned: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        for idx, (task, target_session_id) in enumerate(zip(tasks, target_session_ids, strict=False), start=1):
            if share_scope and callable(policy_fn):
                try:
                    payload = policy_fn(target_session_id, share_scope)
                    if inspect.isawaitable(payload):
                        await payload
                except Exception as exc:
                    failed.append(
                        {
                            "task": task,
                            "target_session_id": target_session_id,
                            "error": str(exc),
                        }
                    )
                    continue

            continuation = await _lookup_continuation_context(
                self.memory,
                session_id=target_session_id,
                user_id=str(ctx.user_id or "").strip(),
                message=task,
            )

            async def _target_runner(
                _owner_session_id: str,
                delegated_task: str,
                *,
                _target_session_id: str = target_session_id,
                _continuation: _ContinuationContext = continuation,
            ) -> str:
                result = self.runner(
                    _target_session_id,
                    _apply_continuation_context(delegated_task, _continuation),
                )
                if inspect.isawaitable(result):
                    result = await result
                return str(getattr(result, "text", result) or "")

            spawn_metadata = {
                "target_session_id": target_session_id,
                "parallel_group_id": group_id,
                "parallel_group_index": idx,
                "parallel_group_size": len(tasks),
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
                failed.append(
                    {
                        "task": task,
                        "target_session_id": target_session_id,
                        "error": str(exc),
                    }
                )
                continue

            run_payload = _run_to_payload(run)
            run_payload.update(_continuation_payload(continuation))
            spawned.append(run_payload)

        status = "ok" if spawned and not failed else "partial" if spawned else "failed"
        return _json(
            {
                "status": status,
                "mode": "parallel",
                "session_id": ctx.session_id,
                "group_id": group_id,
                "requested": len(tasks),
                "spawned": len(spawned),
                "failed": failed,
                "share_scope": share_scope or "",
                "target_session_ids": list(target_session_ids),
                "run_ids": [row["run_id"] for row in spawned],
                "runs": spawned,
            }
        )


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
                    "parallel_group_count": len(_parallel_group_summaries(rows)),
                    "parallel_groups": _parallel_group_summaries(rows),
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
                "recent_subagents": _recent_subagent_runs(runs, limit=3),
                "latest_subagent": _run_to_payload(runs[0]) if runs else None,
                "parallel_group_count": len(_parallel_group_summaries(runs)),
                "parallel_groups": _parallel_group_summaries(runs),
                "maintenance": maintenance,
            }
        )
