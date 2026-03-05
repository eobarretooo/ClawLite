from __future__ import annotations

import asyncio
import hashlib
import contextvars
import time
from collections import deque
from dataclasses import replace
from typing import Any

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

setup_logging()


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


class ChannelManager:
    """Owns channel lifecycle and bridges channels <-> bus <-> engine."""

    _ENGINE_ERROR_FALLBACK_TEXT = "I hit an internal error while processing your request."

    def __init__(self, *, bus: MessageQueue, engine: EngineProtocol) -> None:
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
        self._session_slots: dict[str, asyncio.Semaphore] = {}
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

    def _session_semaphore(self, session_id: str) -> asyncio.Semaphore:
        sem = self._session_slots.get(session_id)
        if sem is None:
            sem = asyncio.Semaphore(self._dispatcher_max_per_session)
            self._session_slots[session_id] = sem
        return sem

    async def _acquire_dispatch_slot(self, session_id: str) -> None:
        await self._dispatch_slots.acquire()
        session_sem = self._session_semaphore(session_id)
        try:
            await session_sem.acquire()
        except Exception:
            self._dispatch_slots.release()
            raise

    def _release_dispatch_slot(self, session_id: str) -> None:
        self._dispatch_slots.release()
        session_sem = self._session_slots.get(session_id)
        if session_sem is not None:
            session_sem.release()

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

    async def _publish_and_send(self, *, event: OutboundEvent) -> None:
        channel = self._channels.get(event.channel)
        if channel is None:
            self._inc_delivery(channel=event.channel, key="channel_unavailable")
            bind_event("channel.dispatch", session=event.session_id, channel=event.channel).error("channel unavailable")
            dead = replace(
                event,
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
            _, idempotency_key = self._ensure_delivery_idempotency_key(event)
            self._record_delivery_recent(
                event=dead,
                outcome="delivery_failed_final",
                idempotency_key=idempotency_key,
                dead_letter_reason=dead.dead_letter_reason,
                last_error=dead.last_error,
            )
            return
        if not self._delivery_allowed(channel=channel, event=event):
            self._inc_delivery(channel=event.channel, key="policy_dropped")
            bind_event("channel.send", session=event.session_id, channel=event.channel).debug(
                "dispatch dropped by delivery policy target={}",
                event.target,
            )
            return
        await self._retry_send(channel=channel, event=event)

    async def replay_dead_letters(
        self,
        *,
        limit: int = 100,
        channel: str = "",
        reason: str = "",
        session_id: str = "",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        summary = await self.bus.replay_dead_letters(
            limit=limit,
            channel=channel,
            reason=reason,
            session_id=session_id,
            dry_run=dry_run,
        )
        replayed_by_channel = summary.get("replayed_by_channel", {})
        if isinstance(replayed_by_channel, dict):
            for name, count in replayed_by_channel.items():
                try:
                    amount = int(count)
                except (TypeError, ValueError):
                    continue
                self._inc_delivery(channel=str(name), key="replayed", delta=amount)
        return summary

    def delivery_diagnostics(self) -> dict[str, Any]:
        return {
            "total": dict(self._delivery_total),
            "per_channel": {name: dict(row) for name, row in sorted(self._delivery_per_channel.items())},
            "recent": list(reversed(self._delivery_recent)),
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
        self._prune_delivery_idempotency_cache()
        self._reset_dispatch_controls()

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
            row: dict[str, Any] = {
                "running": ch.running,
                "last_error": ch.health().last_error,
                "delivery": dict(self._ensure_delivery_channel(name)),
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
