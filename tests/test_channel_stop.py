from __future__ import annotations

import asyncio

from clawlite.channels.manager import ChannelManager
from clawlite.runtime import subagents as sub_mod


def test_stop_cancels_inflight_session_task(monkeypatch) -> None:
    async def _run() -> None:
        cm = ChannelManager()
        started = asyncio.Event()

        async def fake_handle(session_id: str, text: str, channel: str = "") -> str:
            started.set()
            await asyncio.sleep(5)
            return "done"

        monkeypatch.setattr(cm, "_handle_message", fake_handle)

        class _FakeSubRuntime:
            def cancel_session(self, session_id: str) -> int:
                return 0

        monkeypatch.setattr(sub_mod, "get_subagent_runtime", lambda: _FakeSubRuntime())

        handler = cm._build_message_handler(instance_key="irc", channel_name="irc")
        running = asyncio.create_task(handler("irc_group_#ops", "processar tarefa longa"))
        await started.wait()

        stop_reply = await handler("irc_group_#ops", "/stop")
        assert "Stopped" in stop_reply

        await asyncio.wait_for(running, timeout=1.0)
        assert running.done()

    asyncio.run(_run())


def test_stop_without_active_tasks_returns_noop(monkeypatch) -> None:
    async def _run() -> None:
        cm = ChannelManager()

        class _FakeSubRuntime:
            def cancel_session(self, session_id: str) -> int:
                return 0

        monkeypatch.setattr(sub_mod, "get_subagent_runtime", lambda: _FakeSubRuntime())

        handler = cm._build_message_handler(instance_key="signal", channel_name="signal")
        stop_reply = await handler("signal_dm_551199999", "/stop")
        assert stop_reply == "No active task to stop."

    asyncio.run(_run())
