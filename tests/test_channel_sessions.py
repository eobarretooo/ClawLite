from __future__ import annotations

import asyncio

from clawlite.runtime.channel_sessions import ChannelSessionManager


def test_channel_session_manager_bind_and_update() -> None:
    mgr = ChannelSessionManager()

    row1 = mgr.bind(instance_key="irc", channel="irc", session_id="irc_group_#ops")
    assert row1.message_count == 1
    assert mgr.last_session_id("irc") == "irc_group_#ops"

    row2 = mgr.bind(
        instance_key="irc",
        channel="irc",
        session_id="irc_group_#ops",
        metadata={"source": "test"},
    )
    assert row2.message_count == 2
    assert row2.metadata and row2.metadata["source"] == "test"


def test_channel_session_manager_replaces_session_on_new_sid() -> None:
    mgr = ChannelSessionManager()
    mgr.bind(instance_key="slack", channel="slack", session_id="sl_C1")
    mgr.bind(instance_key="slack", channel="slack", session_id="sl_C2")

    assert mgr.last_session_id("slack") == "sl_C2"
    rows = mgr.list_by_channel("slack")
    assert len(rows) == 1
    assert rows[0].session_id == "sl_C2"


def test_channel_session_manager_register_and_cancel_tasks() -> None:
    mgr = ChannelSessionManager()

    async def _run() -> None:
        evt = asyncio.Event()

        async def _waiter() -> None:
            await evt.wait()

        task = asyncio.create_task(_waiter())
        mgr.register_task("tg_1", task)
        assert mgr.active_task_count("tg_1") == 1

        cancelled = mgr.cancel_session_tasks("tg_1")
        assert cancelled == 1

        try:
            await task
        except asyncio.CancelledError:
            pass
        mgr.unregister_task("tg_1", task)
        assert mgr.active_task_count("tg_1") == 0

    asyncio.run(_run())
