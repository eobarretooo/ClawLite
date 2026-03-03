from __future__ import annotations

import asyncio
from collections import defaultdict
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
        self._outbound_dropped = 0

    async def publish_inbound(self, event: InboundEvent) -> None:
        await self._inbound.put(event)
        for queue in self._topics.get(event.channel, []):
            await queue.put(event)

    async def publish_outbound(self, event: OutboundEvent) -> None:
        try:
            self._outbound.put_nowait(event)
        except asyncio.QueueFull:
            self._outbound_dropped += 1

    async def next_inbound(self) -> InboundEvent:
        return await self._inbound.get()

    async def next_outbound(self) -> OutboundEvent:
        return await self._outbound.get()

    async def publish_dead_letter(self, event: OutboundEvent) -> None:
        await self._dead_letter.put(event)

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

    def stats(self) -> dict[str, int]:
        return {
            "inbound_size": self._inbound.qsize(),
            "outbound_size": self._outbound.qsize(),
            "outbound_dropped": self._outbound_dropped,
            "dead_letter_size": self._dead_letter.qsize(),
            "topics": sum(len(v) for v in self._topics.values()),
            "stop_sessions": len(self._stop_events),
        }
