from __future__ import annotations

import asyncio
import json
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable


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


Runner = Callable[[str, str], Awaitable[str]]


class SubagentManager:
    """Executes delegated prompts in background asyncio tasks."""

    def __init__(
        self,
        *,
        state_path: str | Path | None = None,
        max_concurrent_runs: int = 2,
        max_queued_runs: int = 32,
        per_session_quota: int = 4,
    ) -> None:
        if max_concurrent_runs < 1:
            raise ValueError("max_concurrent_runs must be >= 1")
        if max_queued_runs < 0:
            raise ValueError("max_queued_runs must be >= 0")
        if per_session_quota < 1:
            raise ValueError("per_session_quota must be >= 1")

        base = Path(state_path) if state_path else (Path.home() / ".clawlite" / "state" / "subagents")
        self._state_file = (base / "runs.json") if base.suffix == "" else base
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self.max_concurrent_runs = int(max_concurrent_runs)
        self.max_queued_runs = int(max_queued_runs)
        self.per_session_quota = int(per_session_quota)
        self._runs: dict[str, SubagentRun] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._queue: deque[str] = deque()
        self._pending_runners: dict[str, Runner] = {}
        self._lock = asyncio.Lock()
        self._load_state()

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

        now_iso = _utc_now()
        for row in runs_raw:
            if not isinstance(row, dict):
                continue
            run = self._from_payload(row)
            if run is None:
                continue
            if run.status in {"running", "queued"}:
                run.status = "interrupted"
                run.finished_at = run.finished_at or now_iso
                run.updated_at = now_iso
                run.metadata["resumable"] = True
                run.metadata["last_status_reason"] = "manager_restart"
                run.metadata["last_status_at"] = now_iso
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
                    now_iso = _utc_now()
                    active.status = status
                    active.result = result
                    active.error = error
                    active.finished_at = now_iso
                    active.updated_at = now_iso
                    active.metadata["resumable"] = status in {"error", "cancelled", "interrupted"}
                    active.metadata["last_status_reason"] = status
                    active.metadata["last_status_at"] = now_iso
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
        clean_run_id = str(run_id or "").strip()
        if not clean_run_id:
            raise ValueError("run_id is required")

        async with self._lock:
            run = self._runs.get(clean_run_id)
            if run is None:
                raise KeyError(clean_run_id)
            resumable = bool(run.metadata.get("resumable"))
            if run.status in {"done", "running"} and not resumable:
                raise ValueError(f"run '{clean_run_id}' is not resumable")
            self._ensure_limits(run.session_id)

            attempts = int(run.metadata.get("resume_attempts", 0)) + 1
            run.metadata["resume_attempts"] = attempts

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

    async def spawn(self, *, session_id: str, task: str, runner: Runner) -> SubagentRun:
        clean_session_id = str(session_id or "").strip()
        clean_task = str(task or "").strip()
        if not clean_session_id:
            raise ValueError("session_id is required")
        if not clean_task:
            raise ValueError("task is required")

        async with self._lock:
            self._ensure_limits(clean_session_id)
            run_id = uuid.uuid4().hex
            now_iso = _utc_now()
            run = SubagentRun(
                run_id=run_id,
                session_id=clean_session_id,
                task=clean_task,
                status="queued",
                started_at=now_iso,
                queued_at=now_iso,
                updated_at=now_iso,
                metadata={
                    "run_version": 1,
                    "resume_attempts": 0,
                    "resume_token": uuid.uuid4().hex,
                    "resumable": False,
                    "last_status_reason": "spawned",
                    "last_status_at": now_iso,
                },
            )
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

    def list_completed_unsynthesized(self, session_id: str, limit: int = 8) -> list[SubagentRun]:
        clean_session_id = str(session_id or "").strip()
        if not clean_session_id:
            return []
        max_items = max(1, int(limit))
        completed_statuses = {"done", "error", "cancelled", "interrupted"}

        rows = [
            run
            for run in self._runs.values()
            if run.session_id == clean_session_id
            and run.status in completed_statuses
            and not bool(run.metadata.get("synthesized", False))
        ]
        rows.sort(key=lambda item: (item.finished_at or "", item.run_id))
        return rows[:max_items]

    def mark_synthesized(self, run_ids: list[str], *, digest_id: str = "") -> int:
        now_iso = _utc_now()
        clean_digest = str(digest_id or "").strip()
        count = 0
        seen: set[str] = set()
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
            count += 1

        if count > 0:
            self._save_state()
        return count

    def cancel(self, run_id: str) -> bool:
        clean_run_id = str(run_id or "").strip()
        task = self._tasks.get(clean_run_id)
        if task is not None and not task.done():
            task.cancel()
            return True

        if clean_run_id in self._queue:
            self._queue = deque(item for item in self._queue if item != clean_run_id)
            run = self._runs.get(clean_run_id)
            if run is not None:
                now_iso = _utc_now()
                run.status = "cancelled"
                run.finished_at = now_iso
                run.updated_at = now_iso
                run.metadata["resumable"] = True
                run.metadata["last_status_reason"] = "cancelled_while_queued"
                run.metadata["last_status_at"] = now_iso
            self._pending_runners.pop(clean_run_id, None)
            self._save_state()
            return True
        return False

    def cancel_session(self, session_id: str) -> int:
        total = 0
        for run in self.list_runs(session_id=session_id, active_only=True):
            if self.cancel(run.run_id):
                total += 1
        return total
