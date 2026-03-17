from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from clawlite.bus.events import InboundEvent, OutboundEvent
from clawlite.bus.journal import BusJournal
from clawlite.bus.queue import BusFullError, MessageQueue


# ---------------------------------------------------------------------------
# BusJournal unit tests
# ---------------------------------------------------------------------------

def test_journal_append_and_replay_inbound(tmp_path):
    db = tmp_path / "bus.db"
    journal = BusJournal(db)
    journal.open()

    event = InboundEvent(channel="discord", session_id="s1", user_id="u1", text="hello")
    row_id = journal.append_inbound(event)
    assert row_id is not None

    # Should show as unacked
    unacked = journal.unacked_inbound()
    assert len(unacked) == 1
    row_id2, replayed = unacked[0]
    assert row_id2 == row_id
    assert replayed.text == "hello"
    assert replayed.channel == "discord"
    assert replayed.correlation_id == event.correlation_id

    journal.close()


def test_journal_ack_removes_from_replay(tmp_path):
    db = tmp_path / "bus.db"
    journal = BusJournal(db)
    journal.open()

    event = InboundEvent(channel="telegram", session_id="s2", user_id="u2", text="bye")
    row_id = journal.append_inbound(event)
    journal.ack_inbound(row_id)

    assert journal.unacked_inbound() == []
    journal.close()


def test_journal_survives_restart(tmp_path):
    db = tmp_path / "bus.db"

    # First session: write
    j1 = BusJournal(db)
    j1.open()
    e1 = InboundEvent(channel="discord", session_id="s3", user_id="u3", text="persist me")
    j1.append_inbound(e1)
    j1.close()

    # Second session: replay
    j2 = BusJournal(db)
    j2.open()
    unacked = j2.unacked_inbound()
    assert len(unacked) == 1
    _, replayed = unacked[0]
    assert replayed.text == "persist me"
    j2.close()


def test_journal_outbound_append_and_ack(tmp_path):
    db = tmp_path / "bus.db"
    journal = BusJournal(db)
    journal.open()

    event = OutboundEvent(channel="discord", session_id="s4", target="user:1", text="reply")
    row_id = journal.append_outbound(event)
    assert row_id is not None

    unacked = journal.unacked_outbound()
    assert len(unacked) == 1

    journal.ack_outbound(row_id)
    assert journal.unacked_outbound() == []
    journal.close()


def test_journal_closed_does_not_crash():
    journal = BusJournal("/tmp/nonexistent/bus.db")
    # Not opened — all operations should be no-ops / return None
    assert journal.append_inbound(
        InboundEvent(channel="c", session_id="s", user_id="u", text="t")
    ) is None
    assert journal.unacked_inbound() == []


# ---------------------------------------------------------------------------
# MessageQueue integration with journal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_queue_with_journal_acks_on_consume(tmp_path):
    db = tmp_path / "bus.db"
    journal = BusJournal(db)
    journal.open()

    bus = MessageQueue(journal=journal)
    event = InboundEvent(channel="discord", session_id="s5", user_id="u5", text="ack me")
    await bus.publish_inbound(event)

    # Unacked before consume
    assert len(journal.unacked_inbound()) == 1

    consumed = await bus.next_inbound()
    assert consumed.text == "ack me"

    # Acked after consume
    assert journal.unacked_inbound() == []
    journal.close()


@pytest.mark.asyncio
async def test_queue_journal_replay_on_restart(tmp_path):
    db = tmp_path / "bus.db"
    journal = BusJournal(db)
    journal.open()

    bus = MessageQueue(journal=journal)
    await bus.publish_inbound(InboundEvent(channel="c", session_id="s", user_id="u", text="replay"))
    # Don't consume — simulate crash/restart
    journal.close()

    # New session replays
    j2 = BusJournal(db)
    j2.open()
    unacked = j2.unacked_inbound()
    assert len(unacked) == 1
    assert unacked[0][1].text == "replay"
    j2.close()


@pytest.mark.asyncio
async def test_queue_with_journal_acks_outbound_on_consume(tmp_path):
    db = tmp_path / "bus.db"
    journal = BusJournal(db)
    journal.open()

    bus = MessageQueue(journal=journal)
    event = OutboundEvent(channel="discord", session_id="s5", target="u5", text="ack me too")
    await bus.publish_outbound(event)

    assert len(journal.unacked_outbound()) == 1

    consumed = await bus.next_outbound()
    assert consumed.text == "ack me too"
    assert journal.unacked_outbound() == []
    journal.close()


# ---------------------------------------------------------------------------
# Wildcard subscription
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wildcard_subscription_receives_all_channels():
    bus = MessageQueue()
    received: list[InboundEvent] = []

    async def collect():
        async for event in bus.subscribe("*"):
            received.append(event)
            if len(received) >= 2:
                return

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)  # Let task start

    await bus.publish_inbound(InboundEvent(channel="discord", session_id="s", user_id="u", text="A"))
    await bus.publish_inbound(InboundEvent(channel="telegram", session_id="s", user_id="u", text="B"))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert len(received) == 2
    channels = {e.channel for e in received}
    assert channels == {"discord", "telegram"}


# ---------------------------------------------------------------------------
# BusFullError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bus_full_error_raised_on_nowait():
    bus = MessageQueue(maxsize=1)
    # Fill the queue
    await bus.publish_inbound(InboundEvent(channel="c", session_id="s", user_id="u", text="1"))
    # Second publish with nowait should raise
    with pytest.raises(BusFullError):
        await bus.publish_inbound(
            InboundEvent(channel="c", session_id="s", user_id="u", text="2"),
            nowait=True,
        )


@pytest.mark.asyncio
async def test_bus_full_blocks_without_nowait():
    bus = MessageQueue(maxsize=1)
    await bus.publish_inbound(InboundEvent(channel="c", session_id="s", user_id="u", text="1"))

    # With nowait=False (default), publish should block — wrap in timeout
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            bus.publish_inbound(InboundEvent(channel="c", session_id="s", user_id="u", text="2")),
            timeout=0.1,
        )
