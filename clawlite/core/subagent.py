from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
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


Runner = Callable[[str, str], Awaitable[str]]


class SubagentManager:
    """Executes delegated prompts in background asyncio tasks."""

    def __init__(self) -> None:
        self._runs: dict[str, SubagentRun] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def spawn(self, *, session_id: str, task: str, runner: Runner) -> SubagentRun:
        run_id = uuid.uuid4().hex
        run = SubagentRun(run_id=run_id, session_id=session_id, task=task)
        self._runs[run_id] = run

        async def _worker() -> None:
            try:
                result = await runner(session_id, task)
                run.result = str(result)
                run.status = "done"
            except asyncio.CancelledError:
                run.status = "cancelled"
                raise
            except Exception as exc:  # pragma: no cover
                run.status = "error"
                run.error = str(exc)
            finally:
                run.finished_at = datetime.now(timezone.utc).isoformat()

        self._tasks[run_id] = asyncio.create_task(_worker())
        return run

    def list_runs(self, *, session_id: str | None = None, active_only: bool = False) -> list[SubagentRun]:
        values = list(self._runs.values())
        if session_id:
            values = [item for item in values if item.session_id == session_id]
        if active_only:
            values = [item for item in values if item.status == "running"]
        return sorted(values, key=lambda item: item.started_at, reverse=True)

    def cancel(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def cancel_session(self, session_id: str) -> int:
        total = 0
        for run in self.list_runs(session_id=session_id, active_only=True):
            if self.cancel(run.run_id):
                total += 1
        return total
