from __future__ import annotations

import asyncio
import heapq
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
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
    queued: bool = field(default=True, compare=False)


@dataclass(frozen=True, slots=True)
class _WakeKindPolicy:
    quota: int
    coalesce_mode: str


class AutonomyWakeCoordinator:
    def __init__(self, *, max_pending: int = 200, journal_path: str | Path | None = None) -> None:
        self.max_pending = max(1, int(max_pending or 200))
        self.journal_path = Path(journal_path).expanduser() if journal_path is not None else None
        if self.journal_path is not None:
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        self._running = False
        self._on_wake: WakeCallback | None = None
        self._task: asyncio.Task[Any] | None = None
        self._queue: list[_WakeQueueEntry] = []
        self._pending_by_key: dict[str, asyncio.Future[Any]] = {}
        self._pending_entries_by_key: dict[str, _WakeQueueEntry] = {}
        self._sequence = 0
        self._lock = asyncio.Lock()
        self._has_items = asyncio.Condition(self._lock)

        self._enqueued = 0
        self._coalesced = 0
        self._dropped_backpressure = 0
        self._dropped_quota = 0
        self._dropped_global_backpressure = 0
        self._executed_ok = 0
        self._executed_error = 0
        self._coalesced_priority_upgrades = 0
        self._coalesced_payload_updates = 0
        self._inflight = 0
        self._max_queue_depth_seen = 0
        self._restored = 0
        self._journal_load_failures = 0
        self._journal_save_failures = 0
        self._last_journal_error = ""
        self._by_kind: dict[str, dict[str, int]] = {}
        self._kind_policies = self._build_kind_policies()

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
                "coalesced_priority_upgrades": 0,
                "coalesced_payload_updates": 0,
                "dropped_backpressure": 0,
                "dropped_quota": 0,
                "dropped_global_backpressure": 0,
                "executed_ok": 0,
                "executed_error": 0,
            },
        )
        row[metric] = int(row.get(metric, 0) or 0) + 1

    def _build_kind_policies(self) -> dict[str, _WakeKindPolicy]:
        if self.max_pending <= 1:
            quota = 1
            return {
                "heartbeat": _WakeKindPolicy(quota=quota, coalesce_mode="replace_latest"),
                "proactive": _WakeKindPolicy(quota=quota, coalesce_mode="replace_latest"),
                "cron": _WakeKindPolicy(quota=quota, coalesce_mode="merge"),
                "default": _WakeKindPolicy(quota=quota, coalesce_mode="merge"),
            }

        heartbeat_quota = 1
        proactive_quota = 1 if self.max_pending >= 3 else 1
        cron_quota = max(1, self.max_pending - heartbeat_quota - proactive_quota)
        default_quota = max(1, self.max_pending - heartbeat_quota)
        return {
            "heartbeat": _WakeKindPolicy(quota=heartbeat_quota, coalesce_mode="replace_latest"),
            "proactive": _WakeKindPolicy(quota=proactive_quota, coalesce_mode="replace_latest"),
            "cron": _WakeKindPolicy(quota=cron_quota, coalesce_mode="merge"),
            "default": _WakeKindPolicy(quota=default_quota, coalesce_mode="merge"),
        }

    def _policy_for_kind(self, kind: str) -> _WakeKindPolicy:
        return self._kind_policies.get(kind, self._kind_policies["default"])

    def _pending_count_for_kind(self, kind: str) -> int:
        count = 0
        for entry in self._pending_entries_by_key.values():
            if entry.kind == kind:
                count += 1
        return count

    def _merge_payload_for_policy(
        self,
        *,
        current: dict[str, Any],
        incoming: dict[str, Any],
        policy: _WakeKindPolicy,
    ) -> dict[str, Any]:
        if not incoming:
            return dict(current)
        if policy.coalesce_mode == "replace_latest":
            return dict(incoming)
        merged = dict(current)
        merged.update(incoming)
        return merged

    def _kind_limits_status(self) -> dict[str, int]:
        return {kind: int(policy.quota) for kind, policy in self._kind_policies.items()}

    def _kind_policy_status(self) -> dict[str, dict[str, Any]]:
        return {
            kind: {
                "quota": int(policy.quota),
                "coalesce_mode": str(policy.coalesce_mode),
            }
            for kind, policy in self._kind_policies.items()
        }

    def _pending_by_kind_status(self) -> dict[str, int]:
        rows: dict[str, int] = {}
        for entry in self._pending_entries_by_key.values():
            rows[entry.kind] = int(rows.get(entry.kind, 0) or 0) + 1
        return rows

    @staticmethod
    def _consume_background_future(future: asyncio.Future[Any]) -> None:
        try:
            future.result()
        except asyncio.CancelledError:
            return
        except Exception:
            return

    def _journal_rows_locked(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for entry in sorted(self._pending_entries_by_key.values(), key=lambda item: (item.priority, item.sequence)):
            rows.append(
                {
                    "kind": entry.kind,
                    "key": entry.key,
                    "priority": int(entry.priority),
                    "sequence": int(entry.sequence),
                    "payload": dict(entry.payload),
                }
            )
        return rows

    def _write_journal_rows(self, rows: list[dict[str, Any]]) -> None:
        if self.journal_path is None:
            return
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            try:
                self.journal_path.unlink(missing_ok=True)
            except OSError:
                pass
            return
        payload = json.dumps(rows, ensure_ascii=False, indent=2)
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(self.journal_path.parent),
                prefix=f".{self.journal_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                tmp_path = Path(handle.name)
            os.replace(str(tmp_path), str(self.journal_path))
        finally:
            if tmp_path is not None and tmp_path.exists():
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    async def _persist_journal_locked(self) -> None:
        if self.journal_path is None:
            return
        rows = self._journal_rows_locked()
        try:
            await asyncio.to_thread(self._write_journal_rows, rows)
        except Exception as exc:
            self._journal_save_failures += 1
            self._last_journal_error = str(exc)
            bind_event("autonomy.wake").warning("wake journal save failed path={} error={}", self.journal_path, exc)
        else:
            self._last_journal_error = ""

    def _read_journal_rows(self) -> list[dict[str, Any]]:
        if self.journal_path is None or not self.journal_path.exists():
            return []
        raw = json.loads(self.journal_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("invalid_autonomy_wake_journal")
        rows: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                rows.append(item)
        return rows

    async def _restore_journal_locked(self) -> None:
        if self.journal_path is None or self._pending_entries_by_key:
            return
        try:
            rows = await asyncio.to_thread(self._read_journal_rows)
        except Exception as exc:
            self._journal_load_failures += 1
            self._last_journal_error = str(exc)
            bind_event("autonomy.wake").warning("wake journal load failed path={} error={}", self.journal_path, exc)
            return
        if not rows:
            self._last_journal_error = ""
            return
        loop = asyncio.get_running_loop()
        restored = 0
        for row in rows:
            kind = str(row.get("kind", "") or "unknown").strip() or "unknown"
            key = str(row.get("key", "") or kind).strip() or kind
            if key in self._pending_entries_by_key:
                continue
            priority = int(row.get("priority", 100) or 100)
            payload = row.get("payload", {})
            normalized_payload = dict(payload) if isinstance(payload, dict) else {}
            future: asyncio.Future[Any] = loop.create_future()
            future.add_done_callback(self._consume_background_future)
            entry = _WakeQueueEntry(
                priority=priority,
                sequence=max(self._sequence, int(row.get("sequence", self._sequence) or self._sequence)),
                kind=kind,
                key=key,
                payload=normalized_payload,
                future=future,
            )
            self._sequence = entry.sequence + 1
            heapq.heappush(self._queue, entry)
            self._pending_by_key[key] = future
            self._pending_entries_by_key[key] = entry
            depth = len(self._queue)
            if depth > self._max_queue_depth_seen:
                self._max_queue_depth_seen = depth
            restored += 1
            self._track_kind(kind, "enqueued")
        self._restored += restored
        self._enqueued += restored
        self._last_journal_error = ""
        if restored:
            self._has_items.notify_all()

    async def _worker_loop(self) -> None:
        while True:
            async with self._has_items:
                while self._running and not self._queue:
                    await self._has_items.wait()
                if not self._running and not self._queue:
                    break
                entry = heapq.heappop(self._queue)
                entry.queued = False
                self._inflight += 1

            callback = self._on_wake
            preserve_pending = False
            try:
                if callback is None:
                    raise RuntimeError("autonomy_wake_callback_missing")
                result = await callback(entry.kind, dict(entry.payload))
            except asyncio.CancelledError:
                preserve_pending = True
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
                    if not preserve_pending:
                        pending = self._pending_by_key.get(entry.key)
                        if pending is entry.future:
                            self._pending_by_key.pop(entry.key, None)
                            self._pending_entries_by_key.pop(entry.key, None)
                            await self._persist_journal_locked()

    async def start(self, on_wake: WakeCallback) -> None:
        async with self._has_items:
            self._on_wake = on_wake
            if self._task is not None:
                task_state, _task_error = self._task_snapshot()
                if task_state in {"failed", "cancelled", "done"}:
                    self._task = None
                else:
                    self._running = True
                    return
            self._running = True
            await self._restore_journal_locked()
            self._task = asyncio.create_task(self._worker_loop())
            if self._queue:
                self._has_items.notify_all()

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
            self._pending_entries_by_key.clear()

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
                entry = self._pending_entries_by_key.get(normalized_key)
                tracked_kind = normalized_kind
                changed = False
                if entry is not None:
                    tracked_kind = entry.kind
                    policy = self._policy_for_kind(tracked_kind)
                    if entry.queued:
                        normalized_priority = int(priority)
                        if normalized_priority < entry.priority:
                            entry.priority = normalized_priority
                            heapq.heapify(self._queue)
                            self._coalesced_priority_upgrades += 1
                            self._track_kind(tracked_kind, "coalesced_priority_upgrades")
                            changed = True
                        if normalized_payload:
                            next_payload = self._merge_payload_for_policy(
                                current=entry.payload,
                                incoming=normalized_payload,
                                policy=policy,
                            )
                            if next_payload != entry.payload:
                                entry.payload = next_payload
                                self._coalesced_payload_updates += 1
                                self._track_kind(tracked_kind, "coalesced_payload_updates")
                                changed = True
                self._track_kind(tracked_kind, "coalesced")
                if changed:
                    await self._persist_journal_locked()
                future = existing
            else:
                policy = self._policy_for_kind(normalized_kind)
                pending_for_kind = self._pending_count_for_kind(normalized_kind)
                if pending_for_kind >= policy.quota:
                    self._dropped_backpressure += 1
                    self._dropped_quota += 1
                    self._track_kind(normalized_kind, "dropped_backpressure")
                    self._track_kind(normalized_kind, "dropped_quota")
                    return fallback_result
                if len(self._pending_by_key) >= self.max_pending:
                    self._dropped_backpressure += 1
                    self._dropped_global_backpressure += 1
                    self._track_kind(normalized_kind, "dropped_backpressure")
                    self._track_kind(normalized_kind, "dropped_global_backpressure")
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
                self._pending_entries_by_key[normalized_key] = entry
                self._enqueued += 1
                self._track_kind(normalized_kind, "enqueued")
                depth = len(self._queue)
                if depth > self._max_queue_depth_seen:
                    self._max_queue_depth_seen = depth
                await self._persist_journal_locked()
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
            "dropped_quota": self._dropped_quota,
            "dropped_global_backpressure": self._dropped_global_backpressure,
            "executed_ok": self._executed_ok,
            "executed_error": self._executed_error,
            "coalesced_priority_upgrades": self._coalesced_priority_upgrades,
            "coalesced_payload_updates": self._coalesced_payload_updates,
            "queue_depth": len(self._queue),
            "inflight": self._inflight,
            "max_queue_depth_seen": self._max_queue_depth_seen,
            "pending_count": len(self._pending_entries_by_key),
            "restored": self._restored,
            "journal_path": str(self.journal_path) if self.journal_path is not None else "",
            "journal_entries": len(self._pending_entries_by_key),
            "journal_load_failures": self._journal_load_failures,
            "journal_save_failures": self._journal_save_failures,
            "last_journal_error": self._last_journal_error,
            "last_error": task_error,
            "kind_limits": self._kind_limits_status(),
            "kind_policies": self._kind_policy_status(),
            "pending_by_kind": self._pending_by_kind_status(),
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
        task_state, task_error = self._task_snapshot()
        return {
            "running": bool(self._running and task_state == "running"),
            "worker_state": task_state,
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
            "last_error": task_error or self._last_error,
            "consecutive_error_count": self._consecutive_error_count,
            "last_snapshot": dict(self._last_snapshot),
            "cooldown_remaining_s": round(cooldown_remaining_s, 3),
        }
