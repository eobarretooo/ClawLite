from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
import threading
import time
import uuid
from typing import Callable

NotifierFn = Callable[[str, str], None]


@dataclass
class SubagentRun:
    run_id: str
    session_id: str
    label: str
    task: str
    status: str
    created_at: float
    started_at: float | None = None
    ended_at: float | None = None
    result_preview: str = ""
    error: str = ""


class SubagentRuntime:
    """Runtime de subagentes em background para delegacao de tarefas."""

    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max(1, int(max_workers)), thread_name_prefix="clawlite-subagent")
        self._lock = threading.RLock()
        self._runs: dict[str, SubagentRun] = {}
        self._futures: dict[str, Future[str]] = {}
        self._session_index: dict[str, set[str]] = {}
        self._notifier: NotifierFn | None = None

    def set_notifier(self, notifier: NotifierFn | None) -> None:
        with self._lock:
            self._notifier = notifier

    @staticmethod
    def _execute_subagent(session_id: str, run_id: str, task: str) -> str:
        from clawlite.core.agent import run_task_with_learning

        return run_task_with_learning(
            task,
            skill="subagent",
            session_id=f"{session_id}:subagent:{run_id}",
        )

    def spawn(self, *, session_id: str, task: str, label: str = "") -> dict[str, str]:
        text = str(task or "").strip()
        if not text:
            raise ValueError("task do subagente é obrigatória")

        sid = str(session_id or "").strip() or "default"
        rid = uuid.uuid4().hex[:8]
        row = SubagentRun(
            run_id=rid,
            session_id=sid,
            label=(str(label or "").strip() or text[:48]),
            task=text,
            status="queued",
            created_at=time.time(),
        )
        with self._lock:
            self._runs[rid] = row
            self._session_index.setdefault(sid, set()).add(rid)

            future = self._executor.submit(self._execute_subagent, sid, rid, text)
            self._futures[rid] = future
            row.status = "running"
            row.started_at = time.time()
            future.add_done_callback(lambda fut, run_id=rid: self._on_done(run_id, fut))

        return {"run_id": rid, "status": row.status, "label": row.label}

    def _on_done(self, run_id: str, future: Future[str]) -> None:
        callback: NotifierFn | None = None
        session_id = ""
        notify_text = ""
        with self._lock:
            row = self._runs.get(run_id)
            if row is None:
                self._futures.pop(run_id, None)
                return
            row.ended_at = time.time()
            self._futures.pop(run_id, None)

            if future.cancelled():
                row.status = "cancelled"
                row.result_preview = ""
                row.error = "cancelled"
            else:
                try:
                    output = str(future.result() or "").strip()
                    row.status = "done"
                    row.result_preview = output[:600]
                    row.error = ""
                    notify_text = (
                        f"[subagent:{row.run_id}] {row.label}\n"
                        f"Resultado:\n{output[:3500] or '(sem saída)'}"
                    )
                except Exception as exc:
                    row.status = "failed"
                    row.error = str(exc)
                    row.result_preview = ""
                    notify_text = f"[subagent:{row.run_id}] {row.label}\nFalha: {row.error}"

            callback = self._notifier
            session_id = row.session_id

        if callback and notify_text:
            try:
                callback(session_id, notify_text)
            except Exception:
                pass

    def list_runs(self, *, session_id: str | None = None, only_active: bool = False) -> list[dict[str, object]]:
        sid = str(session_id or "").strip()
        with self._lock:
            rows = list(self._runs.values())
        if sid:
            rows = [r for r in rows if r.session_id == sid]
        if only_active:
            rows = [r for r in rows if r.status in {"queued", "running"}]
        rows.sort(key=lambda r: r.created_at, reverse=True)
        return [asdict(r) for r in rows]

    def cancel_run(self, run_id: str) -> bool:
        rid = str(run_id or "").strip()
        if not rid:
            return False
        with self._lock:
            fut = self._futures.get(rid)
            row = self._runs.get(rid)
        if fut is None or row is None:
            return False
        cancelled = fut.cancel()
        if cancelled:
            with self._lock:
                row.status = "cancelled"
                row.ended_at = time.time()
                row.error = "cancelled"
                self._futures.pop(rid, None)
        return cancelled

    def cancel_session(self, session_id: str) -> int:
        sid = str(session_id or "").strip()
        if not sid:
            return 0
        with self._lock:
            run_ids = list(self._session_index.get(sid, set()))
        cancelled = 0
        for rid in run_ids:
            if self.cancel_run(rid):
                cancelled += 1
        return cancelled

    def running_count(self) -> int:
        with self._lock:
            return sum(1 for row in self._runs.values() if row.status in {"queued", "running"})

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


_RUNTIME: SubagentRuntime | None = None
_RUNTIME_LOCK = threading.Lock()


def get_subagent_runtime() -> SubagentRuntime:
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is None:
            _RUNTIME = SubagentRuntime()
        return _RUNTIME


def set_subagent_notifier(notifier: NotifierFn | None) -> None:
    runtime = get_subagent_runtime()
    runtime.set_notifier(notifier)


def reset_subagent_runtime_for_tests() -> None:
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is not None:
            _RUNTIME.shutdown()
        _RUNTIME = None
