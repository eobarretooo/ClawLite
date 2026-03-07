from __future__ import annotations

import inspect
import json
from collections import defaultdict
from typing import Any

from clawlite.core.subagent import SubagentManager, SubagentRun
from clawlite.tools.base import Tool, ToolContext
from clawlite.tools.sessions import _run_to_payload


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _coerce_limit(value: Any, *, default: int, minimum: int = 1, maximum: int = 200) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum
    return parsed


def _resolve_session_id(arguments: dict[str, Any]) -> str:
    value = arguments.get("session_id") or arguments.get("sessionId") or arguments.get("sessionKey") or ""
    return str(value or "").strip()


class AgentsListTool(Tool):
    name = "agents_list"
    description = "List the primary agent runtime and delegated subagent inventory."

    def __init__(self, engine: Any, manager: SubagentManager, *, memory: Any | None = None) -> None:
        self.engine = engine
        self.manager = manager
        self.memory = memory

    def args_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "sessionId": {"type": "string"},
                "sessionKey": {"type": "string"},
                "active_only": {"type": "boolean"},
                "activeOnly": {"type": "boolean"},
                "include_runs": {"type": "boolean"},
                "includeRuns": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1},
            },
        }

    async def _memory_policy_summary(self, *, session_id: str) -> tuple[bool, str]:
        policy_fn = getattr(self.memory, "integration_policy", None)
        if not callable(policy_fn):
            return True, ""
        try:
            verdict = policy_fn("subagent", session_id=session_id)
            if inspect.isawaitable(verdict):
                verdict = await verdict
        except Exception:
            return False, "policy_check_exception"

        if isinstance(verdict, bool):
            return verdict, "" if verdict else "blocked"
        if isinstance(verdict, dict):
            allowed = bool(verdict.get("allowed", verdict.get("allow", verdict.get("ok", True))))
            reason = str(verdict.get("reason", verdict.get("message", verdict.get("detail", ""))) or "").strip()
            return allowed, reason if not allowed else ""
        allowed = getattr(verdict, "allowed", None)
        if allowed is not None:
            is_allowed = bool(allowed)
            reason = str(getattr(verdict, "reason", "") or "").strip()
            return is_allowed, reason if not is_allowed else ""
        return True, ""

    @staticmethod
    def _provider_model(engine: Any) -> str:
        provider = getattr(engine, "provider", None)
        get_default_model = getattr(provider, "get_default_model", None)
        if not callable(get_default_model):
            return ""
        try:
            return str(get_default_model() or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _tool_count(engine: Any) -> int:
        schema_fn = getattr(getattr(engine, "tools", None), "schema", None)
        if not callable(schema_fn):
            return 0
        try:
            rows = schema_fn()
        except Exception:
            return 0
        if not isinstance(rows, list):
            return 0
        return len(rows)

    @staticmethod
    def _status_counts(runs: list[SubagentRun]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for run in runs:
            counts[run.status] = counts.get(run.status, 0) + 1
        return counts

    @classmethod
    def _session_inventory(cls, runs: list[SubagentRun], *, limit: int) -> list[dict[str, Any]]:
        grouped: dict[str, list[SubagentRun]] = defaultdict(list)
        for run in runs:
            grouped[str(run.session_id or "").strip()].append(run)

        rows: list[dict[str, Any]] = []
        for session_id, session_runs in grouped.items():
            if not session_id:
                continue
            status_counts = cls._status_counts(session_runs)
            resumable = sum(
                1 for run in session_runs if bool(dict(getattr(run, "metadata", {}) or {}).get("resumable", False))
            )
            latest = sorted(
                session_runs,
                key=lambda run: (str(run.updated_at or run.finished_at or run.started_at or ""), run.run_id),
                reverse=True,
            )[0]
            rows.append(
                {
                    "session_id": session_id,
                    "run_count": len(session_runs),
                    "active_subagents": sum(1 for run in session_runs if run.status in {"running", "queued"}),
                    "resumable_subagents": resumable,
                    "status_counts": status_counts,
                    "latest_run": _run_to_payload(latest),
                }
            )
        rows.sort(key=lambda row: (-int(row["run_count"]), str(row["session_id"])))
        return rows[: max(1, int(limit or 1))]

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        session_id = _resolve_session_id(arguments)
        active_only = _coerce_bool(arguments.get("active_only", arguments.get("activeOnly")), default=False)
        include_runs = _coerce_bool(arguments.get("include_runs", arguments.get("includeRuns")), default=True)
        limit = _coerce_limit(arguments.get("limit"), default=20, minimum=1, maximum=200)
        maintenance = await self.manager.sweep_async()
        runs = self.manager.list_runs(session_id=session_id or None, active_only=active_only)
        selected_runs = runs[:limit]
        policy_session_id = session_id or ctx.session_id
        spawn_allowed, spawn_block_reason = await self._memory_policy_summary(session_id=policy_session_id)
        session_inventory = self._session_inventory(runs, limit=limit)

        primary_payload: dict[str, Any] = {
            "id": "primary",
            "kind": "primary",
            "label": "ClawLite",
            "provider_model": self._provider_model(self.engine),
            "tool_count": self._tool_count(self.engine),
            "max_iterations": int(getattr(self.engine, "max_iterations", 0) or 0),
            "max_tokens": int(getattr(self.engine, "max_tokens", 0) or 0),
            "temperature": float(getattr(self.engine, "temperature", 0.0) or 0.0),
            "memory_window": int(getattr(self.engine, "memory_window", 0) or 0),
            "reasoning_effort": str(getattr(self.engine, "reasoning_effort_default", "") or "").strip(),
        }
        manager_payload: dict[str, Any] = {
            "id": "subagent_manager",
            "kind": "delegated",
            "label": "Subagent Manager",
            "spawn_allowed": spawn_allowed,
            "spawn_block_reason": spawn_block_reason,
            "max_concurrent_runs": int(getattr(self.manager, "max_concurrent_runs", 0) or 0),
            "max_queued_runs": int(getattr(self.manager, "max_queued_runs", 0) or 0),
            "per_session_quota": int(getattr(self.manager, "per_session_quota", 0) or 0),
            "max_resume_attempts": int(getattr(self.manager, "max_resume_attempts", 0) or 0),
            "run_ttl_seconds": getattr(self.manager, "run_ttl_seconds", None),
            "active_subagents": sum(1 for run in runs if run.status in {"running", "queued"}),
            "queued_subagents": sum(1 for run in runs if run.status == "queued"),
            "resumable_subagents": sum(
                1 for run in runs if bool(dict(getattr(run, "metadata", {}) or {}).get("resumable", False))
            ),
            "status_counts": self._status_counts(runs),
            "session_inventory_count": len(session_inventory),
            "active_sessions": [
                row["session_id"] for row in session_inventory if int(row.get("active_subagents", 0) or 0) > 0
            ],
        }
        return _json(
            {
                "status": "ok",
                "scope": "session" if session_id else "global",
                "session_id": session_id,
                "active_only": active_only,
                "maintenance": maintenance,
                "count": 2,
                "agents": [primary_payload, manager_payload],
                "run_count": len(runs),
                "runs": [_run_to_payload(run) for run in selected_runs] if include_runs else [],
                "session_inventory_count": len(session_inventory),
                "session_inventory": session_inventory,
            }
        )
