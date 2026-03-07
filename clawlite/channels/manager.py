from __future__ import annotations

import asyncio
import hashlib
import contextvars
import json
import time
from collections import deque
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from clawlite.bus.events import InboundEvent, OutboundEvent
from clawlite.bus.queue import MessageQueue
from clawlite.channels.base import BaseChannel
from clawlite.channels.dingtalk import DingTalkChannel
from clawlite.channels.discord import DiscordChannel
from clawlite.channels.email import EmailChannel
from clawlite.channels.feishu import FeishuChannel
from clawlite.channels.googlechat import GoogleChatChannel
from clawlite.channels.imessage import IMessageChannel
from clawlite.channels.irc import IRCChannel
from clawlite.channels.matrix import MatrixChannel
from clawlite.channels.mochat import MochatChannel
from clawlite.channels.qq import QQChannel
from clawlite.channels.signal import SignalChannel
from clawlite.channels.slack import SlackChannel
from clawlite.channels.telegram import TelegramChannel
from clawlite.channels.whatsapp import WhatsAppChannel
from clawlite.utils.logging import bind_event, setup_logging


class EngineProtocol:
    async def run(
        self,
        *,
        session_id: str,
        user_text: str,
        channel: str | None = None,
        chat_id: str | None = None,
        progress_hook=None,
        stop_event=None,
    ): ...

    def request_stop(self, session_id: str) -> bool: ...


@dataclass(slots=True)
class _SessionDispatchSlot:
    semaphore: asyncio.Semaphore
    active_leases: int = 0
    last_used_at: float = 0.0


