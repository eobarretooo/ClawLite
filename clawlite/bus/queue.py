from __future__ import annotations

import asyncio
from collections import deque
from collections import defaultdict
from datetime import datetime, timezone
from time import monotonic
from typing import Any
from typing import AsyncIterator

from clawlite.bus.events import InboundEvent, OutboundEvent


DEFAULT_SUBSCRIBER_QUEUE_MAXSIZE = 256
DEFAULT_STOP_EVENT_TTL_S = 6 * 60 * 60


class MessageQueue:
    """Lightweight in-process message bus with topic subscriptions."""

    def __init__(
        self,
        maxsize: int = 1000,
        subscriber_queue_maxsize: int = DEFAULT_SUBSCRIBER_QUEUE_MAXSIZE,
        stop_event_ttl_s: float = DEFAULT_STOP_EVENT_TTL_S,
    ) -> None:
        self._inbound: asyncio.Queue[InboundEvent] = asyncio.Queue(maxsize=maxsize)
        self._outbound: asyncio.Queue[OutboundEvent] = asyncio.Queue(maxsize=maxsize)
        self._dead_letter: asyncio.Queue[OutboundEvent] = asyncio.Queue(maxsize=maxsize)
        self._topics: dict[str, list[asyncio.Queue[InboundEvent]]] = defaultdict(list)
        self._subscriber_queue_maxsize = max(1, int(subscriber_queue_maxsize or 1))
        self._outbound_created_at: deque[str] = deque()
        self._dead_letter_events: deque[OutboundEvent] = deque()
        self._stop_event_ttl_s = max(0.01, float(stop_event_ttl_s or 0.01))
        self._stop_events: dict[str, tuple[asyncio.Event, float]] = {}
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
    def _oldest_age_seconds(snapshot: list[str]) -> float | None:
        oldest: datetime | None = None
        for raw in snapshot:
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

        snapshot = list(self._dead_letter_events)
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
        for queue in tuple(self._topics.get(event.channel, ())):
            await queue.put(event)

    async def publish_outbound(self, event: OutboundEvent) -> None:
        try:
            self._outbound.put_nowait(event)
            self._outbound_created_at.append(str(event.created_at))
            self._outbound_enqueued += 1
        except asyncio.QueueFull:
            self._outbound_dropped += 1

    async def next_inbound(self) -> InboundEvent:
        return await self._inbound.get()

    async def next_outbound(self) -> OutboundEvent:
        event = await self._outbound.get()
        if self._outbound_created_at:
            self._outbound_created_at.popleft()
        return event

    async def publish_dead_letter(self, event: OutboundEvent) -> None:
        await self._enqueue_dead_letter(event)
        self._dead_letter_enqueued += 1
        reason = str(event.dead_letter_reason or "unknown")
        self._dead_letter_reason_counts[reason] += 1

    async def _enqueue_dead_letter(self, event: OutboundEvent) -> None:
        await self._dead_letter.put(event)
        self._dead_letter_events.append(event)

    def _dequeue_dead_letter_nowait(self) -> OutboundEvent:
        event = self._dead_letter.get_nowait()
        if self._dead_letter_events:
            self._dead_letter_events.popleft()
        return event

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
                dead = self._dequeue_dead_letter_nowait()
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
            await self._enqueue_dead_letter(dead)

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
        event = await self._dead_letter.get()
        if self._dead_letter_events:
            self._dead_letter_events.popleft()
        return event

    async def subscribe(self, channel: str) -> AsyncIterator[InboundEvent]:
        queue: asyncio.Queue[InboundEvent] = asyncio.Queue(maxsize=self._subscriber_queue_maxsize)
        self._topics[channel].append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._topics[channel].remove(queue)

    def _prune_stop_events(self) -> None:
        cutoff = monotonic() - self._stop_event_ttl_s
        stale = [session_id for session_id, (_, touched_at) in self._stop_events.items() if touched_at < cutoff]
        for session_id in stale:
            self._stop_events.pop(session_id, None)

    def stop_event(self, session_id: str) -> asyncio.Event:
        self._prune_stop_events()
        normalized = str(session_id or "").strip()
        if not normalized:
            return asyncio.Event()
        entry = self._stop_events.get(normalized)
        if entry is None:
            event = asyncio.Event()
        else:
            event = entry[0]
        self._stop_events[normalized] = (event, monotonic())
        return event

    def request_stop(self, session_id: str) -> bool:
        self._prune_stop_events()
        normalized = str(session_id or "").strip()
        if not normalized:
            return False
        event = self.stop_event(normalized)
        event.set()
        self._stop_events[normalized] = (event, monotonic())
        return True

    def clear_stop(self, session_id: str) -> None:
        self._prune_stop_events()
        normalized = str(session_id or "").strip()
        if not normalized:
            return
        entry = self._stop_events.pop(normalized, None)
        if entry is not None:
            entry[0].clear()

    def stats(self) -> dict[str, Any]:
        self._prune_stop_events()
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
        outbound_oldest_age_s = self._oldest_age_seconds(list(self._outbound_created_at))
        if outbound_oldest_age_s is not None:
            out["outbound_oldest_age_s"] = outbound_oldest_age_s
        dead_letter_oldest_age_s = self._oldest_age_seconds(
            [str(getattr(event, "created_at", "")) for event in self._dead_letter_events]
        )
        if dead_letter_oldest_age_s is not None:
            out["dead_letter_oldest_age_s"] = dead_letter_oldest_age_s
        return out
