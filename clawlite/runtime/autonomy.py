from __future__ import annotations

import asyncio
import heapq
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from clawlite.utils.logging import bind_event, setup_logging

SnapshotCallback = Callable[[], Awaitable[dict[str, Any]] | dict[str, Any]]
RunCallback = Callable[[dict[str, Any]], Awaitable[Any]]
NowMonotonic = Callable[[], float]
WakeCallback = Callable[[str, dict[str, Any]], Awaitable[Any]]


@dataclass(order=True, slots=True)
class _WakeQueueEntry:
    priority: int
    sequence: int
    kind: str = field(compare=False)
    key: str = field(compare=False)
    payload: dict[str, Any] = field(compare=False)
    future: asyncio.Future[Any] = field(compare=False)


class AutonomyWakeCoordinator:
    def __init__(self, *, max_pending: int = 200) -> None:
        self.max_pending = max(1, int(max_pending or 200))
        self._running = False
        self._on_wake: WakeCallback | None = None
        self._task: asyncio.Task[Any] | None = None
        self._queue: list[_WakeQueueEntry] = []
        self._pending_by_key: dict[str, asyncio.Future[Any]] = {}
        self._sequence = 0
        self._lock = asyncio.Lock()
        self._has_items = asyncio.Condition(self._lock)

        self._enqueued = 0
        self._coalesced = 0
        self._dropped_backpressure = 0
        self._executed_ok = 0
        self._executed_error = 0
        self._inflight = 0
        self._max_queue_depth_seen = 0
        self._by_kind: dict[str, dict[str, int]] = {}

    def _task_snapshot(self) -> tuple[str, str]:
        task = self._task
        if task is None:
            return ("stopped", "")
        if task.cancelled():
            return ("cancelled", "")
        if not task.done():
            return ("running", "")
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return ("cancelled", "")
        if exc is not None:
            return ("failed", str(exc))
        return ("done", "")

    def _track_kind(self, kind: str, metric: str) -> None:
        row = self._by_kind.setdefault(
            kind,
            {
                "enqueued": 0,
                "coalesced": 0,
                "dropped_backpressure": 0,
                "executed_ok": 0,
                "executed_error": 0,
            },
        )
        row[metric] = int(row.get(metric, 0) or 0) + 1

    async def _worker_loop(self) -> None:
        while True:
            async with self._has_items:
                while self._running and not self._queue:
                    await self._has_items.wait()
                if not self._running and not self._queue:
                    break
                entry = heapq.heappop(self._queue)
                self._inflight += 1

            callback = self._on_wake
            try:
                if callback is None:
                    raise RuntimeError("autonomy_wake_callback_missing")
                result = await callback(entry.kind, dict(entry.payload))
            except asyncio.CancelledError:
                if not entry.future.done():
                    entry.future.set_exception(RuntimeError("autonomy_wake_stopped"))
                raise
            except Exception as exc:
                async with self._lock:
                    self._executed_error += 1
                    self._track_kind(entry.kind, "executed_error")
                if not entry.future.done():
                    entry.future.set_exception(exc)
            else:
                async with self._lock:
                    self._executed_ok += 1
                    self._track_kind(entry.kind, "executed_ok")
                if not entry.future.done():
                    entry.future.set_result(result)
            finally:
                async with self._lock:
                    self._inflight = max(0, self._inflight - 1)
                    pending = self._pending_by_key.get(entry.key)
                    if pending is entry.future:
                        self._pending_by_key.pop(entry.key, None)

    async def start(self, on_wake: WakeCallback) -> None:
        async with self._lock:
            self._on_wake = on_wake
            if self._task is not None:
                task_state, _task_error = self._task_snapshot()
                if task_state in {"failed", "cancelled", "done"}:
                    self._task = None
                else:
                    self._running = True
                    return
            self._running = True
            self._task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        async with self._has_items:
            self._running = False
            self._has_items.notify_all()
            task = self._task

        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        async with self._lock:
            self._task = None
            self._on_wake = None
            self._queue.clear()
            self._inflight = 0
            for future in self._pending_by_key.values():
                if not future.done():
                    future.set_exception(RuntimeError("autonomy_wake_stopped"))
            self._pending_by_key.clear()

    async def submit(
        self,
        kind: str,
        key: str,
        priority: int,
        payload: dict[str, Any] | None = None,
        fallback_result: Any = None,
    ) -> Any:
        normalized_kind = str(kind or "unknown").strip() or "unknown"
        normalized_key = str(key or normalized_kind).strip() or normalized_kind
        normalized_payload = dict(payload or {})

        async with self._has_items:
            if not self._running or self._task is None or self._on_wake is None:
                return fallback_result

            existing = self._pending_by_key.get(normalized_key)
            if existing is not None and not existing.done():
                self._coalesced += 1
                self._track_kind(normalized_kind, "coalesced")
                future = existing
            else:
                if len(self._pending_by_key) >= self.max_pending:
                    self._dropped_backpressure += 1
                    self._track_kind(normalized_kind, "dropped_backpressure")
                    return fallback_result

                loop = asyncio.get_running_loop()
                future = loop.create_future()
                entry = _WakeQueueEntry(
                    priority=int(priority),
                    sequence=self._sequence,
                    kind=normalized_kind,
                    key=normalized_key,
                    payload=normalized_payload,
                    future=future,
                )
                self._sequence += 1
                heapq.heappush(self._queue, entry)
                self._pending_by_key[normalized_key] = future
                self._enqueued += 1
                self._track_kind(normalized_kind, "enqueued")
                depth = len(self._queue)
                if depth > self._max_queue_depth_seen:
                    self._max_queue_depth_seen = depth
                self._has_items.notify()

        try:
            return await future
        except RuntimeError as exc:
            if str(exc) == "autonomy_wake_stopped":
                return fallback_result
            raise

    def status(self) -> dict[str, Any]:
        task_state, task_error = self._task_snapshot()
        return {
            "running": bool(self._running and task_state == "running"),
            "worker_state": task_state,
            "max_pending": self.max_pending,
            "enqueued": self._enqueued,
            "coalesced": self._coalesced,
            "dropped_backpressure": self._dropped_backpressure,
            "executed_ok": self._executed_ok,
            "executed_error": self._executed_error,
            "queue_depth": len(self._queue),
            "inflight": self._inflight,
            "max_queue_depth_seen": self._max_queue_depth_seen,
            "last_error": task_error,
            "by_kind": {kind: dict(metrics) for kind, metrics in self._by_kind.items()},
        }


