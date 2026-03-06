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


def test_message_queue_subscription_applies_backpressure_when_subscriber_queue_full() -> None:
    async def _scenario() -> None:
        bus = MessageQueue(subscriber_queue_maxsize=1)

        q1: asyncio.Queue[InboundEvent] = asyncio.Queue(maxsize=1)
        q2: asyncio.Queue[InboundEvent] = asyncio.Queue(maxsize=1)
        bus._topics["telegram"] = [q1, q2]

        await q1.put(InboundEvent(channel="telegram", session_id="seed", user_id="u0", text="seed"))
        await q2.put(InboundEvent(channel="telegram", session_id="seed", user_id="u0", text="seed"))

        blocked = asyncio.create_task(
            bus.publish_inbound(InboundEvent(channel="telegram", session_id="s1", user_id="u1", text="blocked"))
        )
        await asyncio.sleep(0)
        assert blocked.done() is False

        q1.get_nowait()
        q2.get_nowait()
        await asyncio.wait_for(blocked, timeout=1)

        delivered_1 = await asyncio.wait_for(q1.get(), timeout=1)
        delivered_2 = await asyncio.wait_for(q2.get(), timeout=1)
        assert delivered_1.text == "blocked"
        assert delivered_2.text == "blocked"

    asyncio.run(_scenario())


def test_message_queue_publish_inbound_uses_snapshot_when_topics_mutate() -> None:
    async def _scenario() -> None:
        bus = MessageQueue()
        q1: asyncio.Queue[InboundEvent] = asyncio.Queue(maxsize=1)
        q2: asyncio.Queue[InboundEvent] = asyncio.Queue(maxsize=1)
        bus._topics["telegram"] = [q1, q2]

        await q1.put(InboundEvent(channel="telegram", session_id="seed", user_id="u0", text="seed"))
        event = InboundEvent(channel="telegram", session_id="s1", user_id="u1", text="hello")

        publish_task = asyncio.create_task(bus.publish_inbound(event))
        await asyncio.sleep(0)

        bus._topics["telegram"].remove(q2)
        q1.get_nowait()
        await asyncio.wait_for(publish_task, timeout=1)

        delivered = await asyncio.wait_for(q2.get(), timeout=1)
        assert delivered.text == "hello"

    asyncio.run(_scenario())


def test_message_queue_dead_letter_roundtrip() -> None:
    async def _scenario() -> None:
        bus = MessageQueue()
        dead = OutboundEvent(
            channel="telegram",
            session_id="s1",
            target="u1",
            text="failed",
            dead_lettered=True,
            dead_letter_reason="send_failed",
        )
        await bus.publish_dead_letter(dead)
        got = await bus.next_dead_letter()
        assert got.dead_lettered is True
        assert got.dead_letter_reason == "send_failed"
        assert bus.stats()["dead_letter_size"] == 0

    asyncio.run(_scenario())


def test_message_queue_outbound_drop_when_full_is_non_blocking() -> None:
    async def _scenario() -> None:
        bus = MessageQueue(maxsize=1)
        first = OutboundEvent(channel="telegram", session_id="s1", target="u1", text="first")
        second = OutboundEvent(channel="telegram", session_id="s1", target="u1", text="second")

        await bus.publish_outbound(first)
        await asyncio.wait_for(bus.publish_outbound(second), timeout=0.05)

        got = await bus.next_outbound()
        assert got.text == "first"
        stats = bus.stats()
        assert stats["outbound_size"] == 0
        assert stats["outbound_dropped"] == 1

    asyncio.run(_scenario())


def test_message_queue_dead_letter_reason_histogram_increments() -> None:
    async def _scenario() -> None:
        bus = MessageQueue()
        await bus.publish_dead_letter(
            OutboundEvent(channel="fake", session_id="s1", target="u1", text="a", dead_lettered=True, dead_letter_reason="send_failed")
        )
        await bus.publish_dead_letter(
            OutboundEvent(channel="fake", session_id="s2", target="u2", text="b", dead_lettered=True, dead_letter_reason="send_failed")
        )
        await bus.publish_dead_letter(
            OutboundEvent(channel="fake", session_id="s3", target="u3", text="c", dead_lettered=True)
        )

        stats = bus.stats()
        assert stats["dead_letter_enqueued"] == 3
        assert stats["dead_letter_reason_counts"]["send_failed"] == 2
        assert stats["dead_letter_reason_counts"]["unknown"] == 1

    asyncio.run(_scenario())


