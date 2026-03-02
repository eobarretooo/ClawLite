from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from clawlite.bus.queue import MessageQueue
from clawlite.channels.base import BaseChannel, ChannelCapabilities
from clawlite.channels.manager import ChannelManager


@dataclass
class _Result:
    text: str
    model: str = "fake/model"


class FakeEngine:
    async def run(
        self,
        *,
        session_id: str,
        user_text: str,
        channel: str | None = None,
        chat_id: str | None = None,
        progress_hook=None,
        stop_event=None,
    ):
        return _Result(text=f"reply:{session_id}:{user_text}")

    def request_stop(self, session_id: str) -> bool:
        return True


class ProgressEngine(FakeEngine):
    async def run(
        self,
        *,
        session_id: str,
        user_text: str,
        channel: str | None = None,
        chat_id: str | None = None,
        progress_hook=None,
        stop_event=None,
    ):
        assert progress_hook is not None
        await progress_hook(SimpleNamespace(stage="loop", message="progress:planning", iteration=1, tool_name="", metadata={}))
        await progress_hook(SimpleNamespace(stage="tool", message="progress:using-tool", iteration=1, tool_name="search", metadata={}))
        return _Result(text=f"reply:{session_id}:{user_text}")


class ConcurrentEngine(FakeEngine):
    def __init__(self, *, delay_s: float = 0.1) -> None:
        self.delay_s = delay_s
        self.current = 0
        self.max_seen = 0
        self.lock = asyncio.Lock()

    async def run(
        self,
        *,
        session_id: str,
        user_text: str,
        channel: str | None = None,
        chat_id: str | None = None,
        progress_hook=None,
        stop_event=None,
    ):
        async with self.lock:
            self.current += 1
            self.max_seen = max(self.max_seen, self.current)
        await asyncio.sleep(self.delay_s)
        async with self.lock:
            self.current -= 1
        return _Result(text=f"reply:{session_id}:{user_text}")


class MessageToolEngine(FakeEngine):
    def __init__(self) -> None:
        self.manager: ChannelManager | None = None

    async def run(
        self,
        *,
        session_id: str,
        user_text: str,
        channel: str | None = None,
        chat_id: str | None = None,
        progress_hook=None,
        stop_event=None,
    ):
        assert self.manager is not None
        await self.manager.send(channel=str(channel or "fake"), target=str(chat_id or ""), text="tool:sent")
        return _Result(text=f"reply:{session_id}:{user_text}")


class FakeChannel(BaseChannel):
    def __init__(
        self,
        *,
        config: dict[str, Any],
        on_message=None,
    ):
        capabilities = ChannelCapabilities(
            supports_progress=bool(config.get("supports_progress", True)),
            supports_tool_hints=bool(config.get("supports_tool_hints", True)),
            supports_retry=bool(config.get("supports_retry", True)),
        )
        super().__init__(name="fake", config=config, on_message=on_message, capabilities=capabilities)
        self.sent: list[tuple[str, str, dict[str, Any]]] = []
        self.fail_first_n = max(0, int(config.get("fail_first_n", 0) or 0))
        self._send_attempts = 0

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send(self, *, target: str, text: str, metadata=None) -> str:
        self._send_attempts += 1
        if self._send_attempts <= self.fail_first_n:
            raise RuntimeError(f"send failure #{self._send_attempts}")
        payload = dict(metadata or {})
        self.sent.append((target, text, payload))
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


def test_channel_manager_progress_delivery_policy() -> None:
    async def _scenario() -> None:
        bus = MessageQueue()
        mgr = ChannelManager(bus=bus, engine=ProgressEngine())
        mgr.register("fake", FakeChannel)
        await mgr.start(
            {
                "channels": {
                    "send_progress": False,
                    "send_tool_hints": True,
                    "fake": {"enabled": True, "supports_progress": True, "supports_tool_hints": True},
                }
            }
        )

        fake = mgr._channels["fake"]
        await fake.emit(session_id="fake:2", user_id="u1", text="hello", metadata={"channel": "fake", "chat_id": "2"})
        await asyncio.sleep(0.1)

        sent_texts = [row[1] for row in fake.sent]
        assert "progress:planning" not in sent_texts
        assert "progress:using-tool" in sent_texts
        assert any(text.startswith("reply:fake:2:") for text in sent_texts)

        await mgr.stop()

    asyncio.run(_scenario())


