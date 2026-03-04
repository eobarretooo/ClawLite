from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from clawlite.bus.events import OutboundEvent
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


class BlockingEngine(FakeEngine):
    def __init__(self) -> None:
        self.started = asyncio.Event()

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
        self.started.set()
        assert stop_event is not None
        await stop_event.wait()
        return _Result(text=f"reply:{session_id}:{user_text}")


class ExceptionEngine(FakeEngine):
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
        raise RuntimeError("boom")


class SubagentStub:
    def __init__(self, cancelled: int) -> None:
        self.cancelled = cancelled
        self.calls: list[str] = []

    def cancel_session(self, session_id: str) -> int:
        self.calls.append(session_id)
        return self.cancelled


class StopAwareEngine(FakeEngine):
    def __init__(self, *, cancelled_subagents: int) -> None:
        self.subagents = SubagentStub(cancelled=cancelled_subagents)


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


class FakeChannelWithSignals(FakeChannel):
    def signals(self) -> dict[str, Any]:
        return {"foo": 1, "bar": 2}


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


def test_channel_manager_stop_is_responsive_when_slots_saturated() -> None:
    async def _scenario() -> None:
        bus = MessageQueue()
        engine = BlockingEngine()
        mgr = ChannelManager(bus=bus, engine=engine)
        mgr.register("fake", FakeChannel)

        await mgr.start(
            {
                "channels": {
                    "dispatcher_max_concurrency": 1,
                    "dispatcher_max_per_session": 1,
                    "fake": {"enabled": True},
                }
            }
        )

        fake = mgr._channels["fake"]
        await fake.emit(session_id="fake:sat", user_id="u1", text="first", metadata={"channel": "fake", "chat_id": "sat"})
        await asyncio.wait_for(engine.started.wait(), timeout=1)

        await fake.emit(session_id="fake:sat", user_id="u1", text="second", metadata={"channel": "fake", "chat_id": "sat"})
        await fake.emit(session_id="fake:sat", user_id="u1", text="/stop", metadata={"channel": "fake", "chat_id": "sat"})

        for _ in range(20):
            if any(text.startswith("Stopped ") for _, text, _ in fake.sent):
                break
            await asyncio.sleep(0.01)

        assert any(text.startswith("Stopped ") for _, text, _ in fake.sent)

        await mgr.stop()

    asyncio.run(_scenario())


def test_channel_manager_sends_fallback_when_engine_raises() -> None:
    async def _scenario() -> None:
        bus = MessageQueue()
        mgr = ChannelManager(bus=bus, engine=ExceptionEngine())
        mgr.register("fake", FakeChannel)
        await mgr.start({"channels": {"fake": {"enabled": True}}})

        fake = mgr._channels["fake"]
        await fake.emit(session_id="fake:err", user_id="u1", text="hello", metadata={"channel": "fake", "chat_id": "err"})
        await asyncio.sleep(0.1)

        assert len(fake.sent) == 1
        target, text, metadata = fake.sent[0]
        assert target == "err"
        assert text == "I hit an internal error while processing your request."
        assert metadata.get("_error") == "dispatch_engine_exception"
        assert metadata.get("error_type") == "RuntimeError"

        await mgr.stop()

    asyncio.run(_scenario())


def test_channel_manager_stop_reports_subagent_cancellations() -> None:
    async def _scenario() -> None:
        bus = MessageQueue()
        engine = StopAwareEngine(cancelled_subagents=3)
        mgr = ChannelManager(bus=bus, engine=engine)
        mgr.register("fake", FakeChannel)
        await mgr.start({"channels": {"fake": {"enabled": True}}})

        fake = mgr._channels["fake"]
        await fake.emit(session_id="fake:stop", user_id="u1", text="/stop", metadata={"channel": "fake", "chat_id": "stop"})
        await asyncio.sleep(0.1)

        assert len(fake.sent) == 1
        target, text, metadata = fake.sent[0]
        assert target == "stop"
        assert text == "Stopped 0 active task(s); cancelled 3 subagent run(s)."
        assert metadata.get("_control") == "stop"
        assert metadata.get("cancelled_tasks") == 0
        assert metadata.get("cancelled_subagents") == 3
        assert engine.subagents.calls == ["fake:stop"]

        await mgr.stop()

    asyncio.run(_scenario())


def test_channel_manager_send_outbound_uses_session_routing() -> None:
    async def _scenario() -> None:
        bus = MessageQueue()
        mgr = ChannelManager(bus=bus, engine=FakeEngine())
        mgr.register("fake", FakeChannel)
        await mgr.start({"channels": {"fake": {"enabled": True}}})

        out = await mgr.send_outbound(channel="fake", session_id="fake:42", text="hello")

        fake = mgr._channels["fake"]
        assert out == "ok"
        assert fake.sent == [("42", "hello", {})]

        await mgr.stop()

    asyncio.run(_scenario())


def test_channel_manager_dispatch_preserves_telegram_thread_target() -> None:
    async def _scenario() -> None:
        bus = MessageQueue()
        mgr = ChannelManager(bus=bus, engine=FakeEngine())
        mgr.register("telegram", FakeChannel)
        await mgr.start({"channels": {"telegram": {"enabled": True}}})

        telegram = mgr._channels["telegram"]
        await telegram.emit(
            session_id="telegram:42",
            user_id="u1",
            text="hello",
            metadata={"channel": "telegram", "chat_id": "42", "message_thread_id": 9},
        )
        await asyncio.sleep(0.1)

        assert telegram.sent
        assert telegram.sent[0][0] == "42:9"

        await mgr.stop()

    asyncio.run(_scenario())


