from __future__ import annotations

import asyncio
from collections import defaultdict, deque

from clawlite.bus.events import InboundEvent, OutboundEvent
from clawlite.bus.redis_queue import RedisMessageQueue


class _FakeRedisListClient:
    def __init__(self) -> None:
        self._items: dict[str, deque[str]] = defaultdict(deque)
        self._queues: dict[str, asyncio.Queue[str]] = defaultdict(asyncio.Queue)
        self.ping_calls = 0
        self.closed = False

    async def ping(self) -> bool:
        self.ping_calls += 1
        return True

    async def rpush(self, key: str, value: str) -> int:
        self._items[key].append(value)
        await self._queues[key].put(value)
        return len(self._items[key])

    async def blpop(self, key: str, timeout: int = 0):  # noqa: ARG002
        value = await self._queues[key].get()
        self._items[key].popleft()
        return (key, value)

    async def aclose(self) -> None:
        self.closed = True


def test_redis_message_queue_roundtrip_and_stats() -> None:
    async def _scenario() -> None:
        client = _FakeRedisListClient()
        bus = RedisMessageQueue(redis_url="redis://fake", client_factory=lambda _url: client)
        await bus.connect()

        inbound = InboundEvent(channel="telegram", session_id="s1", user_id="u1", text="oi")
        outbound = OutboundEvent(channel="telegram", session_id="s1", target="u1", text="ola")

        await bus.publish_inbound(inbound)
        await bus.publish_outbound(outbound)
        stats_after_publish = bus.stats()
        assert stats_after_publish["backend"] == "redis"
        assert stats_after_publish["redis_connected"] is True
        assert stats_after_publish["inbound_size"] == 1
        assert stats_after_publish["outbound_size"] == 1

        got_in = await bus.next_inbound()
        got_out = await bus.next_outbound()

        assert got_in.text == "oi"
        assert got_out.text == "ola"
        assert client.ping_calls == 1

        stats_after_consume = bus.stats()
        assert stats_after_consume["inbound_size"] == 0
        assert stats_after_consume["outbound_size"] == 0

        await bus.close()
        assert client.closed is True

    asyncio.run(_scenario())
