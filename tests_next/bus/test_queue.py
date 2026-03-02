from __future__ import annotations

import asyncio

from clawlite.bus.events import InboundEvent, OutboundEvent
from clawlite.bus.queue import MessageQueue


def test_message_queue_inbound_outbound_roundtrip() -> None:
    async def _scenario() -> None:
        bus = MessageQueue()
        inbound = InboundEvent(channel="telegram", session_id="s1", user_id="u1", text="oi")
        outbound = OutboundEvent(channel="telegram", session_id="s1", target="u1", text="ola")
        await bus.publish_inbound(inbound)
        await bus.publish_outbound(outbound)

        got_in = await bus.next_inbound()
        got_out = await bus.next_outbound()

        assert got_in.text == "oi"
        assert got_out.text == "ola"
        assert bus.stats()["inbound_size"] == 0
        assert bus.stats()["outbound_size"] == 0

    asyncio.run(_scenario())


def test_message_queue_subscription() -> None:
    async def _scenario() -> None:
        bus = MessageQueue()

        async def _consume_once() -> str:
            async for item in bus.subscribe("telegram"):
                return item.text
            return ""

        task = asyncio.create_task(_consume_once())
        await asyncio.sleep(0)
        await bus.publish_inbound(InboundEvent(channel="telegram", session_id="s1", user_id="u1", text="hello"))
        got = await asyncio.wait_for(task, timeout=2)
        assert got == "hello"

    asyncio.run(_scenario())