class ChannelManager:
    """Owns channel lifecycle and bridges channels <-> bus <-> engine."""

    _ENGINE_ERROR_FALLBACK_TEXT = "I hit an internal error while processing your request."

    def __init__(self, *, bus: MessageQueue, engine: EngineProtocol) -> None:
        setup_logging()
        self.bus = bus
        self.engine = engine
        self._registry: dict[str, type[BaseChannel]] = {
            "telegram": TelegramChannel,
            "discord": DiscordChannel,
            "slack": SlackChannel,
            "whatsapp": WhatsAppChannel,
            "signal": SignalChannel,
            "googlechat": GoogleChatChannel,
            "email": EmailChannel,
            "matrix": MatrixChannel,
            "irc": IRCChannel,
            "imessage": IMessageChannel,
            "dingtalk": DingTalkChannel,
            "feishu": FeishuChannel,
            "mochat": MochatChannel,
            "qq": QQChannel,
        }
        self._channels: dict[str, BaseChannel] = {}
        self._dispatcher_task: asyncio.Task[Any] | None = None
        self._active_tasks: dict[str, set[asyncio.Task[Any]]] = {}
        self._send_progress = False
        self._send_tool_hints = False
        self._dispatcher_max_concurrency = 4
        self._dispatcher_max_per_session = 1
        self._send_max_attempts = 3
        self._send_retry_backoff_s = 0.5
        self._send_retry_max_backoff_s = 4.0
        self._delivery_idempotency_ttl_s = 900.0
        self._delivery_idempotency_max_entries = 2048
        self._delivery_recent_limit = 50
        self._delivery_recent: deque[dict[str, Any]] = deque(maxlen=self._delivery_recent_limit)
        self._delivery_idempotency_cache: dict[str, float] = {}
        self._delivery_idempotency_order: deque[tuple[str, float]] = deque()
        self._dispatch_slots = asyncio.Semaphore(self._dispatcher_max_concurrency)
        self._session_slots: dict[str, _SessionDispatchSlot] = {}
        self._session_slots_max_entries = 2048
        self._dispatch_context: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
            "channel_dispatch_context",
            default=None,
        )
        self._delivery_total: dict[str, int] = {
            "attempts": 0,
            "success": 0,
            "failures": 0,
            "dead_lettered": 0,
            "replayed": 0,
            "channel_unavailable": 0,
            "policy_dropped": 0,
            "delivery_confirmed": 0,
            "delivery_failed_final": 0,
            "idempotency_suppressed": 0,
        }
        self._delivery_per_channel: dict[str, dict[str, int]] = {}
        self._delivery_persistence_path: Path | None = None
        self._delivery_replay_on_startup = True
        self._delivery_replay_limit = 50
        self._delivery_replay_reasons: tuple[str, ...] = ("send_failed", "channel_unavailable")
        self._delivery_persistence_lock = asyncio.Lock()
        self._delivery_persistence_pending = 0
        self._delivery_startup_replay: dict[str, Any] = {
            "enabled": False,
            "running": False,
            "path": "",
            "restored": 0,
            "replayed": 0,
            "failed": 0,
            "skipped": 0,
            "remaining": 0,
            "last_error": "",
            "replayed_by_channel": {},
            "failed_by_channel": {},
            "skipped_by_channel": {},
        }
        self._recovery_enabled = True
        self._recovery_interval_s = 15.0
        self._recovery_cooldown_s = 30.0
        self._recovery_task: asyncio.Task[Any] | None = None
        self._recovery_notifier: Callable[[dict[str, Any]], Awaitable[Any]] | None = None
        self._recovery_total: dict[str, int] = {
            "attempts": 0,
            "success": 0,
            "failures": 0,
            "skipped_cooldown": 0,
        }
        self._recovery_per_channel: dict[str, dict[str, Any]] = {}

    def _ensure_delivery_channel(self, channel: str) -> dict[str, int]:
        name = str(channel or "").strip() or "unknown"
        row = self._delivery_per_channel.get(name)
        if row is None:
            row = {
                "attempts": 0,
                "success": 0,
                "failures": 0,
                "dead_lettered": 0,
                "replayed": 0,
                "channel_unavailable": 0,
                "policy_dropped": 0,
                "delivery_confirmed": 0,
                "delivery_failed_final": 0,
                "idempotency_suppressed": 0,
            }
            self._delivery_per_channel[name] = row
        return row

    def _inc_delivery(self, *, channel: str, key: str, delta: int = 1) -> None:
        amount = int(delta)
        if amount <= 0:
            return
        self._delivery_total[key] = self._delivery_total.get(key, 0) + amount
        row = self._ensure_delivery_channel(channel)
        row[key] = row.get(key, 0) + amount

    def _set_delivery_recent_limit(self, limit: int) -> None:
        bounded = max(1, int(limit))
        if bounded == self._delivery_recent_limit:
            return
        recent_tail = list(self._delivery_recent)[-bounded:]
        self._delivery_recent_limit = bounded
        self._delivery_recent = deque(recent_tail, maxlen=bounded)

    @staticmethod
    def _delivery_metadata_value(metadata: Any, key: str, default: Any = "") -> Any:
        if not isinstance(metadata, dict):
            return default
        return metadata.get(key, default)

    def _record_delivery_recent(
        self,
        *,
        event: OutboundEvent,
        outcome: str,
        idempotency_key: str,
        send_result: str = "",
        receipt: Any = None,
        dead_letter_reason: str = "",
        last_error: str = "",
    ) -> None:
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        replayed_from_dead_letter = bool(self._delivery_metadata_value(metadata, "_replayed_from_dead_letter", False))
        safe_receipt: dict[str, Any] | None = None
        if isinstance(receipt, dict):
            safe_receipt = dict(receipt)
        elif isinstance(metadata, dict):
            from_metadata = metadata.get("_delivery_receipt")
            if isinstance(from_metadata, dict):
                safe_receipt = dict(from_metadata)

        entry: dict[str, Any] = {
            "channel": str(event.channel),
            "session_id": str(event.session_id),
            "target": str(event.target),
            "attempt": int(getattr(event, "attempt", 0) or 0),
            "max_attempts": int(getattr(event, "max_attempts", 0) or 0),
            "outcome": str(outcome),
            "idempotency_key": str(idempotency_key),
            "created_at": str(getattr(event, "created_at", "") or ""),
            "dead_letter_reason": str(dead_letter_reason or ""),
            "last_error": str(last_error or ""),
            "receipt": safe_receipt,
            "send_result": str(send_result or ""),
            "replayed_from_dead_letter": replayed_from_dead_letter,
        }
        self._delivery_recent.append(entry)

    @staticmethod
    def _derive_delivery_idempotency_key(event: OutboundEvent) -> str:
        payload = "\n".join(
            [
                str(event.channel),
                str(event.session_id),
                str(event.target),
                str(event.text),
                str(event.created_at),
            ]
        )
        return f"dlv:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"

    def _ensure_delivery_idempotency_key(self, event: OutboundEvent) -> tuple[OutboundEvent, str]:
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        explicit = str(metadata.get("_delivery_idempotency_key", "")).strip()
        if explicit:
            return event, explicit
        key = self._derive_delivery_idempotency_key(event)
        next_metadata = dict(metadata)
        next_metadata["_delivery_idempotency_key"] = key
        return replace(event, metadata=next_metadata), key

    def _prune_delivery_idempotency_cache(self, *, now: float | None = None) -> None:
        if self._delivery_idempotency_max_entries <= 0:
            self._delivery_idempotency_cache.clear()
            self._delivery_idempotency_order.clear()
            return

        current = time.monotonic() if now is None else now
        while self._delivery_idempotency_order:
            key, expiry = self._delivery_idempotency_order[0]
            if expiry > current:
                break
            self._delivery_idempotency_order.popleft()
            if self._delivery_idempotency_cache.get(key) == expiry:
                self._delivery_idempotency_cache.pop(key, None)

        while len(self._delivery_idempotency_cache) > self._delivery_idempotency_max_entries and self._delivery_idempotency_order:
            key, expiry = self._delivery_idempotency_order.popleft()
            if self._delivery_idempotency_cache.get(key) == expiry:
                self._delivery_idempotency_cache.pop(key, None)

    def _is_delivery_idempotency_suppressed(self, key: str) -> bool:
        current = time.monotonic()
        self._prune_delivery_idempotency_cache(now=current)
        expiry = self._delivery_idempotency_cache.get(key)
        if expiry is None:
            return False
        if expiry <= current:
            self._delivery_idempotency_cache.pop(key, None)
            return False
        return True

    def _remember_delivery_idempotency(self, key: str) -> None:
        ttl = max(0.0, float(self._delivery_idempotency_ttl_s))
        current = time.monotonic()
        expiry = current + ttl
        self._delivery_idempotency_cache[key] = expiry
        self._delivery_idempotency_order.append((key, expiry))
        self._prune_delivery_idempotency_cache(now=current)

    @staticmethod
    def _serialize_delivery_event(event: OutboundEvent) -> dict[str, Any]:
        payload = {
            "channel": str(event.channel),
            "session_id": str(event.session_id),
            "target": str(event.target),
            "text": str(event.text),
            "metadata": dict(event.metadata) if isinstance(event.metadata, dict) else {},
            "attempt": int(getattr(event, "attempt", 0) or 0),
            "max_attempts": int(getattr(event, "max_attempts", 0) or 0),
            "retryable": bool(getattr(event, "retryable", False)),
            "dead_lettered": bool(getattr(event, "dead_lettered", False)),
            "dead_letter_reason": str(getattr(event, "dead_letter_reason", "") or ""),
            "last_error": str(getattr(event, "last_error", "") or ""),
            "created_at": str(getattr(event, "created_at", "") or ""),
        }
        return json.loads(json.dumps(payload, ensure_ascii=True, default=str))

    def _delivery_record_key(self, event: OutboundEvent) -> str:
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        explicit = str(metadata.get("_delivery_idempotency_key", "") or "").strip()
        if explicit:
            return explicit
        return self._derive_delivery_idempotency_key(event)

    def _load_delivery_persistence_locked(self) -> list[OutboundEvent]:
        path = self._delivery_persistence_path
        if path is None or not path.exists():
            self._delivery_persistence_pending = 0
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            bind_event("channel.delivery").warning("delivery journal read failed path={} error={}", path, exc)
            self._delivery_persistence_pending = 0
            return []

        items = raw.get("items", []) if isinstance(raw, dict) else []
        events: list[OutboundEvent] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            metadata_raw = item.get("metadata", {})
            metadata = dict(metadata_raw) if isinstance(metadata_raw, dict) else {}
            event = OutboundEvent(
                channel=str(item.get("channel", "") or "").strip(),
                session_id=str(item.get("session_id", "") or "").strip(),
                target=str(item.get("target", "") or ""),
                text=str(item.get("text", "") or ""),
                metadata=metadata,
                attempt=max(1, int(item.get("attempt", 1) or 1)),
                max_attempts=max(1, int(item.get("max_attempts", 1) or 1)),
                retryable=bool(item.get("retryable", True)),
                dead_lettered=bool(item.get("dead_lettered", True)),
                dead_letter_reason=str(item.get("dead_letter_reason", "") or ""),
                last_error=str(item.get("last_error", "") or ""),
                created_at=str(item.get("created_at", "") or ""),
            )
            if not event.channel or not event.session_id:
                continue
            event, _ = self._ensure_delivery_idempotency_key(event)
            events.append(event)
        self._delivery_persistence_pending = len(events)
        return events

    def _write_delivery_persistence_locked(self, events: list[OutboundEvent]) -> None:
        path = self._delivery_persistence_path
        if path is None:
            self._delivery_persistence_pending = 0
            return
        self._delivery_persistence_pending = len(events)
        if not events:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "items": [self._serialize_delivery_event(event) for event in events],
        }
        tmp_path = path.with_name(f"{path.name}.tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True), encoding="utf-8")
        tmp_path.replace(path)

    async def _persist_dead_letter(self, event: OutboundEvent) -> None:
        if self._delivery_persistence_path is None:
            return
        pending_event, _ = self._ensure_delivery_idempotency_key(event)
        key = self._delivery_record_key(pending_event)
        async with self._delivery_persistence_lock:
            events = self._load_delivery_persistence_locked()
            kept = [row for row in events if self._delivery_record_key(row) != key]
            kept.append(pending_event)
            kept.sort(key=lambda row: str(getattr(row, "created_at", "") or ""))
            self._write_delivery_persistence_locked(kept)

    async def _clear_persisted_dead_letter(self, event: OutboundEvent) -> None:
        if self._delivery_persistence_path is None:
            return
        key = self._delivery_record_key(event)
        async with self._delivery_persistence_lock:
            events = self._load_delivery_persistence_locked()
            kept = [row for row in events if self._delivery_record_key(row) != key]
            self._write_delivery_persistence_locked(kept)

    async def _restore_persisted_dead_letters(self) -> int:
        if self._delivery_persistence_path is None:
            self._delivery_persistence_pending = 0
            return 0
        if int(self.bus.stats().get("dead_letter_size", 0) or 0) > 0:
            async with self._delivery_persistence_lock:
                self._load_delivery_persistence_locked()
            return 0
        async with self._delivery_persistence_lock:
            events = self._load_delivery_persistence_locked()
        if not events:
            return 0
        restored = await self.bus.restore_dead_letters(events)
        bind_event("channel.delivery").info(
            "delivery journal restored path={} restored={}",
            self._delivery_persistence_path,
            restored,
        )
        return restored

    async def _run_startup_delivery_replay(self) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "enabled": bool(self._delivery_replay_on_startup),
            "running": True,
            "path": str(self._delivery_persistence_path) if self._delivery_persistence_path is not None else "",
            "restored": 0,
            "replayed": 0,
            "failed": 0,
            "skipped": 0,
            "remaining": int(self.bus.stats().get("dead_letter_size", 0) or 0),
            "last_error": "",
            "replayed_by_channel": {},
            "failed_by_channel": {},
            "skipped_by_channel": {},
        }
        self._delivery_startup_replay = dict(summary)
        try:
            summary["restored"] = await self._restore_persisted_dead_letters()
            if self._delivery_replay_on_startup:
                replay = await self.replay_dead_letters(
                    limit=self._delivery_replay_limit,
                    reasons=list(self._delivery_replay_reasons),
                )
                for key in (
                    "replayed",
                    "failed",
                    "skipped",
                    "remaining",
                    "replayed_by_channel",
                    "failed_by_channel",
                    "skipped_by_channel",
                ):
                    summary[key] = replay.get(key, summary.get(key))
        except Exception as exc:
            summary["last_error"] = str(exc)
            bind_event("channel.delivery").warning("startup delivery replay failed error={}", exc)
        summary["running"] = False
        self._delivery_startup_replay = dict(summary)
        return dict(summary)

    def startup_replay_status(self) -> dict[str, Any]:
        return dict(self._delivery_startup_replay)

    def set_recovery_notifier(self, notifier: Callable[[dict[str, Any]], Awaitable[Any]] | None) -> None:
        self._recovery_notifier = notifier

    def _ensure_recovery_channel(self, channel: str) -> dict[str, Any]:
        name = str(channel or "").strip() or "unknown"
        row = self._recovery_per_channel.get(name)
        if row is None:
            row = {
                "attempts": 0,
                "success": 0,
                "failures": 0,
                "skipped_cooldown": 0,
                "last_recovery_at": "",
                "last_error": "",
                "last_reason": "",
                "_last_attempt_monotonic": 0.0,
            }
            self._recovery_per_channel[name] = row
        return row

    def _channel_worker_state(self, channel: BaseChannel) -> tuple[str, str]:
        task = getattr(channel, "_task", None)
        if task is None:
            return ("missing", "")
        if not isinstance(task, asyncio.Task):
            return ("external", "")
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

    async def _notify_recovery(self, payload: dict[str, Any]) -> None:
        notifier = self._recovery_notifier
        if notifier is None:
            return
        try:
            result = notifier(dict(payload))
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:
            bind_event("channel.recovery", channel=str(payload.get("channel", "") or "")).warning(
                "recovery notifier failed error={}",
                exc,
            )

    async def _recover_channel(self, channel_name: str, reason: str) -> bool:
        normalized = str(channel_name or "").strip().lower()
        channel = self._channels.get(normalized)
        if channel is None:
            return False

        row = self._ensure_recovery_channel(normalized)
        now = time.monotonic()
        last_attempt = float(row.get("_last_attempt_monotonic", 0.0) or 0.0)
        if self._recovery_cooldown_s > 0 and last_attempt > 0 and now < (last_attempt + self._recovery_cooldown_s):
            self._recovery_total["skipped_cooldown"] += 1
            row["skipped_cooldown"] = int(row.get("skipped_cooldown", 0) or 0) + 1
            return False

        row["_last_attempt_monotonic"] = now
        row["last_reason"] = str(reason or "")
        self._recovery_total["attempts"] += 1
        row["attempts"] = int(row.get("attempts", 0) or 0) + 1
        recovery_at = datetime.now(timezone.utc).isoformat()
        cls = self._registry.get(normalized)
        if cls is None:
            self._recovery_total["failures"] += 1
            row["failures"] = int(row.get("failures", 0) or 0) + 1
            row["last_recovery_at"] = recovery_at
            row["last_error"] = "channel_recovery_unregistered"
            return False

        replacement: BaseChannel | None = None
        try:
            await channel.stop()
        except Exception as exc:
            bind_event("channel.recovery", channel=normalized).warning("channel stop before recovery failed error={}", exc)

        try:
            replacement = cls(config=dict(getattr(channel, "config", {}) or {}), on_message=self._on_channel_message)
            self._channels[normalized] = replacement
            await replacement.start()
        except Exception as exc:
            if replacement is not None:
                try:
                    await replacement.stop()
                except Exception:
                    pass
            self._channels[normalized] = channel
            self._recovery_total["failures"] += 1
            row["failures"] = int(row.get("failures", 0) or 0) + 1
            row["last_recovery_at"] = recovery_at
            row["last_error"] = str(exc)
            bind_event("channel.recovery", channel=normalized).error("channel recovery failed reason={} error={}", reason, exc)
            await self._notify_recovery(
                {
                    "channel": normalized,
                    "status": "failed",
                    "reason": str(reason or ""),
                    "error": str(exc),
                    "at": recovery_at,
                }
            )
            return False

        self._recovery_total["success"] += 1
        row["success"] = int(row.get("success", 0) or 0) + 1
        row["last_recovery_at"] = recovery_at
        row["last_error"] = ""
        bind_event("channel.recovery", channel=normalized).info("channel recovered reason={}", reason)
        await self._notify_recovery(
            {
                "channel": normalized,
                "status": "recovered",
                "reason": str(reason or ""),
                "at": recovery_at,
            }
        )
        return True

    async def _recovery_loop(self) -> None:
        while True:
            try:
                if not self._recovery_enabled:
                    await asyncio.sleep(self._recovery_interval_s)
                    continue
                for name, channel in list(self._channels.items()):
                    health = channel.health()
                    task_state, task_error = self._channel_worker_state(channel)
                    if not health.running:
                        await self._recover_channel(name, reason="channel_stopped")
                        continue
                    if task_state in {"failed", "done", "cancelled"}:
                        reason = f"worker_{task_state}"
                        if task_error:
                            reason = f"{reason}:{task_error}"
                        await self._recover_channel(name, reason=reason)
                await asyncio.sleep(self._recovery_interval_s)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                bind_event("channel.recovery").error("channel recovery loop failed error={}", exc)
                await asyncio.sleep(min(max(self._recovery_interval_s, 1.0), 5.0))

    def register(self, name: str, channel_cls: type[BaseChannel]) -> None:
        self._registry[name] = channel_cls

    async def _on_channel_message(self, session_id: str, user_id: str, text: str, metadata: dict[str, Any]) -> None:
        channel = str(metadata.get("channel", "")).strip() or session_id.split(":", 1)[0]
        bind_event("channel.inbound", session=session_id, channel=channel).debug("inbound message queued user={} chars={}", user_id, len(text))
        await self.bus.publish_inbound(
            InboundEvent(
                channel=channel,
                session_id=session_id,
                user_id=user_id,
                text=text,
                metadata=metadata,
            )
        )

    @staticmethod
    def _is_stop_command(text: str) -> bool:
        return str(text or "").strip().lower() in {"/stop", "stop"}

    @staticmethod
    def _safe_remove_task(store: dict[str, set[asyncio.Task[Any]]], session_id: str, task: asyncio.Task[Any]) -> None:
        group = store.get(session_id)
        if not group:
            return
        group.discard(task)
        if not group:
            store.pop(session_id, None)

    def _reset_dispatch_controls(self) -> None:
        self._dispatch_slots = asyncio.Semaphore(self._dispatcher_max_concurrency)
        self._session_slots.clear()

    def _prune_session_slots(self) -> None:
        limit = max(1, int(self._session_slots_max_entries))
        if len(self._session_slots) <= limit:
            return
        removable: list[tuple[str, float]] = []
        for sid, slot in self._session_slots.items():
            if slot.active_leases != 0:
                continue
            removable.append((sid, float(slot.last_used_at)))
        if not removable:
            return
        removable.sort(key=lambda item: item[1])
        overflow = len(self._session_slots) - limit
        for sid, _ in removable[:overflow]:
            self._session_slots.pop(sid, None)

    def _session_slot(self, session_id: str) -> _SessionDispatchSlot:
        slot = self._session_slots.get(session_id)
        if slot is None:
            slot = _SessionDispatchSlot(
                semaphore=asyncio.Semaphore(self._dispatcher_max_per_session),
                active_leases=0,
                last_used_at=time.monotonic(),
            )
            self._session_slots[session_id] = slot
        return slot

    async def _acquire_dispatch_slot(self, session_id: str) -> None:
        await self._dispatch_slots.acquire()
        slot = self._session_slot(session_id)
        slot.active_leases += 1
        slot.last_used_at = time.monotonic()
        try:
            await slot.semaphore.acquire()
        except Exception:
            slot.active_leases = max(0, slot.active_leases - 1)
            slot.last_used_at = time.monotonic()
            self._dispatch_slots.release()
            self._prune_session_slots()
            raise

    def _release_dispatch_slot(self, session_id: str) -> None:
        self._dispatch_slots.release()
        slot = self._session_slots.get(session_id)
        if slot is None:
            return
        slot.semaphore.release()
        slot.active_leases = max(0, slot.active_leases - 1)
        slot.last_used_at = time.monotonic()
        self._prune_session_slots()

    @staticmethod
    def _is_progress_event(event: OutboundEvent) -> bool:
        return bool(event.metadata.get("_progress", False))

    @staticmethod
    def _is_tool_hint_event(event: OutboundEvent) -> bool:
        return bool(event.metadata.get("_tool_hint", False))

    def _delivery_allowed(self, *, channel: BaseChannel, event: OutboundEvent) -> bool:
        if not self._is_progress_event(event):
            return True
        if self._is_tool_hint_event(event):
            return self._send_tool_hints and channel.capabilities.supports_tool_hints
        return self._send_progress and channel.capabilities.supports_progress

    @staticmethod
    def _target_from_session_id(channel: str, session_id: str) -> str:
        channel_name = str(channel or "").strip().lower()
        raw = str(session_id or "").strip()
        if not raw:
            return ""
        if channel_name == "telegram":
            if raw.startswith("telegram:"):
                payload = raw.split(":", 1)[1].strip()
                if ":topic:" in payload:
                    chat_id, _, thread_id = payload.partition(":topic:")
                    thread = thread_id.strip()
                    return f"{chat_id.strip()}:{thread}" if thread else chat_id.strip()
                return payload
            if raw.startswith("tg_"):
                raw = raw[3:]
                if ":topic:" in raw:
                    chat_id, _, thread_id = raw.partition(":topic:")
                    thread = thread_id.strip()
                    return f"{chat_id.strip()}:{thread}" if thread else chat_id.strip()
                return raw.strip()
        if ":" in raw:
            return raw.split(":", 1)[1].strip()
        return raw

    async def send_outbound(
        self,
        *,
        channel: str,
        session_id: str,
        text: str,
        instance_key: str = "",
    ) -> str:
        del instance_key
        channel_name = str(channel or "").strip().lower()
        target = self._target_from_session_id(channel_name, session_id)
        if not target:
            raise ValueError("invalid_outbound_session")
        if channel_name not in self._channels:
            raise RuntimeError(f"outbound channel unavailable: {channel_name}")
        return await self.send(channel=channel_name, target=target, text=str(text or ""))

    async def _retry_send(self, *, channel: BaseChannel, event: OutboundEvent) -> OutboundEvent | None:
        max_attempts = max(1, self._send_max_attempts)
        last_error = ""
        backoff = self._send_retry_backoff_s
        event, idempotency_key = self._ensure_delivery_idempotency_key(event)
        if self._is_delivery_idempotency_suppressed(idempotency_key):
            self._inc_delivery(channel=event.channel, key="idempotency_suppressed")
            suppressed_event = replace(
                event,
                attempt=0,
                max_attempts=max_attempts,
                retryable=channel.capabilities.supports_retry,
                dead_lettered=False,
                dead_letter_reason="",
                last_error="",
            )
            self._record_delivery_recent(
                event=suppressed_event,
                outcome="idempotency_suppressed",
                idempotency_key=idempotency_key,
            )
            await self._clear_persisted_dead_letter(suppressed_event)
            bind_event("channel.send", session=event.session_id, channel=event.channel).info(
                "dispatch suppressed duplicate target={} key={}",
                event.target,
                idempotency_key,
            )
            return suppressed_event
        for attempt in range(1, max_attempts + 1):
            attempt_event = replace(
                event,
                attempt=attempt,
                max_attempts=max_attempts,
                retryable=channel.capabilities.supports_retry,
                dead_lettered=False,
                dead_letter_reason="",
                last_error=last_error,
            )
            await self.bus.publish_outbound(attempt_event)
            self._inc_delivery(channel=event.channel, key="attempts")
            try:
                send_result = await channel.send(target=event.target, text=event.text, metadata=event.metadata)
                self._inc_delivery(channel=event.channel, key="success")
                self._inc_delivery(channel=event.channel, key="delivery_confirmed")
                self._remember_delivery_idempotency(idempotency_key)
                self._record_delivery_recent(
                    event=attempt_event,
                    outcome="delivery_confirmed",
                    idempotency_key=idempotency_key,
                    send_result=send_result,
                )
                await self._clear_persisted_dead_letter(attempt_event)
                bind_event("channel.send", session=event.session_id, channel=event.channel).info(
                    "dispatch sent target={} attempt={}/{}",
                    event.target,
                    attempt,
                    max_attempts,
                )
                return attempt_event
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._inc_delivery(channel=event.channel, key="failures")
                last_error = str(exc)
                bind_event("channel.send", session=event.session_id, channel=event.channel).error(
                    "dispatch send failed target={} attempt={}/{} error={}",
                    event.target,
                    attempt,
                    max_attempts,
                    exc,
                )
                if attempt >= max_attempts or not channel.capabilities.supports_retry:
                    break
                await asyncio.sleep(min(backoff, self._send_retry_max_backoff_s))
                backoff = min(max(backoff * 2, self._send_retry_backoff_s), self._send_retry_max_backoff_s)

        dead = replace(
            event,
            attempt=max_attempts,
            max_attempts=max_attempts,
            retryable=channel.capabilities.supports_retry,
            dead_lettered=True,
            dead_letter_reason="send_failed",
            last_error=last_error,
        )
        await self.bus.publish_dead_letter(dead)
        self._inc_delivery(channel=event.channel, key="dead_lettered")
        self._inc_delivery(channel=event.channel, key="delivery_failed_final")
        await self._persist_dead_letter(dead)
        self._record_delivery_recent(
            event=dead,
            outcome="delivery_failed_final",
            idempotency_key=idempotency_key,
            dead_letter_reason=dead.dead_letter_reason,
            last_error=dead.last_error,
        )
        bind_event("channel.send", session=event.session_id, channel=event.channel).error(
            "dispatch dead-letter target={} attempts={} error={}",
            event.target,
            max_attempts,
            last_error,
        )
        return None

    async def _publish_and_send(self, *, event: OutboundEvent) -> bool:
        channel = self._channels.get(event.channel)
        if channel is None:
            self._inc_delivery(channel=event.channel, key="channel_unavailable")
            bind_event("channel.dispatch", session=event.session_id, channel=event.channel).error("channel unavailable")
            dead_event, idempotency_key = self._ensure_delivery_idempotency_key(event)
            dead = replace(
                dead_event,
                attempt=1,
                max_attempts=1,
                retryable=False,
                dead_lettered=True,
                dead_letter_reason="channel_unavailable",
                last_error="channel unavailable",
            )
            await self.bus.publish_dead_letter(dead)
            self._inc_delivery(channel=event.channel, key="dead_lettered")
            self._inc_delivery(channel=event.channel, key="delivery_failed_final")
            await self._persist_dead_letter(dead)
            self._record_delivery_recent(
                event=dead,
                outcome="delivery_failed_final",
                idempotency_key=idempotency_key,
                dead_letter_reason=dead.dead_letter_reason,
                last_error=dead.last_error,
            )
            return False
        if not self._delivery_allowed(channel=channel, event=event):
            self._inc_delivery(channel=event.channel, key="policy_dropped")
            bind_event("channel.send", session=event.session_id, channel=event.channel).debug(
                "dispatch dropped by delivery policy target={}",
                event.target,
            )
            return True
        return await self._retry_send(channel=channel, event=event) is not None

    async def replay_dead_letters(
        self,
        *,
        limit: int = 100,
        channel: str = "",
        reason: str = "",
        session_id: str = "",
        reasons: list[str] | tuple[str, ...] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        bounded_limit = max(0, int(limit or 0))
        channel_filter = str(channel or "").strip()
        reason_filter = str(reason or "").strip()
        session_filter = str(session_id or "").strip()
        reasons_filter = {str(item or "").strip() for item in reasons or () if str(item or "").strip()}
        snapshot = self.bus.dead_letter_snapshot()
        scanned = len(snapshot)

        matched_events: list[OutboundEvent] = []
        for event in snapshot:
            if channel_filter and event.channel != channel_filter:
                continue
            if session_filter and event.session_id != session_filter:
                continue
            event_reason = str(event.dead_letter_reason or "")
            if reason_filter and event_reason != reason_filter:
                continue
            if reasons_filter and event_reason not in reasons_filter:
                continue
            matched_events.append(event)

        matched = len(matched_events)
        if dry_run or bounded_limit <= 0:
            return {
                "scanned": scanned,
                "matched": matched,
                "replayed": 0,
                "failed": 0,
                "skipped": 0,
                "kept": int(self.bus.stats().get("dead_letter_size", 0) or 0),
                "dropped": 0,
                "remaining": int(self.bus.stats().get("dead_letter_size", 0) or 0),
                "replayed_by_channel": {},
                "failed_by_channel": {},
                "skipped_by_channel": {},
                "dry_run": bool(dry_run),
                "limit": bounded_limit,
            }

        replayed = 0
        failed = 0
        skipped = 0
        replayed_by_channel: dict[str, int] = {}
        failed_by_channel: dict[str, int] = {}
        skipped_by_channel: dict[str, int] = {}
        skipped_events: list[OutboundEvent] = []

        for event in matched_events[:bounded_limit]:
            event, idempotency_key = self._ensure_delivery_idempotency_key(event)
            drained = await self.bus.drain_dead_letters(
                limit=1,
                channel=event.channel,
                reason=event.dead_letter_reason,
                session_id=event.session_id,
                idempotency_key=idempotency_key,
            )
            if not drained:
                continue
            pending = drained[0]
            if pending.channel not in self._channels:
                skipped += 1
                skipped_by_channel[pending.channel] = skipped_by_channel.get(pending.channel, 0) + 1
                skipped_events.append(pending)
                continue
            replay_metadata = dict(pending.metadata) if isinstance(pending.metadata, dict) else {}
            replay_metadata["_replayed_from_dead_letter"] = True
            replay_event = replace(
                pending,
                metadata=replay_metadata,
                attempt=1,
                dead_lettered=False,
                dead_letter_reason="",
                last_error="",
            )
            delivered = await self._publish_and_send(event=replay_event)
            if delivered:
                replayed += 1
                replayed_by_channel[pending.channel] = replayed_by_channel.get(pending.channel, 0) + 1
                self._inc_delivery(channel=pending.channel, key="replayed")
                continue
            failed += 1
            failed_by_channel[pending.channel] = failed_by_channel.get(pending.channel, 0) + 1

        if skipped_events:
            await self.bus.restore_dead_letters(skipped_events)

        remaining = int(self.bus.stats().get("dead_letter_size", 0) or 0)
        return {
            "scanned": scanned,
            "matched": matched,
            "replayed": replayed,
            "failed": failed,
            "skipped": skipped,
            "kept": remaining,
            "dropped": 0,
            "remaining": remaining,
            "replayed_by_channel": dict(sorted(replayed_by_channel.items())),
            "failed_by_channel": dict(sorted(failed_by_channel.items())),
            "skipped_by_channel": dict(sorted(skipped_by_channel.items())),
            "dry_run": False,
            "limit": bounded_limit,
        }

    def delivery_diagnostics(self) -> dict[str, Any]:
        return {
            "total": dict(self._delivery_total),
            "per_channel": {name: dict(row) for name, row in sorted(self._delivery_per_channel.items())},
            "recent": list(reversed(self._delivery_recent)),
            "persistence": {
                "enabled": self._delivery_persistence_path is not None,
                "path": str(self._delivery_persistence_path) if self._delivery_persistence_path is not None else "",
                "pending": int(self._delivery_persistence_pending),
                "startup_replay": dict(self._delivery_startup_replay),
            },
        }

    async def _handle_stop(self, event: InboundEvent) -> None:
        session_id = event.session_id
        self.bus.request_stop(session_id)
        request_stop = getattr(self.engine, "request_stop", None)
        if callable(request_stop):
            request_stop(session_id)

        cancelled_subagents = 0
        subagents = getattr(self.engine, "subagents", None)
        if subagents is None:
            subagents = getattr(self.engine, "subagent_manager", None)
        cancel_session = getattr(subagents, "cancel_session", None)
        if callable(cancel_session):
            try:
                cancelled_subagents = max(0, int(cancel_session(session_id) or 0))
            except Exception as exc:
                bind_event("channel.dispatch", session=session_id, channel=event.channel).error(
                    "dispatch subagent cancel failed error={}",
                    exc,
                )

        tasks = list(self._active_tasks.get(session_id, set()))
        cancelled = 0
        for task in tasks:
            if not task.done() and task.cancel():
                cancelled += 1
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        target = self._target_from_event(event)
        text = f"Stopped {cancelled} active task(s); cancelled {cancelled_subagents} subagent run(s)."
        await self._publish_and_send(
            event=OutboundEvent(
                channel=event.channel,
                session_id=session_id,
                target=target,
                text=text,
                metadata={
                    "_control": "stop",
                    "cancelled_tasks": cancelled,
                    "cancelled_subagents": cancelled_subagents,
                },
            )
        )

    async def _dispatch_event(self, event: InboundEvent) -> None:
        bind_event("channel.dispatch", session=event.session_id, channel=event.channel).debug("dispatch processing target={}", event.user_id)
        target = self._target_from_event(event)

        async def _progress_hook(progress) -> None:
            stage = str(getattr(progress, "stage", "progress") or "progress")
            message = str(getattr(progress, "message", "") or "").strip()
            if not message:
                return
            metadata = {
                "_progress": True,
                "stage": stage,
                "iteration": int(getattr(progress, "iteration", 0) or 0),
            }
            tool_name = str(getattr(progress, "tool_name", "") or "").strip()
            if tool_name:
                metadata["tool"] = tool_name
                metadata["_tool_hint"] = True
            extra = getattr(progress, "metadata", None)
            if isinstance(extra, dict):
                metadata.update(extra)
            await self._publish_and_send(
                event=OutboundEvent(
                    channel=event.channel,
                    session_id=event.session_id,
                    target=target,
                    text=message,
                    metadata=metadata,
                )
            )

        dispatch_token = self._dispatch_context.set({"session_id": event.session_id, "sent_targets": set()})
        suppress_final_reply = False
        try:
            result = await self.engine.run(
                session_id=event.session_id,
                user_text=event.text,
                channel=event.channel,
                chat_id=target,
                progress_hook=_progress_hook,
                stop_event=self.bus.stop_event(event.session_id),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            bind_event("channel.dispatch", session=event.session_id, channel=event.channel).error("dispatch engine failed error={}", exc)
            await self._publish_and_send(
                event=OutboundEvent(
                    channel=event.channel,
                    session_id=event.session_id,
                    target=target,
                    text=self._ENGINE_ERROR_FALLBACK_TEXT,
                    metadata={
                        "_error": "dispatch_engine_exception",
                        "error_type": type(exc).__name__,
                    },
                )
            )
            return
        finally:
            self.bus.clear_stop(event.session_id)
            dispatch_context = self._dispatch_context.get()
            sent_targets = dispatch_context.get("sent_targets", set()) if isinstance(dispatch_context, dict) else set()
            if (event.channel, target) in sent_targets:
                suppress_final_reply = True
            self._dispatch_context.reset(dispatch_token)

        if suppress_final_reply:
            bind_event("channel.dispatch", session=event.session_id, channel=event.channel).debug(
                "dispatch final reply suppressed target={} reason=already_sent_in_turn",
                target,
            )
            return

        await self._publish_and_send(
            event=OutboundEvent(
                channel=event.channel,
                session_id=event.session_id,
                target=target,
                text=result.text,
                metadata={"model": getattr(result, "model", "")},
            )
        )

    async def _dispatch_loop(self) -> None:
        while True:
            try:
                event = await self.bus.next_inbound()
                if self._is_stop_command(event.text):
                    await self._handle_stop(event)
                    continue

                async def _dispatch_worker(current: InboundEvent) -> None:
                    acquired = False
                    try:
                        await self._acquire_dispatch_slot(current.session_id)
                        acquired = True
                        await self._dispatch_event(current)
                    finally:
                        if acquired:
                            self._release_dispatch_slot(current.session_id)

                task = asyncio.create_task(_dispatch_worker(event))
                bucket = self._active_tasks.setdefault(event.session_id, set())
                bucket.add(task)

                def _on_done(done: asyncio.Task[Any], sid: str = event.session_id) -> None:
                    self._safe_remove_task(self._active_tasks, sid, done)

                task.add_done_callback(_on_done)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                bind_event("channel.dispatch").error("dispatch loop failed error={}", exc)
                await asyncio.sleep(0.05)

    async def start(self, config: dict[str, Any]) -> None:
        channels_cfg = config.get("channels", {}) if isinstance(config, dict) else {}
        self._send_progress = bool(channels_cfg.get("send_progress", channels_cfg.get("sendProgress", False)))
        self._send_tool_hints = bool(channels_cfg.get("send_tool_hints", channels_cfg.get("sendToolHints", False)))
        self._dispatcher_max_concurrency = max(
            1,
            int(channels_cfg.get("dispatcher_max_concurrency", channels_cfg.get("dispatcherMaxConcurrency", 4)) or 4),
        )
        self._dispatcher_max_per_session = max(
            1,
            int(channels_cfg.get("dispatcher_max_per_session", channels_cfg.get("dispatcherMaxPerSession", 1)) or 1),
        )
        self._session_slots_max_entries = max(
            1,
            int(channels_cfg.get("dispatcher_session_slots_max_entries", channels_cfg.get("dispatcherSessionSlotsMaxEntries", 2048)) or 2048),
        )
        self._send_max_attempts = max(1, int(channels_cfg.get("send_max_attempts", channels_cfg.get("sendMaxAttempts", 3)) or 3))
        self._send_retry_backoff_s = max(
            0.0,
            float(channels_cfg.get("send_retry_backoff_s", channels_cfg.get("sendRetryBackoffS", 0.5)) or 0.5),
        )
        self._send_retry_max_backoff_s = max(
            self._send_retry_backoff_s,
            float(channels_cfg.get("send_retry_max_backoff_s", channels_cfg.get("sendRetryMaxBackoffS", 4.0)) or 4.0),
        )
        self._delivery_idempotency_ttl_s = max(
            0.0,
            float(channels_cfg.get("delivery_idempotency_ttl_s", channels_cfg.get("deliveryIdempotencyTtlS", 900.0)) or 900.0),
        )
        self._delivery_idempotency_max_entries = max(
            1,
            int(
                channels_cfg.get(
                    "delivery_idempotency_max_entries",
                    channels_cfg.get("deliveryIdempotencyMaxEntries", 2048),
                )
                or 2048
            ),
        )
        delivery_recent_limit = channels_cfg.get("delivery_recent_limit", channels_cfg.get("deliveryRecentLimit", 50))
        try:
            parsed_recent_limit = int(delivery_recent_limit or 50)
        except (TypeError, ValueError):
            parsed_recent_limit = 50
        self._set_delivery_recent_limit(parsed_recent_limit)
        replay_on_startup_raw = channels_cfg.get(
            "replay_dead_letters_on_startup",
            channels_cfg.get("replayDeadLettersOnStartup", True),
        )
        self._delivery_replay_on_startup = bool(replay_on_startup_raw)
        replay_limit_raw = channels_cfg.get("replay_dead_letters_limit", channels_cfg.get("replayDeadLettersLimit", 50))
        try:
            self._delivery_replay_limit = max(0, int(replay_limit_raw or 50))
        except (TypeError, ValueError):
            self._delivery_replay_limit = 50
        replay_reasons_raw = channels_cfg.get(
            "replay_dead_letters_reasons",
            channels_cfg.get("replayDeadLettersReasons", ["send_failed", "channel_unavailable"]),
        )
        if isinstance(replay_reasons_raw, list):
            replay_reasons = [str(item or "").strip() for item in replay_reasons_raw if str(item or "").strip()]
        else:
            replay_reasons = ["send_failed", "channel_unavailable"]
        self._delivery_replay_reasons = tuple(replay_reasons or ["send_failed", "channel_unavailable"])
        persistence_path_raw = channels_cfg.get(
            "delivery_persistence_path",
            channels_cfg.get("deliveryPersistencePath", ""),
        )
        if persistence_path_raw:
            self._delivery_persistence_path = Path(str(persistence_path_raw)).expanduser()
        else:
            state_path_raw = str(config.get("state_path", "") or "").strip()
            if state_path_raw:
                state_root = Path(state_path_raw).expanduser()
                self._delivery_persistence_path = state_root / "channels" / "delivery-dead-letters.json"
            else:
                self._delivery_persistence_path = None
        self._recovery_enabled = bool(channels_cfg.get("recovery_enabled", channels_cfg.get("recoveryEnabled", True)))
        self._recovery_interval_s = max(
            0.1,
            float(channels_cfg.get("recovery_interval_s", channels_cfg.get("recoveryIntervalS", 15.0)) or 15.0),
        )
        self._recovery_cooldown_s = max(
            0.0,
            float(channels_cfg.get("recovery_cooldown_s", channels_cfg.get("recoveryCooldownS", 30.0)) or 30.0),
        )
        self._prune_delivery_idempotency_cache()
        self._reset_dispatch_controls()
        self._delivery_startup_replay = {
            "enabled": bool(self._delivery_replay_on_startup),
            "running": False,
            "path": str(self._delivery_persistence_path) if self._delivery_persistence_path is not None else "",
            "restored": 0,
            "replayed": 0,
            "failed": 0,
            "skipped": 0,
            "remaining": int(self.bus.stats().get("dead_letter_size", 0) or 0),
            "last_error": "",
            "replayed_by_channel": {},
            "failed_by_channel": {},
            "skipped_by_channel": {},
        }
        async with self._delivery_persistence_lock:
            self._load_delivery_persistence_locked()

        for name, row in channels_cfg.items():
            if not isinstance(row, dict):
                continue
            if not row.get("enabled", False):
                continue
            cls = self._registry.get(name)
            if cls is None:
                bind_event("channel.lifecycle", channel=name).error("channel enabled but not registered")
                continue
            bind_event("channel.lifecycle", channel=name).info("channel enabled")
            channel = cls(config=row, on_message=self._on_channel_message)
            self._channels[name] = channel
            await channel.start()
            bind_event("channel.lifecycle", channel=name).info("channel started")

        if self._dispatcher_task is None:
            self._dispatcher_task = asyncio.create_task(self._dispatch_loop())
            bind_event("channel.lifecycle").info("channel dispatcher started")
        if self._recovery_task is None:
            self._recovery_task = asyncio.create_task(self._recovery_loop())
            bind_event("channel.lifecycle").info(
                "channel recovery supervisor started enabled={} interval_s={} cooldown_s={}",
                self._recovery_enabled,
                self._recovery_interval_s,
                self._recovery_cooldown_s,
            )

        await self._run_startup_delivery_replay()

    async def stop(self) -> None:
        for session_id, tasks in list(self._active_tasks.items()):
            self.bus.request_stop(session_id)
            request_stop = getattr(self.engine, "request_stop", None)
            if callable(request_stop):
                request_stop(session_id)
            for task in list(tasks):
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
        self._active_tasks.clear()

        if self._dispatcher_task is not None:
            bind_event("channel.lifecycle").info("channel dispatcher stopping")
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass
            self._dispatcher_task = None
            bind_event("channel.lifecycle").info("channel dispatcher stopped")

        if self._recovery_task is not None:
            bind_event("channel.lifecycle").info("channel recovery supervisor stopping")
            self._recovery_task.cancel()
            try:
                await self._recovery_task
            except asyncio.CancelledError:
                pass
            self._recovery_task = None
            bind_event("channel.lifecycle").info("channel recovery supervisor stopped")

        for name, channel in list(self._channels.items()):
            bind_event("channel.lifecycle", channel=name).info("channel stopping")
            await channel.stop()
            bind_event("channel.lifecycle", channel=name).info("channel stopped")
        self._channels.clear()

    async def send(self, *, channel: str, target: str, text: str, metadata: dict[str, Any] | None = None) -> str:
        instance = self._channels.get(channel)
        if instance is None:
            raise KeyError(f"channel_not_available:{channel}")
        response = await instance.send(target=target, text=text, metadata=metadata or {})
        dispatch_context = self._dispatch_context.get()
        if isinstance(dispatch_context, dict):
            sent_targets = dispatch_context.get("sent_targets")
            if isinstance(sent_targets, set):
                sent_targets.add((str(channel), str(target)))
        return response

    def get_channel(self, name: str) -> BaseChannel | None:
        return self._channels.get(str(name or "").strip().lower())

    @staticmethod
    def _target_from_event(event: InboundEvent) -> str:
        target = str(event.metadata.get("chat_id") or event.user_id)
        if event.channel != "telegram":
            return target
        thread_raw = event.metadata.get("message_thread_id")
        try:
            thread_id = int(thread_raw)
        except (TypeError, ValueError):
            return target
        if thread_id <= 0:
            return target
        return f"{target}:{thread_id}"

    def status(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for name, ch in self._channels.items():
            task_state, task_error = self._channel_worker_state(ch)
            recovery_row = dict(self._ensure_recovery_channel(name))
            recovery_row.pop("_last_attempt_monotonic", None)
            row: dict[str, Any] = {
                "running": ch.running,
                "last_error": ch.health().last_error,
                "task_state": task_state,
                "task_error": task_error,
                "delivery": dict(self._ensure_delivery_channel(name)),
                "recovery": recovery_row,
            }
            channel_signals = getattr(ch, "signals", None)
            if callable(channel_signals):
                try:
                    signals = channel_signals()
                except Exception:
                    signals = None
                if isinstance(signals, dict) and signals:
                    row["signals"] = signals
            out[name] = row
        return out
