"""Async job queue for one-off background tasks."""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Literal


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


JobStatus = Literal["queued", "running", "done", "failed", "cancelled"]
WorkerFn = Callable[["Job"], Awaitable[str]]


@dataclass
class Job:
    id: str
    kind: str
    payload: dict[str, Any]
    priority: int
    session_id: str
    status: JobStatus = "queued"
    result: str = ""
    error: str = ""
    created_at: str = field(default_factory=_utc_now)
    started_at: str = ""
    finished_at: str = ""
    max_retries: int = 0
    retry_count: int = 0
    cancellation_requested: bool = False


class JobQueue:
    """Priority async job queue with status tracking, cancellation, and optional retry."""

    def __init__(self, *, concurrency: int = 2) -> None:
        self._concurrency = max(1, int(concurrency))
        self._jobs: dict[str, Job] = {}
        # heap: (-priority, created_at, job_id)
        self._pending: list[tuple[int, str, str]] = []
        self._workers: list[asyncio.Task] = []
        self._worker_fn: WorkerFn | None = None
        self._custom: dict[str, WorkerFn] = {}
        self._running = False
        self._sem: asyncio.Semaphore | None = None
        self._new_job: asyncio.Event | None = None
        self._journal: Any = None  # optional JobJournal

    def set_journal(self, journal: Any) -> None:
        self._journal = journal

    def register_custom(self, handler: str, fn: WorkerFn) -> None:
        self._custom[handler] = fn

    def submit(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        priority: int = 5,
        session_id: str = "",
        max_retries: int = 0,
    ) -> Job:
        job = Job(
            id=uuid.uuid4().hex,
            kind=str(kind),
            payload=dict(payload),
            priority=max(0, min(10, int(priority))),
            session_id=str(session_id),
            max_retries=max(0, int(max_retries)),
        )
        self._jobs[job.id] = job
        import heapq
        heapq.heappush(self._pending, (-job.priority, job.created_at, job.id))
        if self._journal:
            try:
                self._journal.save(job)
            except Exception:
                pass
        if self._new_job is not None:
            self._new_job.set()
        return job

    def status(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        if job.status == "queued":
            job.status = "cancelled"
            job.finished_at = _utc_now()
            if self._journal:
                try:
                    self._journal.save(job)
                except Exception:
                    pass
            return True
        if job.status == "running":
            job.cancellation_requested = True
            return True
        return False

    def list_jobs(
        self,
        *,
        session_id: str | None = None,
        status: str | None = None,
    ) -> list[Job]:
        jobs = list(self._jobs.values())
        if session_id is not None:
            jobs = [j for j in jobs if j.session_id == session_id]
        if status is not None:
            jobs = [j for j in jobs if j.status == status]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    def start(self, worker_fn: WorkerFn) -> None:
        self._worker_fn = worker_fn
        self._running = True
        self._sem = asyncio.Semaphore(self._concurrency)
        self._new_job = asyncio.Event()
        # Signal immediately if jobs were submitted before start()
        if self._pending:
            self._new_job.set()
        for _ in range(self._concurrency):
            task = asyncio.ensure_future(self._worker_loop())
            self._workers.append(task)

    async def stop(self) -> None:
        self._running = False
        if self._new_job:
            self._new_job.set()
        for task in self._workers:
            task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def _worker_loop(self) -> None:
        while self._running:
            job = self._pop_pending()
            if job is None:
                # No work available — wait for a signal
                if self._new_job is not None:
                    await self._new_job.wait()
                    self._new_job.clear()
                else:
                    await asyncio.sleep(0.05)
                continue
            async with self._sem:
                await self._run_job(job)

    def _pop_pending(self) -> Job | None:
        import heapq
        while self._pending:
            _, _, job_id = heapq.heappop(self._pending)
            job = self._jobs.get(job_id)
            if job is None or job.status != "queued":
                continue
            return job
        return None

    async def _run_job(self, job: Job) -> None:
        job.status = "running"
        job.started_at = _utc_now()
        if self._journal:
            try:
                self._journal.save(job)
            except Exception:
                pass
        try:
            fn = self._resolve_worker(job)
            result = await fn(job)
            job.status = "done"
            job.result = str(result)
        except Exception as exc:
            if job.retry_count < job.max_retries:
                job.retry_count += 1
                job.status = "queued"
                job.started_at = ""
                import heapq
                heapq.heappush(self._pending, (-job.priority, job.created_at, job.id))
                if self._new_job:
                    self._new_job.set()
            else:
                job.status = "failed"
                job.error = str(exc)
        job.finished_at = _utc_now() if job.status in ("done", "failed", "cancelled") else ""
        if self._journal:
            try:
                self._journal.save(job)
            except Exception:
                pass

    def _resolve_worker(self, job: Job) -> WorkerFn:
        if job.kind == "custom":
            handler = job.payload.get("handler", "")
            fn = self._custom.get(str(handler))
            if fn is None:
                raise ValueError(f"no custom handler registered: {handler}")
            return fn
        if self._worker_fn is None:
            raise RuntimeError("no worker_fn set — call start() first")
        return self._worker_fn

    def worker_status(self) -> dict:
        """Return live health of the worker pool for supervisor monitoring."""
        alive = sum(1 for t in self._workers if not t.done() and not t.cancelled())
        pending_count = len([j for j in self._jobs.values() if j.status == "queued"])
        running_count = len([j for j in self._jobs.values() if j.status == "running"])
        return {
            "running": self._running and alive > 0,
            "concurrency": self._concurrency,
            "workers_alive": alive,
            "workers_total": len(self._workers),
            "pending_jobs": pending_count,
            "running_jobs": running_count,
        }

    def restore_from_journal(self) -> int:
        """Reload queued jobs from journal. Returns count restored."""
        if self._journal is None:
            return 0
        import heapq
        count = 0
        for job in self._journal.load_queued():
            self._jobs[job.id] = job
            heapq.heappush(self._pending, (-job.priority, job.created_at, job.id))
            count += 1
        return count
