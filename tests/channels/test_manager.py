from __future__ import annotations

import asyncio
from dataclasses import dataclass

from clawlite.bus.queue import MessageQueue
from clawlite.channels.base import BaseChannel
from clawlite.channels.manager import ChannelManager


@dataclass
class _Result:
    text: str
    model: str = "fake/model"


class FakeEngine:
    async def run(self, *, session_id: str, user_text: str, channel: str | None = None, chat_id: str | None = None):
        return _Result(text=f"reply:{session_id}:{user_text}")


class FakeChannel(BaseChannel):
    def __init__(self, *, config: dict, on_message=None):
        super().__init__(name="fake", config=config, on_message=on_message)
        self.sent: list[tuple[str, str]] = []

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send(self, *, target: str, text: str, metadata=None) -> str:
        self.sent.append((target, text))
        return "ok"



def test_channel_manager_dispatches_inbound_to_engine_and_send() -> None:
    async def _scenario() -> None:
        bus = MessageQueue()
        mgr = ChannelManager(bus=bus, engine=FakeEngine())
        mgr.register("fake", FakeChannel)

        await mgr.start({"channels": {"fake": {"enabled": True}}})

        fake = mgr._channels["fake"]
        await fake.emit(session_id="fake:1", user_id="u1", text="hello", metadata={"channel": "fake", "chat_id": "1"})

        await asyncio.sleep(0.1)
        assert fake.sent
        assert fake.sent[0][0] == "1"
        assert "reply:fake:1:hello" in fake.sent[0][1]

        await mgr.stop()

    asyncio.run(_scenario())