def test_channel_manager_stop_preserves_telegram_thread_target() -> None:
    async def _scenario() -> None:
        bus = MessageQueue()
        mgr = ChannelManager(bus=bus, engine=StopAwareEngine(cancelled_subagents=0))
        mgr.register("telegram", FakeChannel)
        await mgr.start({"channels": {"telegram": {"enabled": True}}})

        telegram = mgr._channels["telegram"]
        await telegram.emit(
            session_id="telegram:42",
            user_id="u1",
            text="/stop",
            metadata={"channel": "telegram", "chat_id": "42", "message_thread_id": 7},
        )
        await asyncio.sleep(0.1)

        assert telegram.sent
        assert telegram.sent[0][0] == "42:7"
        assert telegram.sent[0][2].get("_control") == "stop"

        await mgr.stop()

    asyncio.run(_scenario())


def test_channel_manager_status_includes_channel_specific_signals() -> None:
    async def _scenario() -> None:
        bus = MessageQueue()
        mgr = ChannelManager(bus=bus, engine=FakeEngine())
        mgr.register("fake", FakeChannelWithSignals)
        await mgr.start({"channels": {"fake": {"enabled": True}}})

        status = mgr.status()
        assert status["fake"]["running"] is True
        assert status["fake"]["signals"] == {"foo": 1, "bar": 2}

        await mgr.stop()

    asyncio.run(_scenario())


def test_channel_manager_delivery_counters_track_success_failure_and_dead_letter() -> None:
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
        await fake.emit(session_id="fake:diag", user_id="u1", text="hello", metadata={"channel": "fake", "chat_id": "diag"})
        await asyncio.sleep(0.2)

        channel_delivery = mgr.status()["fake"]["delivery"]
        assert channel_delivery["attempts"] == 2
        assert channel_delivery["success"] == 0
        assert channel_delivery["failures"] == 2
        assert channel_delivery["dead_lettered"] == 1
        assert channel_delivery["delivery_confirmed"] == 0
        assert channel_delivery["delivery_failed_final"] == 1
        assert channel_delivery["idempotency_suppressed"] == 0

        diagnostics = mgr.delivery_diagnostics()
        assert diagnostics["total"]["attempts"] == 2
        assert diagnostics["total"]["failures"] == 2
        assert diagnostics["total"]["dead_lettered"] == 1
        assert diagnostics["total"]["delivery_confirmed"] == 0
        assert diagnostics["total"]["delivery_failed_final"] == 1
        assert diagnostics["total"]["idempotency_suppressed"] == 0
        assert diagnostics["per_channel"]["fake"]["dead_lettered"] == 1

        await mgr.stop()

    asyncio.run(_scenario())


def test_channel_manager_suppresses_duplicate_outbound_with_explicit_idempotency_key() -> None:
    async def _scenario() -> None:
        bus = MessageQueue()
        mgr = ChannelManager(bus=bus, engine=FakeEngine())
        mgr.register("fake", FakeChannel)
        await mgr.start(
            {
                "channels": {
                    "delivery_idempotency_ttl_s": 900,
                    "delivery_idempotency_max_entries": 32,
                    "fake": {"enabled": True},
                }
            }
        )

        fake = mgr._channels["fake"]
        key = "explicit-dedupe-key"
        first = OutboundEvent(
            channel="fake",
            session_id="fake:idem",
            target="idem",
            text="hello",
            metadata={"_delivery_idempotency_key": key},
        )
        second = OutboundEvent(
            channel="fake",
            session_id="fake:idem",
            target="idem",
            text="hello",
            metadata={"_delivery_idempotency_key": key},
        )

        await mgr._publish_and_send(event=first)
        await mgr._publish_and_send(event=second)

        assert len(fake.sent) == 1
        assert fake.sent[0][2]["_delivery_idempotency_key"] == key

        delivery = mgr.status()["fake"]["delivery"]
        assert delivery["attempts"] == 1
        assert delivery["success"] == 1
        assert delivery["delivery_confirmed"] == 1
        assert delivery["idempotency_suppressed"] == 1
        assert delivery["delivery_failed_final"] == 0

        diagnostics = mgr.delivery_diagnostics()
        assert diagnostics["total"]["idempotency_suppressed"] == 1
        assert diagnostics["total"]["delivery_confirmed"] == 1

        await mgr.stop()

    asyncio.run(_scenario())


def test_channel_manager_replay_dead_letters_updates_replay_counters() -> None:
    async def _scenario() -> None:
        bus = MessageQueue()
        mgr = ChannelManager(bus=bus, engine=FakeEngine())

        await bus.publish_dead_letter(
            OutboundEvent(
                channel="fake",
                session_id="s1",
                target="u1",
                text="dead",
                dead_lettered=True,
                dead_letter_reason="send_failed",
            )
        )
        await bus.publish_dead_letter(
            OutboundEvent(
                channel="telegram",
                session_id="s2",
                target="u2",
                text="dead2",
                dead_lettered=True,
                dead_letter_reason="send_failed",
            )
        )

        summary = await mgr.replay_dead_letters(limit=5, channel="fake", reason="send_failed", session_id="s1", dry_run=False)
        assert summary["matched"] == 1
        assert summary["replayed"] == 1
        assert summary["replayed_by_channel"] == {"fake": 1}

        diagnostics = mgr.delivery_diagnostics()
        assert diagnostics["total"]["replayed"] == 1
        assert diagnostics["per_channel"]["fake"]["replayed"] == 1
        assert "telegram" not in diagnostics["per_channel"]

    asyncio.run(_scenario())
