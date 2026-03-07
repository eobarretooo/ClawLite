from __future__ import annotations

import asyncio
import json
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable, Coroutine, TypeVar


@dataclass(slots=True)
class SubagentRun:
    run_id: str
    session_id: str
    task: str
    status: str = "running"
    result: str = ""
    error: str = ""
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str = ""
    queued_at: str = ""
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, str | int | bool] = field(default_factory=dict)


class SubagentLimitError(RuntimeError):
    """Raised when subagent queueing/quota limits are exceeded."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_utc(value: str) -> datetime | None:
    clean = str(value or "").strip()
    if not clean:
        return None
    try:
        parsed = datetime.fromisoformat(clean)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


Runner = Callable[[str, str], Awaitable[str]]
_T = TypeVar("_T")


class SubagentManager:
    """Executes delegated prompts in background asyncio tasks."""

    def __init__(
        self,
        *,
        state_path: str | Path | None = None,
        max_concurrent_runs: int = 2,
        max_queued_runs: int = 32,
        per_session_quota: int = 4,
        max_resume_attempts: int = 2,
        run_ttl_seconds: float | None = 900.0,
        zombie_grace_seconds: float = 5.0,
    ) -> None:
        if max_concurrent_runs < 1:
            raise ValueError("max_concurrent_runs must be >= 1")
        if max_queued_runs < 0:
            raise ValueError("max_queued_runs must be >= 0")
        if per_session_quota < 1:
            raise ValueError("per_session_quota must be >= 1")
        if max_resume_attempts < 0:
            raise ValueError("max_resume_attempts must be >= 0")
        if run_ttl_seconds is not None and float(run_ttl_seconds) <= 0:
            raise ValueError("run_ttl_seconds must be > 0 when provided")
        if float(zombie_grace_seconds) < 0:
            raise ValueError("zombie_grace_seconds must be >= 0")

        base = Path(state_path) if state_path else (Path.home() / ".clawlite" / "state" / "subagents")
        self._state_file = (base / "runs.json") if base.suffix == "" else base
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self.max_concurrent_runs = int(max_concurrent_runs)
        self.max_queued_runs = int(max_queued_runs)
        self.per_session_quota = int(per_session_quota)
        self.max_resume_attempts = int(max_resume_attempts)
        self.run_ttl_seconds = None if run_ttl_seconds is None else float(run_ttl_seconds)
        self.zombie_grace_seconds = float(zombie_grace_seconds)
        self._runs: dict[str, SubagentRun] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._queue: deque[str] = deque()
        self._pending_runners: dict[str, Runner] = {}
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._load_state()

    @staticmethod
    def _metadata_int(
        metadata: dict[str, str | int | bool],
        key: str,
        default: int,
    ) -> int:
        try:
            return int(metadata.get(key, default))
        except Exception:
            return int(default)

    def _sync_retry_metadata(self, run: SubagentRun) -> None:
        attempts = max(0, self._metadata_int(run.metadata, "resume_attempts", 0))
        attempts_max = max(0, self._metadata_int(run.metadata, "resume_attempts_max", self.max_resume_attempts))
        run.metadata["resume_attempts"] = attempts
        run.metadata["resume_attempts_max"] = attempts_max
        run.metadata["retry_budget_remaining"] = max(0, attempts_max - attempts)

    def _default_expires_at(self, *, now_dt: datetime | None = None) -> str:
        if self.run_ttl_seconds is None:
            return ""
        current = now_dt or datetime.now(timezone.utc)
        return (current + timedelta(seconds=self.run_ttl_seconds)).isoformat()

    def _ensure_run_defaults(self, run: SubagentRun, *, now_dt: datetime | None = None, refresh_expiry: bool = False) -> None:
        self._sync_retry_metadata(run)
        if self.run_ttl_seconds is None:
            return
        if refresh_expiry or not str(run.metadata.get("expires_at", "") or "").strip():
            run.metadata["expires_at"] = self._default_expires_at(now_dt=now_dt)

    def _run_is_expired(self, run: SubagentRun, *, now_dt: datetime) -> bool:
        expires_at = _parse_utc(str(run.metadata.get("expires_at", "") or ""))
        return bool(expires_at is not None and expires_at <= now_dt)

    def _run_is_stale(self, run: SubagentRun, *, now_dt: datetime) -> bool:
        reference = _parse_utc(str(run.updated_at or "") or "") or _parse_utc(str(run.started_at or "") or "")
        if reference is None:
            return True
        return (now_dt - reference).total_seconds() >= self.zombie_grace_seconds

    def _mark_terminal(
        self,
        run: SubagentRun,
        *,
        status: str,
        reason: str,
        error: str = "",
        resumable: bool,
        now_iso: str,
    ) -> None:
        run.status = status
        run.finished_at = now_iso
        run.updated_at = now_iso
        if error:
            run.error = error
        run.metadata["resumable"] = resumable
        run.metadata["last_status_reason"] = reason
        run.metadata["last_status_at"] = now_iso
        self._sync_retry_metadata(run)

    def _empty_sweep_stats(self) -> dict[str, int]:
        return {
            "expired": 0,
            "orphaned_running": 0,
            "orphaned_queued": 0,
        }

    def _remove_from_queue_locked(self, run_id: str) -> None:
        if run_id not in self._queue:
            return
        self._queue = deque(item for item in self._queue if item != run_id)

    def _sweep_locked(self) -> dict[str, int]:
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        stats = self._empty_sweep_stats()
        changed = False

        for run in self._runs.values():
            self._ensure_run_defaults(run, now_dt=now_dt, refresh_expiry=False)

            if run.status == "queued":
                if self._run_is_expired(run, now_dt=now_dt):
                    self._remove_from_queue_locked(run.run_id)
                    self._pending_runners.pop(run.run_id, None)
                    self._mark_terminal(
                        run,
                        status="expired",
                        reason="expired",
                        error="subagent run expired before execution",
                        resumable=False,
                        now_iso=now_iso,
                    )
                    stats["expired"] += 1
                    changed = True
                    continue
                has_pending = run.run_id in self._pending_runners
                in_queue = run.run_id in self._queue
                if (not has_pending or not in_queue) and self._run_is_stale(run, now_dt=now_dt):
                    self._remove_from_queue_locked(run.run_id)
                    self._pending_runners.pop(run.run_id, None)
                    self._mark_terminal(
                        run,
                        status="interrupted",
                        reason="orphaned_queue_entry",
                        error="subagent queue entry lost before execution",
                        resumable=bool(run.metadata.get("retry_budget_remaining", 0)),
                        now_iso=now_iso,
                    )
                    stats["orphaned_queued"] += 1
                    changed = True
                    continue

            if run.status == "running":
                task = self._tasks.get(run.run_id)
                if self._run_is_expired(run, now_dt=now_dt):
                    if task is not None and not task.done():
                        task.cancel()
                    self._tasks.pop(run.run_id, None)
                    self._pending_runners.pop(run.run_id, None)
                    self._mark_terminal(
                        run,
                        status="expired",
                        reason="expired",
                        error="subagent run expired while running",
                        resumable=False,
                        now_iso=now_iso,
                    )
                    stats["expired"] += 1
                    changed = True
                    continue
                if (task is None or task.done()) and self._run_is_stale(run, now_dt=now_dt):
                    self._tasks.pop(run.run_id, None)
                    self._pending_runners.pop(run.run_id, None)
                    self._mark_terminal(
                        run,
                        status="interrupted",
                        reason="orphaned_task",
                        error="subagent worker disappeared before completion",
                        resumable=bool(run.metadata.get("retry_budget_remaining", 0)),
                        now_iso=now_iso,
                    )
                    stats["orphaned_running"] += 1
                    changed = True

        if changed:
            self._drain_queue_locked()
            self._save_state()
        return stats

    def _bind_loop(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
            return
        if self._loop is not loop:
            raise RuntimeError("SubagentManager cannot be used across multiple event loops")

    def _run_sync(self, coro: Coroutine[object, object, _T], *, method_name: str) -> _T:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(f"{method_name} cannot be called from an active event loop; use the async variant")

        target_loop = self._loop
        if target_loop is not None and target_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, target_loop)
            return future.result()
        return asyncio.run(coro)

    def _to_payload(self, run: SubagentRun) -> dict[str, str | int | bool | dict[str, str | int | bool]]:
        return {
            "run_id": run.run_id,
            "session_id": run.session_id,
            "task": run.task,
            "status": run.status,
            "result": run.result,
            "error": run.error,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "queued_at": run.queued_at,
            "updated_at": run.updated_at,
            "metadata": dict(run.metadata),
        }

    @staticmethod
    def _from_payload(payload: dict[str, object]) -> SubagentRun | None:
        run_id = str(payload.get("run_id", "")).strip()
        session_id = str(payload.get("session_id", "")).strip()
        task = str(payload.get("task", "")).strip()
        if not run_id or not session_id or not task:
            return None
        metadata_raw = payload.get("metadata", {})
        metadata: dict[str, str | int | bool]
        if isinstance(metadata_raw, dict):
            metadata = {
                str(k): v
                for k, v in metadata_raw.items()
                if isinstance(v, (str, int, bool))
            }
        else:
            metadata = {}
        return SubagentRun(
            run_id=run_id,
            session_id=session_id,
            task=task,
            status=str(payload.get("status", "queued") or "queued"),
            result=str(payload.get("result", "")),
            error=str(payload.get("error", "")),
            started_at=str(payload.get("started_at", "") or _utc_now()),
            finished_at=str(payload.get("finished_at", "")),
            queued_at=str(payload.get("queued_at", "")),
            updated_at=str(payload.get("updated_at", "") or _utc_now()),
            metadata=metadata,
        )

    def _save_state(self) -> None:
        payload = {
            "max_concurrent_runs": self.max_concurrent_runs,
            "max_queued_runs": self.max_queued_runs,
            "per_session_quota": self.per_session_quota,
            "queue": list(self._queue),
            "runs": [self._to_payload(run) for run in self._runs.values()],
        }
        tmp_path = self._state_file.with_suffix(self._state_file.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp_path.replace(self._state_file)

    @staticmethod
    def _normalize_run_metadata(
        metadata: dict[str, str | int | bool] | None,
    ) -> dict[str, str | int | bool]:
        if not isinstance(metadata, dict):
            return {}
        out: dict[str, str | int | bool] = {}
        for key, value in metadata.items():
            if not isinstance(value, (str, int, bool)):
                continue
            clean_key = str(key or "").strip()
            if not clean_key:
                continue
            out[clean_key] = value
        return out

    def _load_state(self) -> None:
        if not self._state_file.exists():
            return
        try:
            raw = json.loads(self._state_file.read_text(encoding="utf-8"))
        except Exception:
            return
        runs_raw = raw.get("runs", []) if isinstance(raw, dict) else []
        queue_raw = raw.get("queue", []) if isinstance(raw, dict) else []
        if not isinstance(runs_raw, list):
            runs_raw = []
        if not isinstance(queue_raw, list):
            queue_raw = []

        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        for row in runs_raw:
            if not isinstance(row, dict):
                continue
            run = self._from_payload(row)
            if run is None:
                continue
            self._ensure_run_defaults(run, now_dt=now_dt, refresh_expiry=False)
            if run.status in {"running", "queued"}:
                if self._run_is_expired(run, now_dt=now_dt):
                    self._mark_terminal(
                        run,
                        status="expired",
                        reason="expired",
                        error="subagent run expired during restart recovery",
                        resumable=False,
                        now_iso=now_iso,
                    )
                else:
                    self._mark_terminal(
                        run,
                        status="interrupted",
                        reason="manager_restart",
                        resumable=bool(run.metadata.get("retry_budget_remaining", 0)),
                        now_iso=now_iso,
                    )
            self._runs[run.run_id] = run

        for run_id in queue_raw:
            clean_run_id = str(run_id or "").strip()
            if clean_run_id and clean_run_id in self._runs:
                self._queue.append(clean_run_id)

    def _session_outstanding(self, session_id: str) -> int:
        return sum(
            1
            for run in self._runs.values()
            if run.session_id == session_id and run.status in {"running", "queued"}
        )

    def _running_count(self) -> int:
        return sum(1 for run in self._runs.values() if run.status == "running")

    def _mark_queued(self, run: SubagentRun, *, reason: str) -> None:
        now_iso = _utc_now()
        run.status = "queued"
        run.queued_at = run.queued_at or now_iso
        run.updated_at = now_iso
        run.metadata["resumable"] = False
        run.metadata["last_status_reason"] = reason
        run.metadata["last_status_at"] = now_iso
        self._sync_retry_metadata(run)

    def _mark_running(self, run: SubagentRun, *, reason: str) -> None:
        now_iso = _utc_now()
        run.status = "running"
        run.started_at = run.started_at or now_iso
        run.finished_at = ""
        run.error = ""
        run.result = ""
        run.updated_at = now_iso
        run.metadata["resumable"] = False
        run.metadata["last_status_reason"] = reason
        run.metadata["last_status_at"] = now_iso
        self._sync_retry_metadata(run)

    def _ensure_limits(self, session_id: str) -> None:
        outstanding = self._session_outstanding(session_id)
        if outstanding >= self.per_session_quota:
            raise SubagentLimitError(
                f"subagent quota reached for session '{session_id}' ({self.per_session_quota})"
            )

    def _start_worker_locked(self, run: SubagentRun, runner: Runner, *, reason: str) -> None:
        self._mark_running(run, reason=reason)

        async def _worker() -> None:
            status = "done"
            result = ""
            error = ""
            try:
                result = str(await runner(run.session_id, run.task))
            except asyncio.CancelledError:
                status = "cancelled"
                raise
            except Exception as exc:  # pragma: no cover
                status = "error"
                error = str(exc)
            finally:
                async with self._lock:
                    active = self._runs.get(run.run_id)
                    if active is None:
                        return
                    if active.status == "expired":
                        self._tasks.pop(run.run_id, None)
                        self._pending_runners.pop(run.run_id, None)
                        self._drain_queue_locked()
                        self._save_state()
                        return
                    now_iso = _utc_now()
                    active.status = status
                    active.result = result
                    active.error = error
                    active.finished_at = now_iso
                    active.updated_at = now_iso
                    active.metadata["resumable"] = (
                        status in {"error", "cancelled", "interrupted"}
                        and bool(active.metadata.get("retry_budget_remaining", 0))
                    )
                    active.metadata["last_status_reason"] = status
                    active.metadata["last_status_at"] = now_iso
                    self._sync_retry_metadata(active)
                    self._tasks.pop(run.run_id, None)
                    self._pending_runners.pop(run.run_id, None)
                    self._drain_queue_locked()
                    self._save_state()

        self._tasks[run.run_id] = asyncio.create_task(_worker())

    def _drain_queue_locked(self) -> None:
        while self._queue and self._running_count() < self.max_concurrent_runs:
            run_id = self._queue.popleft()
            run = self._runs.get(run_id)
            runner = self._pending_runners.get(run_id)
            if run is None or runner is None:
                continue
            self._start_worker_locked(run, runner, reason="dequeued")

    async def resume(self, *, run_id: str, runner: Runner) -> SubagentRun:
        self._bind_loop()
        clean_run_id = str(run_id or "").strip()
        if not clean_run_id:
            raise ValueError("run_id is required")

        async with self._lock:
            self._sweep_locked()
            run = self._runs.get(clean_run_id)
            if run is None:
                raise KeyError(clean_run_id)
            resumable = bool(run.metadata.get("resumable"))
            if run.status in {"done", "running"} and not resumable:
                raise ValueError(f"run '{clean_run_id}' is not resumable")
            now_dt = datetime.now(timezone.utc)
            if self._run_is_expired(run, now_dt=now_dt):
                now_iso = now_dt.isoformat()
                self._mark_terminal(
                    run,
                    status="expired",
                    reason="expired",
                    error="subagent run expired before resume",
                    resumable=False,
                    now_iso=now_iso,
                )
                self._save_state()
                raise ValueError(f"run '{clean_run_id}' expired before resume")
            self._ensure_limits(run.session_id)

            attempts = self._metadata_int(run.metadata, "resume_attempts", 0)
            attempts_max = self._metadata_int(run.metadata, "resume_attempts_max", self.max_resume_attempts)
            if attempts >= attempts_max:
                run.metadata["resumable"] = False
                run.metadata["retry_budget_remaining"] = 0
                self._save_state()
                raise ValueError(f"run '{clean_run_id}' exhausted retry budget")

            attempts = int(run.metadata.get("resume_attempts", 0)) + 1
            run.metadata["resume_attempts"] = attempts
            self._ensure_run_defaults(run, now_dt=now_dt, refresh_expiry=True)

            if self._running_count() < self.max_concurrent_runs:
                self._pending_runners[run.run_id] = runner
                self._start_worker_locked(run, runner, reason="resume")
            else:
                if len(self._queue) >= self.max_queued_runs:
                    raise SubagentLimitError(
                        f"subagent queue limit reached ({self.max_queued_runs}); wait for existing runs to finish"
                    )
                self._pending_runners[run.run_id] = runner
                self._mark_queued(run, reason="resume_queued")
                self._queue.append(run.run_id)

            self._save_state()
            return run

    async def spawn(
        self,
        *,
        session_id: str,
        task: str,
        runner: Runner,
        metadata: dict[str, str | int | bool] | None = None,
    ) -> SubagentRun:
        self._bind_loop()
        clean_session_id = str(session_id or "").strip()
        clean_task = str(task or "").strip()
        if not clean_session_id:
            raise ValueError("session_id is required")
        if not clean_task:
            raise ValueError("task is required")
        normalized_metadata = self._normalize_run_metadata(metadata)

        async with self._lock:
            self._sweep_locked()
            self._ensure_limits(clean_session_id)
            run_id = uuid.uuid4().hex
            now_dt = datetime.now(timezone.utc)
            now_iso = now_dt.isoformat()
            run = SubagentRun(
                run_id=run_id,
                session_id=clean_session_id,
                task=clean_task,
                status="queued",
                started_at=now_iso,
                queued_at=now_iso,
                updated_at=now_iso,
                metadata={
                    **normalized_metadata,
                    "run_version": 1,
                    "resume_attempts": 0,
                    "resume_token": uuid.uuid4().hex,
                    "resumable": False,
                    "last_status_reason": "spawned",
                    "last_status_at": now_iso,
                },
            )
            self._ensure_run_defaults(run, now_dt=now_dt, refresh_expiry=False)
            self._runs[run_id] = run
            self._pending_runners[run_id] = runner
            if self._running_count() < self.max_concurrent_runs:
                self._start_worker_locked(run, runner, reason="spawn")
            else:
                if len(self._queue) >= self.max_queued_runs:
                    self._runs.pop(run_id, None)
                    self._pending_runners.pop(run_id, None)
                    raise SubagentLimitError(
                        f"subagent queue limit reached ({self.max_queued_runs}); wait for existing runs to finish"
                    )
                self._mark_queued(run, reason="queued_by_limit")
                self._queue.append(run_id)
            self._save_state()
            return run

    def list_runs(self, *, session_id: str | None = None, active_only: bool = False) -> list[SubagentRun]:
        values = list(self._runs.values())
        if session_id:
            values = [item for item in values if item.session_id == session_id]
        if active_only:
            values = [item for item in values if item.status in {"running", "queued"}]
        return sorted(values, key=lambda item: item.started_at, reverse=True)

    def get_run(self, run_id: str) -> SubagentRun | None:
        clean_run_id = str(run_id or "").strip()
        if not clean_run_id:
            return None
        return self._runs.get(clean_run_id)

    def list_resumable_runs(
        self,
        *,
        session_id: str | None = None,
        reason: str = "",
        limit: int = 50,
    ) -> list[SubagentRun]:
        clean_reason = str(reason or "").strip()
        max_items = max(1, int(limit))
        rows = self.list_runs(session_id=session_id, active_only=False)
        out: list[SubagentRun] = []
        for run in rows:
            metadata = dict(getattr(run, "metadata", {}) or {})
            if not bool(metadata.get("resumable", False)):
                continue
            if clean_reason and str(metadata.get("last_status_reason", "") or "").strip() != clean_reason:
                continue
            out.append(run)
            if len(out) >= max_items:
                break
        out.sort(key=lambda item: (item.updated_at or item.finished_at or item.started_at, item.run_id))
        return out

    def list_completed_unsynthesized(self, session_id: str, limit: int = 8) -> list[SubagentRun]:
        clean_session_id = str(session_id or "").strip()
        if not clean_session_id:
            return []
        max_items = max(1, int(limit))
        completed_statuses = {"done", "error", "cancelled", "interrupted", "expired"}

        rows = [
            run
            for run in self._runs.values()
            if run.session_id == clean_session_id
            and run.status in completed_statuses
            and not bool(run.metadata.get("synthesized", False))
        ]
        rows.sort(key=lambda item: (item.finished_at or "", item.run_id))
        return rows[:max_items]

    async def mark_synthesized_async(self, run_ids: list[str], *, digest_id: str = "") -> int:
        self._bind_loop()
        now_iso = _utc_now()
        clean_digest = str(digest_id or "").strip()
        count = 0
        seen: set[str] = set()
        async with self._lock:
            for run_id in run_ids:
                clean_run_id = str(run_id or "").strip()
                if not clean_run_id or clean_run_id in seen:
                    continue
                seen.add(clean_run_id)
                run = self._runs.get(clean_run_id)
                if run is None:
                    continue
                run.metadata["synthesized"] = True
                run.metadata["synthesized_at"] = now_iso
                if clean_digest:
                    run.metadata["synthesized_digest_id"] = clean_digest
                run.updated_at = now_iso
                self._sync_retry_metadata(run)
                count += 1

            if count > 0:
                self._save_state()
        return count

    def mark_synthesized(self, run_ids: list[str], *, digest_id: str = "") -> int:
        return self._run_sync(
            self.mark_synthesized_async(run_ids, digest_id=digest_id),
            method_name="mark_synthesized()",
        )

    def _cancel_locked(self, run_id: str) -> tuple[bool, bool]:
        task = self._tasks.get(run_id)
        if task is not None and not task.done():
            task.cancel()
            return True, False

        if run_id in self._queue:
            self._queue = deque(item for item in self._queue if item != run_id)
            run = self._runs.get(run_id)
            if run is not None:
                now_iso = _utc_now()
                self._mark_terminal(
                    run,
                    status="cancelled",
                    reason="cancelled_while_queued",
                    resumable=bool(run.metadata.get("retry_budget_remaining", 0)),
                    now_iso=now_iso,
                )
            self._pending_runners.pop(run_id, None)
            return True, True

        return False, False

    async def cancel_async(self, run_id: str) -> bool:
        self._bind_loop()
        clean_run_id = str(run_id or "").strip()
        async with self._lock:
            cancelled, persist = self._cancel_locked(clean_run_id)
            if persist:
                self._save_state()
            return cancelled

    def cancel(self, run_id: str) -> bool:
        return self._run_sync(self.cancel_async(run_id), method_name="cancel()")

    async def cancel_session_async(self, session_id: str) -> int:
        self._bind_loop()
        clean_session_id = str(session_id or "").strip()
        if not clean_session_id:
            return 0

        async with self._lock:
            run_ids = [
                run.run_id
                for run in self._runs.values()
                if run.session_id == clean_session_id and run.status in {"running", "queued"}
            ]
            total = 0
            persist = False
            for run_id in run_ids:
                cancelled, needs_persist = self._cancel_locked(run_id)
                if cancelled:
                    total += 1
                persist = persist or needs_persist
            if persist:
                self._save_state()
            return total

    def cancel_session(self, session_id: str) -> int:
        return self._run_sync(self.cancel_session_async(session_id), method_name="cancel_session()")

    async def sweep_async(self) -> dict[str, int]:
        self._bind_loop()
        async with self._lock:
            return self._sweep_locked()

    def sweep(self) -> dict[str, int]:
        return self._run_sync(self.sweep_async(), method_name="sweep()")