def test_channel_manager_retries_and_dead_letters_failed_send() -> None:
    async def _scenario() -> None:
        bus = MessageQueue()
        mgr = ChannelManager(bus=bus, engine=FakeEngine())
        mgr.register("fake", FakeChannel)

        await mgr.start(
            {
                "channels": {
                    "send_max_attempts": 2,
                    "send_retry_backoff_s": 0.01,
                    "send_retry_max_backoff_s": 0.01,
                    "fake": {"enabled": True, "fail_first_n": 10},
                }
            }
        )

        fake = mgr._channels["fake"]
        await fake.emit(session_id="fake:3", user_id="u1", text="hello", metadata={"channel": "fake", "chat_id": "3"})
        await asyncio.sleep(0.2)

        assert fake.sent == []
        first = await asyncio.wait_for(bus.next_outbound(), timeout=1)
        second = await asyncio.wait_for(bus.next_outbound(), timeout=1)
        assert (first.attempt, first.max_attempts) == (1, 2)
        assert (second.attempt, second.max_attempts) == (2, 2)

        dead = await asyncio.wait_for(bus.next_dead_letter(), timeout=1)
        assert dead.dead_lettered is True
        assert dead.dead_letter_reason == "send_failed"
        assert dead.attempt == 2
        assert dead.channel == "fake"

        await mgr.stop()

    asyncio.run(_scenario())


def test_channel_manager_default_drops_progress_events() -> None:
    async def _scenario() -> None:
        bus = MessageQueue()
        mgr = ChannelManager(bus=bus, engine=ProgressEngine())
        mgr.register("fake", FakeChannel)
        await mgr.start({"channels": {"fake": {"enabled": True, "supports_progress": True, "supports_tool_hints": True}}})

        fake = mgr._channels["fake"]
        await fake.emit(session_id="fake:4", user_id="u1", text="hello", metadata={"channel": "fake", "chat_id": "4"})
        await asyncio.sleep(0.1)

        sent_texts = [row[1] for row in fake.sent]
        assert "progress:planning" not in sent_texts
        assert "progress:using-tool" not in sent_texts
        assert any(text.startswith("reply:fake:4:") for text in sent_texts)

        await mgr.stop()

    asyncio.run(_scenario())


def test_channel_manager_suppresses_final_reply_after_tool_message_same_target() -> None:
    async def _scenario() -> None:
        bus = MessageQueue()
        engine = MessageToolEngine()
        mgr = ChannelManager(bus=bus, engine=engine)
        engine.manager = mgr
        mgr.register("fake", FakeChannel)

        await mgr.start({"channels": {"fake": {"enabled": True}}})

        fake = mgr._channels["fake"]
        await fake.emit(session_id="fake:5", user_id="u1", text="hello", metadata={"channel": "fake", "chat_id": "5"})
        await asyncio.sleep(0.1)

        assert [text for _, text, _ in fake.sent] == ["tool:sent"]

        await mgr.stop()

    asyncio.run(_scenario())


def test_channel_manager_dispatch_concurrency_bound() -> None:
    async def _scenario() -> None:
        bus = MessageQueue()
        engine = ConcurrentEngine(delay_s=0.08)
        mgr = ChannelManager(bus=bus, engine=engine)
        mgr.register("fake", FakeChannel)

        await mgr.start(
            {
                "channels": {
                    "dispatcher_max_concurrency": 2,
                    "dispatcher_max_per_session": 2,
                    "fake": {"enabled": True},
                }
            }
        )

        fake = mgr._channels["fake"]
        for idx in range(6):
            await fake.emit(
                session_id=f"fake:{idx}",
                user_id="u1",
                text=f"hello-{idx}",
                metadata={"channel": "fake", "chat_id": str(idx)},
            )

        await asyncio.sleep(0.7)
        assert engine.max_seen <= 2

        await mgr.stop()

    asyncio.run(_scenario())
