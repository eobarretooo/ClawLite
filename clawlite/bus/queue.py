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
        self._topics: dict[str, list[asyncio.Queue[InboundEvent]]] = defaultdict(list)

    async def publish_inbound(self, event: InboundEvent) -> None:
        await self._inbound.put(event)
        for queue in self._topics.get(event.channel, []):
            await queue.put(event)

    async def publish_outbound(self, event: OutboundEvent) -> None:
        await self._outbound.put(event)

    async def next_inbound(self) -> InboundEvent:
        return await self._inbound.get()

    async def next_outbound(self) -> OutboundEvent:
        return await self._outbound.get()

    async def subscribe(self, channel: str) -> AsyncIterator[InboundEvent]:
        queue: asyncio.Queue[InboundEvent] = asyncio.Queue()
        self._topics[channel].append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._topics[channel].remove(queue)

    def stats(self) -> dict[str, int]:
        return {
            "inbound_size": self._inbound.qsize(),
            "outbound_size": self._outbound.qsize(),
            "topics": sum(len(v) for v in self._topics.values()),
        }