class AutonomyService:
    def __init__(
        self,
        *,
        enabled: bool = False,
        interval_s: float = 900,
        cooldown_s: float = 300,
        timeout_s: float = 45.0,
        max_queue_backlog: int = 200,
        session_id: str = "autonomy:system",
        snapshot_callback: SnapshotCallback | None = None,
        run_callback: RunCallback | None = None,
        now_monotonic: NowMonotonic | None = None,
    ) -> None:
        setup_logging()
        self.enabled = bool(enabled)
        self.interval_s = max(1.0, float(interval_s))
        self.cooldown_s = max(0.0, float(cooldown_s))
        self.timeout_s = max(0.1, float(timeout_s))
        self.max_queue_backlog = max(0, int(max_queue_backlog))
        self.session_id = str(session_id or "autonomy:system").strip() or "autonomy:system"
        self._snapshot_callback = snapshot_callback
        self._run_callback = run_callback
        self._now_monotonic = now_monotonic or time.monotonic

        self._task: asyncio.Task[Any] | None = None
        self._running = False
        self._cooldown_until = 0.0

        self._ticks = 0
        self._run_attempts = 0
        self._run_success = 0
        self._run_failures = 0
        self._skipped_backlog = 0
        self._skipped_cooldown = 0
        self._skipped_disabled = 0
        self._last_run_at = ""
        self._last_result_excerpt = ""
        self._last_error = ""
        self._consecutive_error_count = 0
        self._last_snapshot: dict[str, Any] = {}

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _excerpt(value: Any, *, max_chars: int = 280) -> str:
        text = str(value or "").strip()
        if len(text) <= max_chars:
            return text
        return f"{text[: max_chars - 3]}..."

    @staticmethod
    def _trim_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
        queue_raw = snapshot.get("queue")
        supervisor_raw = snapshot.get("supervisor")
        channels_raw = snapshot.get("channels")

        queue = queue_raw if isinstance(queue_raw, dict) else {}
        supervisor = supervisor_raw if isinstance(supervisor_raw, dict) else {}
        channels = channels_raw if isinstance(channels_raw, dict) else {}

        queue_trimmed = {
            "outbound_size": int(queue.get("outbound_size", 0) or 0),
            "dead_letter_size": int(queue.get("dead_letter_size", 0) or 0),
            "outbound_oldest_age_s": float(queue.get("outbound_oldest_age_s", 0.0) or 0.0),
            "dead_letter_oldest_age_s": float(queue.get("dead_letter_oldest_age_s", 0.0) or 0.0),
        }

        supervisor_trimmed = {
            "running": bool(supervisor.get("running", False)),
            "incident_count": int(supervisor.get("incident_count", 0) or 0),
            "consecutive_error_count": int(supervisor.get("consecutive_error_count", 0) or 0),
        }

        channels_trimmed = {
            "enabled_count": int(channels.get("enabled_count", 0) or 0),
            "running_count": int(channels.get("running_count", 0) or 0),
        }

        return {
            "queue": queue_trimmed,
            "supervisor": supervisor_trimmed,
            "channels": channels_trimmed,
        }

    async def _read_snapshot(self) -> dict[str, Any]:
        if self._snapshot_callback is None:
            trimmed = self._trim_snapshot({})
            self._last_snapshot = trimmed
            return trimmed
        raw = self._snapshot_callback()
        if asyncio.iscoroutine(raw):
            raw = await raw
        snapshot = raw if isinstance(raw, dict) else {}
        trimmed = self._trim_snapshot(snapshot)
        self._last_snapshot = trimmed
        return trimmed

    async def run_once(self, force: bool = False) -> dict[str, Any]:
        self._ticks += 1
        try:
            now = self._now_monotonic()
            snapshot = await self._read_snapshot()
            queue = snapshot.get("queue", {}) if isinstance(snapshot.get("queue"), dict) else {}
            backlog = int(queue.get("outbound_size", 0) or 0) + int(queue.get("dead_letter_size", 0) or 0)

            if not force and not self.enabled:
                self._skipped_disabled += 1
                return self.status()
            if not force and backlog > self.max_queue_backlog:
                self._skipped_backlog += 1
                return self.status()
            if not force and now < self._cooldown_until:
                self._skipped_cooldown += 1
                return self.status()

            if self._run_callback is None:
                self._run_failures += 1
                self._consecutive_error_count += 1
                self._last_error = "autonomy_callback_unavailable"
                self._cooldown_until = now + self.cooldown_s
                return self.status()

            self._run_attempts += 1
            self._last_run_at = self._utc_now_iso()
            self._cooldown_until = now + self.cooldown_s
            result = await asyncio.wait_for(self._run_callback(snapshot), timeout=self.timeout_s)
            self._run_success += 1
            self._last_result_excerpt = self._excerpt(result)
            self._last_error = ""
            self._consecutive_error_count = 0
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._run_failures += 1
            self._consecutive_error_count += 1
            self._last_error = str(exc)
            bind_event("autonomy.tick", session=self.session_id).error("autonomy run failed error={}", exc)
        return self.status()

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self.run_once(force=False)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._run_failures += 1
                self._consecutive_error_count += 1
                self._last_error = str(exc)
                bind_event("autonomy.tick", session=self.session_id).error("autonomy loop tick failed error={}", exc)
            if not self._running:
                break
            await asyncio.sleep(self.interval_s)

    async def start(self) -> None:
        if self._task is not None:
            if self._task.done() or self._task.cancelled():
                self._task = None
            else:
                return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        bind_event("autonomy.lifecycle").info(
            "autonomy started enabled={} interval_s={} cooldown_s={} timeout_s={} max_queue_backlog={} session_id={}",
            self.enabled,
            self.interval_s,
            self.cooldown_s,
            self.timeout_s,
            self.max_queue_backlog,
            self.session_id,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self._last_error = str(exc)
        self._task = None
        bind_event("autonomy.lifecycle").info("autonomy stopped")

    def status(self) -> dict[str, Any]:
        cooldown_remaining_s = max(0.0, self._cooldown_until - self._now_monotonic())
        return {
            "running": bool(self._running and self._task is not None),
            "enabled": bool(self.enabled),
            "session_id": self.session_id,
            "interval_s": self.interval_s,
            "cooldown_s": self.cooldown_s,
            "timeout_s": self.timeout_s,
            "max_queue_backlog": self.max_queue_backlog,
            "ticks": self._ticks,
            "run_attempts": self._run_attempts,
            "run_success": self._run_success,
            "run_failures": self._run_failures,
            "skipped_backlog": self._skipped_backlog,
            "skipped_cooldown": self._skipped_cooldown,
            "skipped_disabled": self._skipped_disabled,
            "last_run_at": self._last_run_at,
            "last_result_excerpt": self._last_result_excerpt,
            "last_error": self._last_error,
            "consecutive_error_count": self._consecutive_error_count,
            "last_snapshot": dict(self._last_snapshot),
            "cooldown_remaining_s": round(cooldown_remaining_s, 3),
        }
