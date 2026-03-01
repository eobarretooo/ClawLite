from __future__ import annotations

import asyncio

from clawlite.runtime.message_bus import InboundEnvelope, MessageBus, OutboundEnvelope


def test_message_bus_request_reply_roundtrip() -> None:
    async def _run() -> None:
        async def inbound_handler(env: InboundEnvelope) -> str:
            return f"{env.channel}:{env.session_id}:{env.text}".upper()

        async def outbound_handler(env: OutboundEnvelope) -> None:
            return None

        bus = MessageBus(inbound_handler=inbound_handler, outbound_handler=outbound_handler)
        reply = await bus.request_reply(channel="irc", session_id="irc_group_#ops", text="ping")
        assert reply == "IRC:IRC_GROUP_#OPS:PING"
        await bus.stop()

    asyncio.run(_run())


def test_message_bus_publish_outbound_dispatches() -> None:
    async def _run() -> None:
        seen: list[tuple[str, str, str, str]] = []

        async def inbound_handler(env: InboundEnvelope) -> str:
            return "ok"

        async def outbound_handler(env: OutboundEnvelope) -> None:
            seen.append((env.instance_key, env.channel, env.session_id, env.text))

        bus = MessageBus(inbound_handler=inbound_handler, outbound_handler=outbound_handler)
        await bus.publish_outbound(
            channel="telegram",
            session_id="tg_123",
            text="hello",
            instance_key="telegram",
        )

        timeout_at = asyncio.get_running_loop().time() + 1.0
        while not seen and asyncio.get_running_loop().time() < timeout_at:
            await asyncio.sleep(0.01)

        await bus.stop()
        assert seen == [("telegram", "telegram", "tg_123", "hello")]

    asyncio.run(_run())
