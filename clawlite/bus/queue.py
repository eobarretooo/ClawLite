from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from typing import AsyncIterator

from clawlite.bus.events import InboundEvent, OutboundEvent


class MessageQueue:
    """Lightweight in-process message bus with topic subscriptions."""

    def __init__(self, maxsize: int = 1000) -> None:
        self._inbound: asyncio.Queue[InboundEvent] = asyncio.Queue(maxsize=maxsize)
        self._outbound: asyncio.Queue[OutboundEvent] = asyncio.Queue(maxsize=maxsize)
        self._dead_letter: asyncio.Queue[OutboundEvent] = asyncio.Queue(maxsize=maxsize)
        self._topics: dict[str, list[asyncio.Queue[InboundEvent]]] = defaultdict(list)
        self._stop_events: dict[str, asyncio.Event] = {}
        self._inbound_published = 0
        self._outbound_enqueued = 0
        self._outbound_dropped = 0
        self._dead_letter_enqueued = 0
        self._dead_letter_replayed = 0
        self._dead_letter_replay_attempts = 0
        self._dead_letter_replay_skipped = 0
        self._dead_letter_replay_dropped = 0
        self._dead_letter_reason_counts: dict[str, int] = defaultdict(int)

    @staticmethod
    def _oldest_age_seconds(queue: asyncio.Queue[Any]) -> float | None:
        snapshot = list(getattr(queue, "_queue", []))
        oldest: datetime | None = None
        for item in snapshot:
            raw = getattr(item, "created_at", "")
            try:
                stamp = datetime.fromisoformat(str(raw))
            except Exception:
                continue
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            if oldest is None or stamp < oldest:
                oldest = stamp
        if oldest is None:
            return None
        age = (datetime.now(timezone.utc) - oldest).total_seconds()
        return max(0.0, age)

    def _dead_letter_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        bounded_limit = max(0, int(limit or 0))
        if bounded_limit == 0:
            return []

        snapshot = list(getattr(self._dead_letter, "_queue", []))
        indexed = list(enumerate(snapshot))
        indexed.sort(key=lambda item: (str(getattr(item[1], "created_at", "")), item[0]), reverse=True)

        recent: list[dict[str, Any]] = []
        for _, event in indexed[:bounded_limit]:
            metadata = getattr(event, "metadata", {})
            replayed = False
            if isinstance(metadata, dict):
                replayed = bool(metadata.get("_replayed_from_dead_letter", False))
            recent.append(
                {
                    "channel": str(getattr(event, "channel", "")),
                    "session_id": str(getattr(event, "session_id", "")),
                    "attempt": int(getattr(event, "attempt", 0) or 0),
                    "max_attempts": int(getattr(event, "max_attempts", 0) or 0),
                    "retryable": bool(getattr(event, "retryable", False)),
                    "dead_letter_reason": str(getattr(event, "dead_letter_reason", "")),
                    "last_error": str(getattr(event, "last_error", "")),
                    "created_at": str(getattr(event, "created_at", "")),
                    "replayed_from_dead_letter": replayed,
                }
            )
        return recent

    async def publish_inbound(self, event: InboundEvent) -> None:
        await self._inbound.put(event)
        self._inbound_published += 1
        for queue in self._topics.get(event.channel, []):
            await queue.put(event)

    async def publish_outbound(self, event: OutboundEvent) -> None:
        try:
            self._outbound.put_nowait(event)
            self._outbound_enqueued += 1
        except asyncio.QueueFull:
            self._outbound_dropped += 1

    async def next_inbound(self) -> InboundEvent:
        return await self._inbound.get()

    async def next_outbound(self) -> OutboundEvent:
        return await self._outbound.get()

    async def publish_dead_letter(self, event: OutboundEvent) -> None:
        await self._dead_letter.put(event)
        self._dead_letter_enqueued += 1
        reason = str(event.dead_letter_reason or "unknown")
        self._dead_letter_reason_counts[reason] += 1

    @staticmethod
    def _dead_letter_matches(
        event: OutboundEvent,
        *,
        channel: str,
        reason: str,
        session_id: str,
    ) -> bool:
        if channel and event.channel != channel:
            return False
        if reason and event.dead_letter_reason != reason:
            return False
        if session_id and event.session_id != session_id:
            return False
        return True

    async def replay_dead_letters(
        self,
        *,
        limit: int = 100,
        channel: str = "",
        reason: str = "",
        session_id: str = "",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        bounded_limit = max(0, int(limit or 0))
        replay_budget = bounded_limit
        channel_filter = str(channel or "").strip()
        reason_filter = str(reason or "").strip()
        session_filter = str(session_id or "").strip()

        scanned = 0
        matched = 0
        replayed = 0
        kept = 0
        dropped = 0
        replayed_by_channel: dict[str, int] = defaultdict(int)

        to_keep: list[OutboundEvent] = []
        size = self._dead_letter.qsize()
        for _ in range(size):
            try:
                dead = self._dead_letter.get_nowait()
            except asyncio.QueueEmpty:
                break
            scanned += 1
            if not self._dead_letter_matches(
                dead,
                channel=channel_filter,
                reason=reason_filter,
                session_id=session_filter,
            ):
                to_keep.append(dead)
                kept += 1
                continue

            matched += 1
            if dry_run or replay_budget <= 0:
                to_keep.append(dead)
                kept += 1
                self._dead_letter_replay_skipped += 1
                continue

            self._dead_letter_replay_attempts += 1
            metadata = dict(dead.metadata)
            metadata["_replayed_from_dead_letter"] = True
            replay_event = OutboundEvent(
                channel=dead.channel,
                session_id=dead.session_id,
                target=dead.target,
                text=dead.text,
                metadata=metadata,
                attempt=1,
                max_attempts=dead.max_attempts,
                retryable=dead.retryable,
                dead_lettered=False,
                dead_letter_reason="",
                last_error="",
            )
            before_dropped = self._outbound_dropped
            await self.publish_outbound(replay_event)
            if self._outbound_dropped > before_dropped:
                dropped += 1
                self._dead_letter_replay_dropped += 1
                to_keep.append(dead)
                kept += 1
                continue
            replay_budget -= 1
            replayed += 1
            self._dead_letter_replayed += 1
            replayed_by_channel[dead.channel] += 1

        for dead in to_keep:
            await self._dead_letter.put(dead)

        return {
            "scanned": scanned,
            "matched": matched,
            "replayed": replayed,
            "kept": kept,
            "dropped": dropped,
            "replayed_by_channel": dict(sorted(replayed_by_channel.items())),
            "dry_run": bool(dry_run),
            "limit": bounded_limit,
        }

    async def next_dead_letter(self) -> OutboundEvent:
        return await self._dead_letter.get()

    async def subscribe(self, channel: str) -> AsyncIterator[InboundEvent]:
        queue: asyncio.Queue[InboundEvent] = asyncio.Queue()
        self._topics[channel].append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._topics[channel].remove(queue)

    def stop_event(self, session_id: str) -> asyncio.Event:
        normalized = str(session_id or "").strip()
        if not normalized:
            return asyncio.Event()
        event = self._stop_events.get(normalized)
        if event is None:
            event = asyncio.Event()
            self._stop_events[normalized] = event
        return event

    def request_stop(self, session_id: str) -> bool:
        normalized = str(session_id or "").strip()
        if not normalized:
            return False
        self.stop_event(normalized).set()
        return True

    def clear_stop(self, session_id: str) -> None:
        normalized = str(session_id or "").strip()
        if not normalized:
            return
        event = self._stop_events.get(normalized)
        if event is not None:
            event.clear()
            if not event.is_set():
                self._stop_events.pop(normalized, None)

    def stats(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "inbound_size": self._inbound.qsize(),
            "inbound_published": self._inbound_published,
            "outbound_size": self._outbound.qsize(),
            "outbound_enqueued": self._outbound_enqueued,
            "outbound_dropped": self._outbound_dropped,
            "dead_letter_size": self._dead_letter.qsize(),
            "dead_letter_enqueued": self._dead_letter_enqueued,
            "dead_letter_replayed": self._dead_letter_replayed,
            "dead_letter_replay_attempts": self._dead_letter_replay_attempts,
            "dead_letter_replay_skipped": self._dead_letter_replay_skipped,
            "dead_letter_replay_dropped": self._dead_letter_replay_dropped,
            "dead_letter_reason_counts": dict(sorted(self._dead_letter_reason_counts.items())),
            "dead_letter_recent": self._dead_letter_recent(),
            "topics": sum(len(v) for v in self._topics.values()),
            "stop_sessions": len(self._stop_events),
        }
        outbound_oldest_age_s = self._oldest_age_seconds(self._outbound)
        if outbound_oldest_age_s is not None:
            out["outbound_oldest_age_s"] = outbound_oldest_age_s
        dead_letter_oldest_age_s = self._oldest_age_seconds(self._dead_letter)
        if dead_letter_oldest_age_s is not None:
            out["dead_letter_oldest_age_s"] = dead_letter_oldest_age_s
        return out
