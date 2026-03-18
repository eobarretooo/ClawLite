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
        self._delivery_idempotency_persistence_path: Path | None = None
        self._delivery_idempotency_persistence_lock = asyncio.Lock()
        self._delivery_idempotency_persistence_pending = 0
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
        self._delivery_manual_replay: dict[str, Any] = {
            "running": False,
            "last_at": "",
            "last_error": "",
            "restored": 0,
            "restored_idempotency_keys": 0,
            "scanned": 0,
            "matched": 0,
            "replayed": 0,
            "failed": 0,
            "skipped": 0,
            "suppressed": 0,
            "remaining": 0,
            "replayed_by_channel": {},
            "failed_by_channel": {},
            "skipped_by_channel": {},
            "suppressed_by_channel": {},
        }
        self._operator_recovery: dict[str, Any] = {
            "running": False,
            "last_at": "",
            "last_error": "",
            "attempted": 0,
            "recovered": 0,
            "failed": 0,
            "skipped_healthy": 0,
            "skipped_cooldown": 0,
            "not_found": 0,
            "forced": False,
            "channels": [],
        }
        self._inbound_persistence_path: Path | None = None
        self._inbound_replay_on_startup = True
        self._inbound_replay_limit = 100
        self._inbound_persistence_lock = asyncio.Lock()
        self._inbound_persistence_pending = 0
        self._inbound_startup_replay: dict[str, Any] = {
            "enabled": False,
            "running": False,
            "path": "",
            "restored": 0,
            "replayed": 0,
            "remaining": 0,
            "last_error": "",
            "replayed_by_channel": {},
        }
        self._inbound_manual_replay: dict[str, Any] = {
            "running": False,
            "last_at": "",
            "last_error": "",
            "restored": 0,
            "replayed": 0,
            "remaining": 0,
            "skipped_busy": 0,
            "replayed_by_channel": {},
        }
        self._recovery_enabled = True
        self._recovery_interval_s = 15.0
        self._recovery_cooldown_s = 30.0
        self._recovery_task: asyncio.Task[Any] | None = None
        self._recovery_notifier: Callable[[dict[str, Any]], Awaitable[Any]] | None = None
        self._inbound_interceptor: Callable[[InboundEvent], Awaitable[bool]] | None = None
        self._recovery_total: dict[str, int] = {
            "attempts": 0,
            "success": 0,
            "failures": 0,
            "skipped_cooldown": 0,
        }
        self._recovery_per_channel: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _background_task_state(task: asyncio.Task[Any] | None) -> tuple[str, str]:
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
            self._delivery_idempotency_persistence_pending = 0
            return

        current = time.time() if now is None else now
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
        self._delivery_idempotency_persistence_pending = len(self._delivery_idempotency_cache)

    def _is_delivery_idempotency_suppressed(self, key: str) -> bool:
        current = time.time()
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
        current = time.time()
        expiry = current + ttl
        self._delivery_idempotency_cache[key] = expiry
        self._delivery_idempotency_order.append((key, expiry))
        self._prune_delivery_idempotency_cache(now=current)

    def _load_delivery_idempotency_persistence_locked(self) -> dict[str, float]:
        path = self._delivery_idempotency_persistence_path
        if path is None or not path.exists():
            self._delivery_idempotency_persistence_pending = len(self._delivery_idempotency_cache)
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            bind_event("channel.delivery").warning("delivery idempotency journal read failed path={} error={}", path, exc)
            self._delivery_idempotency_persistence_pending = len(self._delivery_idempotency_cache)
            return {}

        items = raw.get("items", []) if isinstance(raw, dict) else []
        current = time.time()
        restored: dict[str, float] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", "") or "").strip()
            if not key:
                continue
            try:
                expiry = float(item.get("expires_at_epoch", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
            if expiry <= current:
                continue
            prior = float(restored.get(key, 0.0) or 0.0)
            restored[key] = max(prior, expiry)
        self._delivery_idempotency_persistence_pending = len(restored)
        return restored

    def _write_delivery_idempotency_persistence_locked(self) -> None:
        path = self._delivery_idempotency_persistence_path
        if path is None:
            self._delivery_idempotency_persistence_pending = len(self._delivery_idempotency_cache)
            return
        self._prune_delivery_idempotency_cache()
        self._delivery_idempotency_persistence_pending = len(self._delivery_idempotency_cache)
        if not self._delivery_idempotency_cache:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        items = [
            {"key": key, "expires_at_epoch": float(expiry)}
            for key, expiry in sorted(self._delivery_idempotency_cache.items(), key=lambda item: item[1])
        ]
        payload = {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "items": items,
        }
        tmp_path = path.with_name(f"{path.name}.tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True), encoding="utf-8")
        tmp_path.replace(path)

    async def _sync_delivery_idempotency_persistence(self) -> None:
        if self._delivery_idempotency_persistence_path is None:
            self._delivery_idempotency_persistence_pending = len(self._delivery_idempotency_cache)
            return
        async with self._delivery_idempotency_persistence_lock:
            self._write_delivery_idempotency_persistence_locked()

    async def _restore_delivery_idempotency_persistence(self) -> int:
        if self._delivery_idempotency_persistence_path is None:
            self._delivery_idempotency_persistence_pending = len(self._delivery_idempotency_cache)
            return 0
        async with self._delivery_idempotency_persistence_lock:
            restored = self._load_delivery_idempotency_persistence_locked()
            if not restored:
                self._write_delivery_idempotency_persistence_locked()
                return 0
            current = time.time()
            self._prune_delivery_idempotency_cache(now=current)
            merged = dict(self._delivery_idempotency_cache)
            for key, expiry in restored.items():
                prior = float(merged.get(key, 0.0) or 0.0)
                merged[key] = max(prior, float(expiry))
            ordered = sorted(merged.items(), key=lambda item: item[1])
            self._delivery_idempotency_cache = dict(ordered)
            self._delivery_idempotency_order = deque(ordered)
            self._prune_delivery_idempotency_cache(now=current)
            restored_count = len(restored)
            self._write_delivery_idempotency_persistence_locked()
            bind_event("channel.delivery").info(
                "delivery idempotency journal restored path={} restored={}",
                self._delivery_idempotency_persistence_path,
                restored_count,
            )
            return restored_count

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

    @staticmethod
    def _serialize_inbound_event(event: InboundEvent) -> dict[str, Any]:
        payload = {
            "channel": str(event.channel),
            "session_id": str(event.session_id),
            "user_id": str(event.user_id),
            "text": str(event.text),
            "metadata": dict(event.metadata) if isinstance(event.metadata, dict) else {},
            "created_at": str(getattr(event, "created_at", "") or ""),
        }
        return json.loads(json.dumps(payload, ensure_ascii=True, default=str))

    @staticmethod
    def _inbound_record_key(event: InboundEvent) -> str:
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        explicit = str(metadata.get("_inbound_idempotency_key", "") or "").strip()
        if explicit:
            return explicit
        payload = "\n".join(
            [
                str(event.channel),
                str(event.session_id),
                str(event.user_id),
                str(event.text),
                json.dumps(metadata, ensure_ascii=True, sort_keys=True, default=str),
                str(getattr(event, "created_at", "") or ""),
            ]
        )
        return f"inb:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"

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
            "restored_idempotency_keys": 0,
            "restored": 0,
            "replayed": 0,
            "failed": 0,
            "skipped": 0,
            "suppressed": 0,
            "remaining": int(self.bus.stats().get("dead_letter_size", 0) or 0),
            "last_error": "",
            "replayed_by_channel": {},
            "failed_by_channel": {},
            "skipped_by_channel": {},
            "suppressed_by_channel": {},
        }
        self._delivery_startup_replay = dict(summary)
        try:
            summary["restored_idempotency_keys"] = await self._restore_delivery_idempotency_persistence()
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
                    "suppressed",
                    "remaining",
                    "replayed_by_channel",
                    "failed_by_channel",
                    "skipped_by_channel",
                    "suppressed_by_channel",
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

    async def operator_replay_dead_letters(
        self,
        *,
        limit: int = 50,
        channel: str = "",
        reason: str = "",
        session_id: str = "",
        reasons: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "running": True,
            "last_at": datetime.now(timezone.utc).isoformat(),
            "last_error": "",
            "restored": 0,
            "restored_idempotency_keys": 0,
            "scanned": 0,
            "matched": 0,
            "replayed": 0,
            "failed": 0,
            "skipped": 0,
            "suppressed": 0,
            "remaining": int(self.bus.stats().get("dead_letter_size", 0) or 0),
            "replayed_by_channel": {},
            "failed_by_channel": {},
            "skipped_by_channel": {},
            "suppressed_by_channel": {},
        }
        self._delivery_manual_replay = dict(summary)
        try:
            summary["restored_idempotency_keys"] = await self._restore_delivery_idempotency_persistence()
            summary["restored"] = await self._restore_persisted_dead_letters()
            replay = await self.replay_dead_letters(
                limit=limit,
                channel=channel,
                reason=reason,
                session_id=session_id,
                reasons=reasons,
                dry_run=False,
            )
            for key, value in replay.items():
                summary[key] = value
        except Exception as exc:
            summary["last_error"] = str(exc)
            bind_event("channel.delivery").warning("manual dead-letter replay failed error={}", exc)
            raise
        finally:
            summary["running"] = False
            self._delivery_manual_replay = dict(summary)
        return dict(summary)

    def _load_inbound_persistence_locked(self) -> list[InboundEvent]:
        path = self._inbound_persistence_path
        if path is None or not path.exists():
            self._inbound_persistence_pending = 0
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            bind_event("channel.inbound").warning("inbound journal read failed path={} error={}", path, exc)
            self._inbound_persistence_pending = 0
            return []

        items = raw.get("items", []) if isinstance(raw, dict) else []
        events: list[InboundEvent] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            metadata_raw = item.get("metadata", {})
            metadata = dict(metadata_raw) if isinstance(metadata_raw, dict) else {}
            event = InboundEvent(
                channel=str(item.get("channel", "") or "").strip(),
                session_id=str(item.get("session_id", "") or "").strip(),
                user_id=str(item.get("user_id", "") or "").strip(),
                text=str(item.get("text", "") or ""),
                metadata=metadata,
                created_at=str(item.get("created_at", "") or ""),
            )
            if not event.channel or not event.session_id or not event.user_id:
                continue
            events.append(event)
        events.sort(key=lambda row: str(getattr(row, "created_at", "") or ""))
        self._inbound_persistence_pending = len(events)
        return events

    def _write_inbound_persistence_locked(self, events: list[InboundEvent]) -> None:
        path = self._inbound_persistence_path
        if path is None:
            self._inbound_persistence_pending = 0
            return
        self._inbound_persistence_pending = len(events)
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
            "items": [self._serialize_inbound_event(event) for event in events],
        }
        tmp_path = path.with_name(f"{path.name}.tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True), encoding="utf-8")
        tmp_path.replace(path)

    async def _persist_pending_inbound(self, event: InboundEvent) -> None:
        if self._inbound_persistence_path is None:
            return
        key = self._inbound_record_key(event)
        async with self._inbound_persistence_lock:
            events = self._load_inbound_persistence_locked()
            kept = [row for row in events if self._inbound_record_key(row) != key]
            kept.append(event)
            kept.sort(key=lambda row: str(getattr(row, "created_at", "") or ""))
            self._write_inbound_persistence_locked(kept)

    async def _clear_persisted_inbound(self, event: InboundEvent) -> None:
        if self._inbound_persistence_path is None:
            return
        key = self._inbound_record_key(event)
        async with self._inbound_persistence_lock:
            events = self._load_inbound_persistence_locked()
            kept = [row for row in events if self._inbound_record_key(row) != key]
            self._write_inbound_persistence_locked(kept)

    async def _restore_persisted_inbound(self) -> tuple[int, dict[str, int]]:
        if self._inbound_persistence_path is None:
            self._inbound_persistence_pending = 0
            return (0, {})
        if int(self.bus.stats().get("inbound_size", 0) or 0) > 0:
            async with self._inbound_persistence_lock:
                self._load_inbound_persistence_locked()
            return (0, {})
        async with self._inbound_persistence_lock:
            events = self._load_inbound_persistence_locked()
        if not events:
            return (0, {})
        replay_budget = max(0, int(self._inbound_replay_limit or 0))
        if replay_budget <= 0:
            return (0, {})
        restored = 0
        replayed_by_channel: dict[str, int] = {}
        for event in events[:replay_budget]:
            await self.bus.publish_inbound(event)
            restored += 1
            replayed_by_channel[event.channel] = replayed_by_channel.get(event.channel, 0) + 1
        bind_event("channel.inbound").info(
            "inbound journal restored path={} restored={}",
            self._inbound_persistence_path,
            restored,
        )
        return (restored, dict(sorted(replayed_by_channel.items())))

    async def _run_startup_inbound_replay(self) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "enabled": bool(self._inbound_replay_on_startup),
            "running": True,
            "path": str(self._inbound_persistence_path) if self._inbound_persistence_path is not None else "",
            "restored": 0,
            "replayed": 0,
            "remaining": 0,
            "last_error": "",
            "replayed_by_channel": {},
        }
        self._inbound_startup_replay = dict(summary)
        try:
            if self._inbound_replay_on_startup:
                restored, replayed_by_channel = await self._restore_persisted_inbound()
                summary["restored"] = restored
                summary["replayed"] = restored
                summary["replayed_by_channel"] = replayed_by_channel
            async with self._inbound_persistence_lock:
                self._load_inbound_persistence_locked()
            summary["remaining"] = int(self._inbound_persistence_pending)
        except Exception as exc:
            summary["last_error"] = str(exc)
            bind_event("channel.inbound").warning("startup inbound replay failed error={}", exc)
        summary["running"] = False
        self._inbound_startup_replay = dict(summary)
        return dict(summary)

    def startup_inbound_replay_status(self) -> dict[str, Any]:
        return dict(self._inbound_startup_replay)

    async def operator_replay_inbound(
        self,
        *,
        limit: int = 100,
        channel: str = "",
        session_id: str = "",
        force: bool = False,
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "running": True,
            "last_at": datetime.now(timezone.utc).isoformat(),
            "last_error": "",
            "restored": 0,
            "replayed": 0,
            "remaining": int(self._inbound_persistence_pending),
            "skipped_busy": 0,
            "replayed_by_channel": {},
        }
        self._inbound_manual_replay = dict(summary)

        try:
            channel_filter = str(channel or "").strip()
            session_filter = str(session_id or "").strip()
            async with self._inbound_persistence_lock:
                events = self._load_inbound_persistence_locked()

            if not events:
                summary["running"] = False
                self._inbound_manual_replay = dict(summary)
                return dict(summary)

            inbound_size = int(self.bus.stats().get("inbound_size", 0) or 0)
            if inbound_size > 0 and not force:
                summary["skipped_busy"] = inbound_size
                summary["remaining"] = int(self._inbound_persistence_pending)
                summary["running"] = False
                self._inbound_manual_replay = dict(summary)
                return dict(summary)

            bounded_limit = max(1, int(limit or 1))
            replay_budget = min(bounded_limit, max(0, int(self._inbound_replay_limit or 0) or bounded_limit))
            if replay_budget <= 0:
                summary["running"] = False
                self._inbound_manual_replay = dict(summary)
                return dict(summary)

            replayed_by_channel: dict[str, int] = {}
            restored = 0
            for event in events:
                if channel_filter and event.channel != channel_filter:
                    continue
                if session_filter and event.session_id != session_filter:
                    continue
                if restored >= replay_budget:
                    break
                await self.bus.publish_inbound(event)
                restored += 1
                replayed_by_channel[event.channel] = replayed_by_channel.get(event.channel, 0) + 1

            summary["restored"] = restored
            summary["replayed"] = restored
            summary["replayed_by_channel"] = dict(sorted(replayed_by_channel.items()))
            async with self._inbound_persistence_lock:
                self._load_inbound_persistence_locked()
            summary["remaining"] = int(self._inbound_persistence_pending)
            bind_event("channel.inbound").info(
                "manual inbound replay restored={} channel={} session_id={} force={}",
                restored,
                channel_filter,
                session_filter,
                force,
            )
        except Exception as exc:
            summary["last_error"] = str(exc)
            self._inbound_manual_replay = dict(summary)
            bind_event("channel.inbound").warning("manual inbound replay failed error={}", exc)
            raise

        summary["running"] = False
        self._inbound_manual_replay = dict(summary)
        return dict(summary)

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

    async def _recover_channel_detailed(self, channel_name: str, reason: str, *, force: bool = False) -> dict[str, Any]:
        normalized = str(channel_name or "").strip().lower()
        channel = self._channels.get(normalized)
        if channel is None:
            return {"channel": normalized, "status": "not_found", "reason": str(reason or "")}

        row = self._ensure_recovery_channel(normalized)
        now = time.monotonic()
        last_attempt = float(row.get("_last_attempt_monotonic", 0.0) or 0.0)
        if not force and self._recovery_cooldown_s > 0 and last_attempt > 0 and now < (last_attempt + self._recovery_cooldown_s):
            self._recovery_total["skipped_cooldown"] += 1
            row["skipped_cooldown"] = int(row.get("skipped_cooldown", 0) or 0) + 1
            return {"channel": normalized, "status": "skipped_cooldown", "reason": str(reason or "")}

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
            return {
                "channel": normalized,
                "status": "failed",
                "reason": str(reason or ""),
                "error": "channel_recovery_unregistered",
            }

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
            return {
                "channel": normalized,
                "status": "failed",
                "reason": str(reason or ""),
                "error": str(exc),
            }

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
        return {"channel": normalized, "status": "recovered", "reason": str(reason or "")}

    async def _recover_channel(self, channel_name: str, reason: str) -> bool:
        result = await self._recover_channel_detailed(channel_name, reason, force=False)
        return str(result.get("status", "")) == "recovered"

    async def operator_recover_channels(self, *, channel: str = "", force: bool = True) -> dict[str, Any]:
        normalized = str(channel or "").strip().lower()
        summary: dict[str, Any] = {
            "running": True,
            "last_at": datetime.now(timezone.utc).isoformat(),
            "last_error": "",
            "attempted": 0,
            "recovered": 0,
            "failed": 0,
            "skipped_healthy": 0,
            "skipped_cooldown": 0,
            "not_found": 0,
            "forced": bool(force),
            "channels": [],
        }
        self._operator_recovery = dict(summary)

        try:
            if normalized:
                names = [normalized]
            else:
                names = sorted(self._channels.keys())

            for name in names:
                current = self._channels.get(name)
                if current is None:
                    summary["not_found"] += 1
                    summary["channels"].append({"channel": name, "status": "not_found"})
                    continue

                health = current.health()
                task_state, task_error = self._channel_worker_state(current)
                if not normalized and health.running and task_state == "running":
                    summary["skipped_healthy"] += 1
                    summary["channels"].append(
                        {"channel": name, "status": "skipped_healthy", "reason": "already_running"}
                    )
                    continue

                summary["attempted"] += 1
                reason = "operator_recover_all"
                if normalized:
                    reason = "operator_recover_channel"
                elif not health.running:
                    reason = "operator_recover_channel_stopped"
                elif task_state != "running":
                    reason = f"operator_recover_worker_{task_state}"
                    if task_error:
                        reason = f"{reason}:{task_error}"

                result = await self._recover_channel_detailed(name, reason, force=force)
                status = str(result.get("status", "") or "")
                if status == "recovered":
                    summary["recovered"] += 1
                elif status == "skipped_cooldown":
                    summary["skipped_cooldown"] += 1
                elif status == "not_found":
                    summary["not_found"] += 1
                else:
                    summary["failed"] += 1
                summary["channels"].append(result)
        except Exception as exc:
            summary["last_error"] = str(exc)
            self._operator_recovery = dict(summary)
            bind_event("channel.recovery").warning("operator channel recovery failed error={}", exc)
            raise

        summary["running"] = False
        self._operator_recovery = dict(summary)
        return dict(summary)

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

    async def start_dispatcher_loop(self) -> None:
        task_state, _ = self._background_task_state(self._dispatcher_task)
        if task_state == "running":
            return
        self._dispatcher_task = asyncio.create_task(self._dispatch_loop())
        bind_event("channel.lifecycle").info("channel dispatcher started")

    async def start_recovery_supervisor(self) -> None:
        task_state, _ = self._background_task_state(self._recovery_task)
        if task_state == "running":
            return
        self._recovery_task = asyncio.create_task(self._recovery_loop())
        bind_event("channel.lifecycle").info(
            "channel recovery supervisor started enabled={} interval_s={} cooldown_s={}",
            self._recovery_enabled,
            self._recovery_interval_s,
            self._recovery_cooldown_s,
        )

    def register(self, name: str, channel_cls: type[BaseChannel]) -> None:
        self._registry[name] = channel_cls

    def set_inbound_interceptor(self, handler: Callable[[InboundEvent], Awaitable[bool]] | None) -> None:
        self._inbound_interceptor = handler

    async def _on_channel_message(self, session_id: str, user_id: str, text: str, metadata: dict[str, Any]) -> None:
        channel = str(metadata.get("channel", "")).strip() or session_id.split(":", 1)[0]
        event = InboundEvent(
            channel=channel,
            session_id=session_id,
            user_id=user_id,
            text=text,
            metadata=metadata,
        )
        interceptor = self._inbound_interceptor
        if interceptor is not None:
            try:
                handled = bool(await interceptor(event))
            except Exception as exc:
                bind_event("channel.inbound", session=session_id, channel=channel).warning(
                    "inbound interceptor failed error={}",
                    exc,
                )
                handled = False
            if handled:
                return
        await self._persist_pending_inbound(event)
        bind_event("channel.inbound", session=session_id, channel=channel).debug("inbound message queued user={} chars={}", user_id, len(text))
        await self.bus.publish_inbound(event)

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
                if ":thread:" in payload:
                    chat_id, _, thread_id = payload.partition(":thread:")
                    thread = thread_id.strip()
                    return f"{chat_id.strip()}:{thread}" if thread else chat_id.strip()
                return payload
            if raw.startswith("tg_"):
                raw = raw[3:]
                if ":topic:" in raw:
                    chat_id, _, thread_id = raw.partition(":topic:")
                    thread = thread_id.strip()
                    return f"{chat_id.strip()}:{thread}" if thread else chat_id.strip()
                if ":thread:" in raw:
                    chat_id, _, thread_id = raw.partition(":thread:")
                    thread = thread_id.strip()
                    return f"{chat_id.strip()}:{thread}" if thread else chat_id.strip()
                return raw.strip()
        if channel_name == "discord":
            if raw.startswith("discord:dm:"):
                payload = raw[len("discord:dm:") :].strip()
                if payload.endswith(":slash"):
                    payload = payload[: -len(":slash")].strip()
                return f"user:{payload}" if payload else ""
            if raw.startswith("discord:guild:"):
                payload = raw[len("discord:guild:") :].strip()
                if ":channel:" in payload:
                    _, _, channel_payload = payload.partition(":channel:")
                    if ":slash:" in channel_payload:
                        channel_payload, _, _ = channel_payload.partition(":slash:")
                    if ":thread:" in channel_payload:
                        _, _, thread_id = channel_payload.partition(":thread:")
                        thread = thread_id.strip()
                        return f"channel:{thread}" if thread else ""
                    clean_channel = channel_payload.strip()
                    return f"channel:{clean_channel}" if clean_channel else ""
            if raw.startswith("discord:channel:"):
                payload = raw[len("discord:channel:") :].strip()
                return f"channel:{payload}" if payload else ""
            if raw.startswith("discord:thread:"):
                payload = raw[len("discord:thread:") :].strip()
                return f"channel:{payload}" if payload else ""
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
                send_result = await channel.send(
                    target=event.target,
                    text=event.text,
                    metadata=self._prepare_outbound_metadata(
                        channel_name=event.channel,
                        target=event.target,
                        metadata=event.metadata,
                    ),
                )
                self._inc_delivery(channel=event.channel, key="success")
                self._inc_delivery(channel=event.channel, key="delivery_confirmed")
                self._remember_delivery_idempotency(idempotency_key)
                await self._sync_delivery_idempotency_persistence()
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
        suppressed = 0
        replayed_by_channel: dict[str, int] = {}
        failed_by_channel: dict[str, int] = {}
        skipped_by_channel: dict[str, int] = {}
        suppressed_by_channel: dict[str, int] = {}
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
            suppressed_before = int(self._delivery_total.get("idempotency_suppressed", 0) or 0)
            delivered = await self._publish_and_send(event=replay_event)
            suppressed_delta = int(self._delivery_total.get("idempotency_suppressed", 0) or 0) - suppressed_before
            if suppressed_delta > 0:
                suppressed += 1
                suppressed_by_channel[pending.channel] = suppressed_by_channel.get(pending.channel, 0) + 1
                continue
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
            "suppressed": suppressed,
            "kept": remaining,
            "dropped": 0,
            "remaining": remaining,
            "replayed_by_channel": dict(sorted(replayed_by_channel.items())),
            "failed_by_channel": dict(sorted(failed_by_channel.items())),
            "skipped_by_channel": dict(sorted(skipped_by_channel.items())),
            "suppressed_by_channel": dict(sorted(suppressed_by_channel.items())),
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
                "idempotency": {
                    "enabled": self._delivery_idempotency_persistence_path is not None,
                    "path": (
                        str(self._delivery_idempotency_persistence_path)
                        if self._delivery_idempotency_persistence_path is not None
                        else ""
                    ),
                    "active": int(self._delivery_idempotency_persistence_pending),
                },
                "startup_replay": dict(self._delivery_startup_replay),
                "manual_replay": dict(self._delivery_manual_replay),
            },
        }

    def dispatcher_diagnostics(self) -> dict[str, Any]:
        task_state, task_error = self._background_task_state(self._dispatcher_task)
        active_tasks = sum(len(tasks) for tasks in self._active_tasks.values())
        active_sessions = sum(1 for tasks in self._active_tasks.values() if tasks)
        return {
            "enabled": True,
            "running": bool(task_state == "running"),
            "task_state": task_state,
            "last_error": task_error,
            "max_concurrency": int(self._dispatcher_max_concurrency),
            "max_per_session": int(self._dispatcher_max_per_session),
            "session_slots_max_entries": int(self._session_slots_max_entries),
            "session_slots": int(len(self._session_slots)),
            "active_tasks": int(active_tasks),
            "active_sessions": int(active_sessions),
        }

    def inbound_diagnostics(self) -> dict[str, Any]:
        return {
            "persistence": {
                "enabled": self._inbound_persistence_path is not None,
                "path": str(self._inbound_persistence_path) if self._inbound_persistence_path is not None else "",
                "pending": int(self._inbound_persistence_pending),
                "startup_replay": dict(self._inbound_startup_replay),
                "manual_replay": dict(self._inbound_manual_replay),
            }
        }

    def recovery_diagnostics(self) -> dict[str, Any]:
        task_state, task_error = self._background_task_state(self._recovery_task)
        per_channel: dict[str, dict[str, Any]] = {}
        for name, row in sorted(self._recovery_per_channel.items()):
            clean_row = dict(row)
            clean_row.pop("_last_attempt_monotonic", None)
            per_channel[name] = clean_row
        return {
            "enabled": bool(self._recovery_enabled),
            "running": bool(task_state == "running"),
            "task_state": task_state,
            "last_error": task_error,
            "interval_s": float(self._recovery_interval_s),
            "cooldown_s": float(self._recovery_cooldown_s),
            "total": dict(self._recovery_total),
            "operator": dict(self._operator_recovery),
            "per_channel": per_channel,
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
        response_metadata = self._response_metadata_from_event(event)
        reply_metadata = self._reply_metadata_from_event(event)
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
                }
                | response_metadata
                | reply_metadata,
            )
        )

    async def _dispatch_event(self, event: InboundEvent) -> None:
        bind_event("channel.dispatch", session=event.session_id, channel=event.channel).debug("dispatch processing target={}", event.user_id)
        target = self._target_from_event(event)
        response_metadata = self._response_metadata_from_event(event)
        reply_metadata = self._reply_metadata_from_event(event)
        activity_channel, activity_chat_id, activity_thread_id = self._dispatch_typing_context(event)
        if activity_channel is not None and activity_chat_id:
            self._start_dispatch_typing(
                channel=activity_channel,
                chat_id=activity_chat_id,
                message_thread_id=activity_thread_id,
            )

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
                    metadata=metadata | response_metadata | reply_metadata,
                )
            )

        dispatch_token = self._dispatch_context.set(
            {
                "session_id": event.session_id,
                "channel": event.channel,
                "target": target,
                "response_metadata": dict(response_metadata),
                "sent_targets": set(),
                "reply_targets": set(),
            }
        )
        suppress_final_reply = False
        try:
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
                        }
                        | response_metadata
                        | reply_metadata,
                    )
                )
                return
            finally:
                self.bus.clear_stop(event.session_id)
                dispatch_context = self._dispatch_context.get()
                sent_targets = (
                    dispatch_context.get("sent_targets", set())
                    if isinstance(dispatch_context, dict)
                    else set()
                )
                if (event.channel, target) in sent_targets:
                    suppress_final_reply = True
                if activity_channel is not None and activity_chat_id:
                    await self._stop_dispatch_typing(
                        channel=activity_channel,
                        chat_id=activity_chat_id,
                        message_thread_id=activity_thread_id,
                    )

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
                    metadata={"model": getattr(result, "model", "")}
                    | response_metadata
                    | reply_metadata,
                )
            )
        finally:
            self._dispatch_context.reset(dispatch_token)

    async def _dispatch_loop(self) -> None:
        while True:
            try:
                event = await self.bus.next_inbound()
                if self._is_stop_command(event.text):
                    await self._handle_stop(event)
                    await self._clear_persisted_inbound(event)
                    continue

                async def _dispatch_worker(current: InboundEvent) -> None:
                    acquired = False
                    completed = False
                    try:
                        await self._acquire_dispatch_slot(current.session_id)
                        acquired = True
                        await self._dispatch_event(current)
                        completed = True
                    finally:
                        if completed:
                            await self._clear_persisted_inbound(current)
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
        idempotency_persistence_path_raw = channels_cfg.get(
            "delivery_idempotency_persistence_path",
            channels_cfg.get("deliveryIdempotencyPersistencePath", ""),
        )
        persistence_path_raw = channels_cfg.get(
            "delivery_persistence_path",
            channels_cfg.get("deliveryPersistencePath", ""),
        )
        state_path_raw = str(config.get("state_path", "") or "").strip()
        state_root = Path(state_path_raw).expanduser() if state_path_raw else None
        if idempotency_persistence_path_raw:
            self._delivery_idempotency_persistence_path = Path(str(idempotency_persistence_path_raw)).expanduser()
        elif state_root is not None:
            self._delivery_idempotency_persistence_path = state_root / "channels" / "delivery-idempotency.json"
        else:
            self._delivery_idempotency_persistence_path = None
        if persistence_path_raw:
            self._delivery_persistence_path = Path(str(persistence_path_raw)).expanduser()
        else:
            if state_root is not None:
                self._delivery_persistence_path = state_root / "channels" / "delivery-dead-letters.json"
            else:
                self._delivery_persistence_path = None
        inbound_replay_on_startup_raw = channels_cfg.get(
            "replay_inbound_on_startup",
            channels_cfg.get("replayInboundOnStartup", True),
        )
        self._inbound_replay_on_startup = bool(inbound_replay_on_startup_raw)
        inbound_replay_limit_raw = channels_cfg.get("replay_inbound_limit", channels_cfg.get("replayInboundLimit", 100))
        try:
            self._inbound_replay_limit = max(0, int(inbound_replay_limit_raw or 100))
        except (TypeError, ValueError):
            self._inbound_replay_limit = 100
        inbound_persistence_path_raw = channels_cfg.get(
            "inbound_persistence_path",
            channels_cfg.get("inboundPersistencePath", ""),
        )
        if inbound_persistence_path_raw:
            self._inbound_persistence_path = Path(str(inbound_persistence_path_raw)).expanduser()
        else:
            if state_root is not None:
                self._inbound_persistence_path = state_root / "channels" / "inbound-pending.json"
            else:
                self._inbound_persistence_path = None
        self._recovery_enabled = bool(channels_cfg.get("recovery_enabled", channels_cfg.get("recoveryEnabled", True)))
        recovery_interval_raw = channels_cfg.get("recovery_interval_s", channels_cfg.get("recoveryIntervalS", 15.0))
        self._recovery_interval_s = max(
            0.1,
            float(15.0 if recovery_interval_raw is None else recovery_interval_raw),
        )
        recovery_cooldown_raw = channels_cfg.get("recovery_cooldown_s", channels_cfg.get("recoveryCooldownS", 30.0))
        self._recovery_cooldown_s = max(
            0.0,
            float(30.0 if recovery_cooldown_raw is None else recovery_cooldown_raw),
        )
        self._prune_delivery_idempotency_cache()
        self._reset_dispatch_controls()
        self._delivery_startup_replay = {
            "enabled": bool(self._delivery_replay_on_startup),
            "running": False,
            "path": str(self._delivery_persistence_path) if self._delivery_persistence_path is not None else "",
            "restored_idempotency_keys": 0,
            "restored": 0,
            "replayed": 0,
            "failed": 0,
            "skipped": 0,
            "suppressed": 0,
            "remaining": int(self.bus.stats().get("dead_letter_size", 0) or 0),
            "last_error": "",
            "replayed_by_channel": {},
            "failed_by_channel": {},
            "skipped_by_channel": {},
            "suppressed_by_channel": {},
        }
        self._inbound_startup_replay = {
            "enabled": bool(self._inbound_replay_on_startup),
            "running": False,
            "path": str(self._inbound_persistence_path) if self._inbound_persistence_path is not None else "",
            "restored": 0,
            "replayed": 0,
            "remaining": 0,
            "last_error": "",
            "replayed_by_channel": {},
        }
        async with self._delivery_persistence_lock:
            self._load_delivery_persistence_locked()
        async with self._inbound_persistence_lock:
            self._load_inbound_persistence_locked()

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
            channel_config = dict(row)
            if (
                name == "discord"
                and state_root is not None
                and not str(
                    channel_config.get(
                        "thread_binding_state_path",
                        channel_config.get("threadBindingStatePath", ""),
                    )
                    or ""
                ).strip()
            ):
                channel_config["thread_binding_state_path"] = str(
                    state_root / "channels" / "discord-thread-bindings.json"
                )
            channel = cls(config=channel_config, on_message=self._on_channel_message)
            self._channels[name] = channel
            await channel.start()
            bind_event("channel.lifecycle", channel=name).info("channel started")

        await self.start_dispatcher_loop()
        await self.start_recovery_supervisor()

        await self._run_startup_delivery_replay()
        await self._run_startup_inbound_replay()

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
        payload_metadata = self._prepare_outbound_metadata(
            channel_name=str(channel),
            target=str(target),
            metadata=metadata or {},
        )
        response = await instance.send(target=target, text=text, metadata=payload_metadata)
        dispatch_context = self._dispatch_context.get()
        if isinstance(dispatch_context, dict):
            sent_targets = dispatch_context.get("sent_targets")
            if isinstance(sent_targets, set):
                sent_targets.add((str(channel), str(target)))
        return response

    def get_channel(self, name: str) -> BaseChannel | None:
        return self._channels.get(str(name or "").strip().lower())

    @staticmethod
    def _base_target_from_event(event: InboundEvent) -> str:
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        target = str(
            metadata.get("chat_id")
            or metadata.get("channel_id")
            or event.user_id
            or ""
        ).strip()
        return target

    @staticmethod
    def _normalize_reply_to_mode(raw: Any) -> str:
        mode = str(raw or "all").strip().lower()
        if mode not in {"off", "first", "all"}:
            return "all"
        return mode

    @staticmethod
    def _strip_reply_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        clean = dict(metadata)
        clean.pop("reply_to_message_id", None)
        clean.pop("message_reference_id", None)
        clean.pop("_reply_to_mode", None)
        return clean

    def _response_metadata_from_event(self, event: InboundEvent) -> dict[str, Any]:
        if str(event.channel or "").strip().lower() != "discord":
            return {}
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        interaction_id = str(metadata.get("interaction_id", "") or "").strip()
        interaction_token = str(metadata.get("interaction_token", "") or "").strip()
        if not interaction_id or not interaction_token:
            return {}
        response_metadata = {
            "interaction_id": interaction_id,
            "interaction_token": interaction_token,
        }
        if "discord_ephemeral" in metadata:
            response_metadata["discord_ephemeral"] = bool(metadata.get("discord_ephemeral"))
        if "ephemeral" in metadata:
            response_metadata["ephemeral"] = bool(metadata.get("ephemeral"))
        return response_metadata

    def _prepare_outbound_metadata(
        self,
        *,
        channel_name: str,
        target: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        prepared = dict(metadata or {})
        dispatch_context = self._dispatch_context.get()
        if isinstance(dispatch_context, dict):
            response_metadata = dispatch_context.get("response_metadata")
            if (
                str(dispatch_context.get("channel", "") or "").strip().lower()
                == str(channel_name or "").strip().lower()
                and str(dispatch_context.get("target", "") or "").strip() == str(target or "").strip()
                and isinstance(response_metadata, dict)
            ):
                for key, value in response_metadata.items():
                    prepared.setdefault(str(key), value)

        if str(channel_name or "").strip().lower() != "discord":
            return prepared

        reply_to_message_id = str(
            prepared.get("reply_to_message_id", prepared.get("message_reference_id", ""))
            or ""
        ).strip()
        if not reply_to_message_id:
            return prepared

        if str(prepared.get("interaction_token", "") or "").strip():
            return self._strip_reply_metadata(prepared)

        channel = self._channels.get("discord")
        mode = self._normalize_reply_to_mode(
            prepared.get("_reply_to_mode", getattr(channel, "reply_to_mode", "all"))
        )
        if mode == "off":
            return self._strip_reply_metadata(prepared)
        if mode == "all":
            return prepared

        if not isinstance(dispatch_context, dict):
            return prepared
        reply_targets = dispatch_context.get("reply_targets")
        if not isinstance(reply_targets, set):
            reply_targets = set()
            dispatch_context["reply_targets"] = reply_targets
        key = (str(channel_name), str(target))
        if key in reply_targets:
            return self._strip_reply_metadata(prepared)
        reply_targets.add(key)
        return prepared

    def _reply_metadata_from_event(self, event: InboundEvent) -> dict[str, Any]:
        if str(event.channel or "").strip().lower() != "discord":
            return {}
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        message_id = str(metadata.get("message_id", "") or "").strip()
        if not message_id:
            return {}
        channel = self._channels.get("discord")
        mode = self._normalize_reply_to_mode(getattr(channel, "reply_to_mode", "all"))
        if mode == "off":
            return {}
        return {"reply_to_message_id": message_id, "_reply_to_mode": mode}

    @staticmethod
    def _target_from_event(event: InboundEvent) -> str:
        target = ChannelManager._base_target_from_event(event)
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

    def _dispatch_typing_context(
        self,
        event: InboundEvent,
    ) -> tuple[BaseChannel | None, str, int | None]:
        channel = self._channels.get(event.channel)
        if channel is None:
            return None, "", None
        if not callable(getattr(channel, "_start_typing_keepalive", None)):
            return None, "", None
        if not callable(getattr(channel, "_stop_typing_keepalive", None)):
            return None, "", None

        chat_id = self._base_target_from_event(event)
        if not chat_id:
            return None, "", None
        thread_raw = event.metadata.get("message_thread_id")
        try:
            thread_id = int(thread_raw)
        except (TypeError, ValueError):
            thread_id = None
        if thread_id is not None and thread_id <= 0:
            thread_id = None
        return channel, chat_id, thread_id

    @staticmethod
    def _start_dispatch_typing(
        *,
        channel: BaseChannel,
        chat_id: str,
        message_thread_id: int | None,
    ) -> None:
        start_fn = getattr(channel, "_start_typing_keepalive", None)
        if callable(start_fn):
            start_fn(chat_id=chat_id, message_thread_id=message_thread_id)

    @staticmethod
    async def _stop_dispatch_typing(
        *,
        channel: BaseChannel,
        chat_id: str,
        message_thread_id: int | None,
    ) -> None:
        stop_fn = getattr(channel, "_stop_typing_keepalive", None)
        if callable(stop_fn):
            await stop_fn(chat_id=chat_id, message_thread_id=message_thread_id)

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