def test_message_queue_dead_letter_replay_filters_dry_run_marker_and_bounds() -> None:
    async def _scenario() -> None:
        bus = MessageQueue(maxsize=10)
        await bus.publish_dead_letter(
            OutboundEvent(
                channel="fake",
                session_id="s1",
                target="u1",
                text="one",
                metadata={"id": "one"},
                dead_lettered=True,
                dead_letter_reason="send_failed",
                last_error="boom",
            )
        )
        await bus.publish_dead_letter(
            OutboundEvent(
                channel="fake",
                session_id="s2",
                target="u2",
                text="two",
                metadata={"id": "two"},
                dead_lettered=True,
                dead_letter_reason="send_failed",
            )
        )
        await bus.publish_dead_letter(
            OutboundEvent(
                channel="telegram",
                session_id="s1",
                target="u3",
                text="three",
                metadata={"id": "three"},
                dead_lettered=True,
                dead_letter_reason="channel_unavailable",
            )
        )
        await bus.publish_dead_letter(
            OutboundEvent(
                channel="fake",
                session_id="s1",
                target="u4",
                text="four",
                metadata={"id": "four"},
                dead_lettered=True,
                dead_letter_reason="send_failed",
            )
        )

        dry = await bus.replay_dead_letters(limit=5, channel="fake", reason="send_failed", session_id="s1", dry_run=True)
        assert dry["scanned"] == 4
        assert dry["matched"] == 2
        assert dry["replayed"] == 0
        assert dry["kept"] == 4
        assert dry["dropped"] == 0
        assert dry["replayed_by_channel"] == {}
        assert bus.stats()["dead_letter_size"] == 4

        replay = await bus.replay_dead_letters(limit=1, channel="fake", reason="send_failed", session_id="s1", dry_run=False)
        assert replay["scanned"] == 4
        assert replay["matched"] == 2
        assert replay["replayed"] == 1
        assert replay["kept"] == 3
        assert replay["dropped"] == 0
        assert replay["replayed_by_channel"] == {"fake": 1}

        replayed = await bus.next_outbound()
        assert replayed.attempt == 1
        assert replayed.dead_lettered is False
        assert replayed.dead_letter_reason == ""
        assert replayed.last_error == ""
        assert replayed.metadata["_replayed_from_dead_letter"] is True

        for idx in range(10):
            await bus.publish_outbound(OutboundEvent(channel="fake", session_id="fill", target="x", text=f"fill-{idx}"))

        dropped = await bus.replay_dead_letters(limit=5, channel="fake", reason="send_failed", session_id="s1", dry_run=False)
        assert dropped["matched"] == 1
        assert dropped["replayed"] == 0
        assert dropped["dropped"] == 1

        stats = bus.stats()
        assert stats["dead_letter_replayed"] == 1
        assert stats["dead_letter_replay_attempts"] == 2
        assert stats["dead_letter_replay_skipped"] == 3
        assert stats["dead_letter_replay_dropped"] == 1
        assert stats["dead_letter_size"] == 3

    asyncio.run(_scenario())


def test_message_queue_dead_letter_recent_snapshot_is_bounded_ordered_and_sanitized() -> None:
    async def _scenario() -> None:
        bus = MessageQueue(maxsize=32)
        for idx in range(12):
            await bus.publish_dead_letter(
                OutboundEvent(
                    channel="telegram",
                    session_id=f"s{idx}",
                    target="u1",
                    text=f"secret-{idx}",
                    metadata={"_replayed_from_dead_letter": idx == 11, "opaque": "keep-internal"},
                    attempt=idx + 1,
                    max_attempts=12,
                    retryable=bool(idx % 2),
                    dead_lettered=True,
                    dead_letter_reason="send_failed",
                    last_error=f"error-{idx}",
                    created_at=f"2026-03-04T00:00:{idx:02d}+00:00",
                )
            )

        stats = bus.stats()
        assert "dead_letter_recent" in stats
        recent = stats["dead_letter_recent"]
        assert isinstance(recent, list)
        assert len(recent) == 10

        expected_keys = {
            "channel",
            "session_id",
            "attempt",
            "max_attempts",
            "retryable",
            "dead_letter_reason",
            "last_error",
            "created_at",
            "replayed_from_dead_letter",
        }
        for row in recent:
            assert set(row.keys()) == expected_keys
            assert "text" not in row

        created = [row["created_at"] for row in recent]
        assert created == sorted(created, reverse=True)
        assert recent[0]["session_id"] == "s11"
        assert recent[0]["replayed_from_dead_letter"] is True
        assert recent[-1]["session_id"] == "s2"

        assert bus.stats()["dead_letter_recent"] == recent

    asyncio.run(_scenario())


def test_message_queue_stop_events_are_pruned_by_ttl() -> None:
    async def _scenario() -> None:
        bus = MessageQueue(stop_event_ttl_s=0.05)
        ev1 = bus.stop_event("s1")
        assert ev1.is_set() is False
        assert bus.stats()["stop_sessions"] == 1

        await asyncio.sleep(0.08)
        ev2 = bus.stop_event("s2")
        assert ev2.is_set() is False

        stats = bus.stats()
        assert stats["stop_sessions"] == 1
        assert "s1" not in bus._stop_events
        assert "s2" in bus._stop_events

    asyncio.run(_scenario())
