from __future__ import annotations

import asyncio
import json
import threading

from clawlite.core.subagent import SubagentManager
from clawlite.tools.base import ToolContext
from clawlite.tools.cron import CronTool
from clawlite.tools.message import MessageTool
from clawlite.tools.spawn import SpawnTool


class FakeCronAPI:
    def __init__(self) -> None:
        self.last_add: dict | None = None

    async def add_job(
        self,
        *,
        session_id: str,
        expression: str,
        prompt: str,
        name: str = "",
        timezone_name: str | None = None,
        channel: str = "",
        target: str = "",
        metadata: dict | None = None,
    ) -> str:
        self.last_add = {
            "session_id": session_id,
            "expression": expression,
            "prompt": prompt,
            "name": name,
            "timezone_name": timezone_name,
            "channel": channel,
            "target": target,
            "metadata": metadata,
        }
        return f"job:{session_id}:{expression}:{prompt}"

    async def list_jobs(self, *, session_id: str):
        return [{"id": "j1", "expression": "*/2 * * * *", "timezone": "UTC"}]

    def remove_job(self, job_id: str) -> bool:
        return job_id == "j1"

    def enable_job(self, job_id: str, *, enabled: bool) -> bool:
        return job_id == "j1"

    async def run_job(self, job_id: str, *, force: bool = True) -> str | None:
        if job_id != "j1":
            raise KeyError(job_id)
        return "ran"


class FakeMsgAPI:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send(self, *, channel: str, target: str, text: str, metadata: dict | None = None) -> str:
        self.calls.append({"channel": channel, "target": target, "text": text, "metadata": metadata})
        return f"sent:{channel}:{target}:{text}"


class FakeMemory:
    def __init__(self, verdict) -> None:
        self.verdict = verdict
        self.calls: list[tuple[str, str]] = []

    def integration_policy(self, kind: str, *, session_id: str):
        self.calls.append((kind, session_id))
        return self.verdict


class FakeMemoryPolicyRaises:
    def integration_policy(self, _kind: str, *, session_id: str):
        raise RuntimeError(f"boom:{session_id}")


async def _runner(_session_id: str, task: str) -> str:
    return f"done:{task}"


def test_cron_tool_add_and_list() -> None:
    async def _scenario() -> None:
        api = FakeCronAPI()
        tool = CronTool(api)
        added = await tool.run(
            {"action": "add", "expression": "*/2 * * * *", "prompt": "ping", "run_once": True},
            ToolContext(session_id="s1"),
        )
        added_payload = json.loads(added)
        assert added_payload["ok"] is True
        assert "job:s1" in added_payload["job_id"]
        assert api.last_add is not None
        assert api.last_add["metadata"] == {"source": "tool:cron", "run_once": True}

        listed = await tool.run({"action": "list"}, ToolContext(session_id="s1"))
        listed_payload = json.loads(listed)
        assert listed_payload["ok"] is True
        assert listed_payload["count"] == 1
        assert listed_payload["jobs"][0]["id"] == "j1"

        removed = json.loads(await tool.run({"action": "remove", "job_id": "j1"}, ToolContext(session_id="s1")))
        assert removed["ok"] is True

        enabled = json.loads(await tool.run({"action": "enable", "job_id": "j1"}, ToolContext(session_id="s1")))
        assert enabled["ok"] is True
        assert enabled["enabled"] is True

        disabled = json.loads(await tool.run({"action": "disable", "job_id": "j1"}, ToolContext(session_id="s1")))
        assert disabled["ok"] is True
        assert disabled["enabled"] is False

        ran = json.loads(await tool.run({"action": "run", "job_id": "j1"}, ToolContext(session_id="s1")))
        assert ran["ok"] is True
        assert ran["output"] == "ran"

        missing = json.loads(await tool.run({"action": "run", "job_id": "missing"}, ToolContext(session_id="s1")))
        assert missing["ok"] is False
        assert missing["error"] == "job_not_found"

    asyncio.run(_scenario())


def test_message_tool() -> None:
    async def _scenario() -> None:
        api = FakeMsgAPI()
        tool = MessageTool(api)
        out = await tool.run({"channel": "telegram", "target": "1", "text": "hello"}, ToolContext(session_id="s"))
        assert out.startswith("sent:telegram")
        assert api.calls[-1]["metadata"] is None

    asyncio.run(_scenario())


def test_cron_tool_sync_remove_and_enable_run_off_event_loop_thread() -> None:
    class ThreadAwareCronAPI:
        async def add_job(self, **_kwargs):  # pragma: no cover - not used in this scenario
            return "job"

        def list_jobs(self, *, session_id: str):
            return [{"id": f"job:{session_id}"}]

        def remove_job(self, job_id: str) -> bool:
            self.remove_thread_id = threading.get_ident()
            return job_id == "j1"

        def enable_job(self, job_id: str, *, enabled: bool) -> bool:
            self.enable_thread_id = threading.get_ident()
            self.enable_enabled = enabled
            return job_id == "j1"

        async def run_job(self, job_id: str, *, force: bool = True) -> str | None:
            return None

    async def _scenario() -> None:
        api = ThreadAwareCronAPI()
        tool = CronTool(api)
        loop_thread_id = threading.get_ident()

        removed = json.loads(await tool.run({"action": "remove", "job_id": "j1"}, ToolContext(session_id="s1")))
        assert removed["ok"] is True
        assert api.remove_thread_id != loop_thread_id

        enabled = json.loads(await tool.run({"action": "enable", "job_id": "j1"}, ToolContext(session_id="s1")))
        assert enabled["ok"] is True
        assert api.enable_enabled is True
        assert api.enable_thread_id != loop_thread_id

    asyncio.run(_scenario())


def test_message_tool_maps_buttons_to_telegram_metadata() -> None:
    async def _scenario() -> None:
        api = FakeMsgAPI()
        tool = MessageTool(api)
        out = await tool.run(
            {
                "channel": "telegram",
                "target": "1",
                "text": "choose",
                "metadata": {"message_thread_id": 7},
                "buttons": [[{"text": "Approve", "callback_data": "approve:1"}, {"text": "Open", "url": "https://example.com"}]],
            },
            ToolContext(session_id="s"),
        )
        assert out.startswith("sent:telegram")
        sent_metadata = api.calls[-1]["metadata"]
        assert sent_metadata["message_thread_id"] == 7
        assert sent_metadata["_telegram_inline_keyboard"][0][0]["text"] == "Approve"
        assert sent_metadata["_telegram_inline_keyboard"][0][0]["callback_data"] == "approve:1"
        assert sent_metadata["_telegram_inline_keyboard"][0][1]["text"] == "Open"
        assert sent_metadata["_telegram_inline_keyboard"][0][1]["url"] == "https://example.com"

    asyncio.run(_scenario())


def test_message_tool_invalid_buttons_raises_value_error() -> None:
    async def _scenario() -> None:
        api = FakeMsgAPI()
        tool = MessageTool(api)

        try:
            await tool.run(
                {
                    "channel": "telegram",
                    "target": "1",
                    "text": "choose",
                    "buttons": [[{"text": "Broken", "callback_data": "x", "url": "https://example.com"}]],
                },
                ToolContext(session_id="s"),
            )
            raise AssertionError("expected ValueError for invalid buttons")
        except ValueError as exc:
            assert "exactly one" in str(exc)

    asyncio.run(_scenario())


def test_message_tool_maps_telegram_edit_action_to_metadata_bridge() -> None:
    async def _scenario() -> None:
        api = FakeMsgAPI()
        tool = MessageTool(api)
        out = await tool.run(
            {
                "channel": "telegram",
                "target": "1",
                "action": "edit",
                "message_id": 42,
                "text": "updated",
            },
            ToolContext(session_id="s"),
        )
        assert out.startswith("sent:telegram")
        metadata = api.calls[-1]["metadata"]
        assert metadata["_telegram_action"] == "edit"
        assert metadata["_telegram_action_message_id"] == 42

    asyncio.run(_scenario())


def test_message_tool_telegram_action_constraints_raise_value_error() -> None:
    async def _scenario() -> None:
        api = FakeMsgAPI()
        tool = MessageTool(api)

        try:
            await tool.run(
                {
                    "channel": "telegram",
                    "target": "1",
                    "action": "delete",
                    "text": "",
                },
                ToolContext(session_id="s"),
            )
            raise AssertionError("expected ValueError for missing message_id")
        except ValueError as exc:
            assert "message_id" in str(exc)

        try:
            await tool.run(
                {
                    "channel": "slack",
                    "target": "general",
                    "action": "edit",
                    "message_id": 1,
                    "text": "x",
                },
                ToolContext(session_id="s"),
            )
            raise AssertionError("expected ValueError for non-telegram action")
        except ValueError as exc:
            assert "telegram" in str(exc)

    asyncio.run(_scenario())


def test_spawn_tool() -> None:
    async def _scenario() -> None:
        manager = SubagentManager()
        tool = SpawnTool(manager, _runner)
        run_id = await tool.run({"task": "analyze"}, ToolContext(session_id="s1"))
        assert run_id

    asyncio.run(_scenario())


def test_spawn_tool_surfaces_queue_limits(tmp_path) -> None:
    async def _scenario() -> None:
        gate = asyncio.Event()

        async def _slow_runner(_session_id: str, task: str) -> str:
            await gate.wait()
            return task

        manager = SubagentManager(
            state_path=tmp_path / "state",
            max_concurrent_runs=1,
            max_queued_runs=0,
            per_session_quota=2,
        )
        tool = SpawnTool(manager, _slow_runner)
        await tool.run({"task": "first"}, ToolContext(session_id="s1"))

        try:
            await tool.run({"task": "second"}, ToolContext(session_id="s2"))
            raise AssertionError("expected ValueError for queue limit")
        except ValueError as exc:
            assert "queue limit" in str(exc)

        gate.set()
        await asyncio.sleep(0)

    asyncio.run(_scenario())


def test_spawn_tool_allows_when_memory_policy_allows() -> None:
    async def _scenario() -> None:
        manager = SubagentManager()
        memory = FakeMemory({"allowed": True})
        tool = SpawnTool(manager, _runner, memory=memory)
        run_id = await tool.run({"task": "analyze"}, ToolContext(session_id="s-policy-allow"))
        assert run_id
        assert memory.calls == [("subagent", "s-policy-allow")]

    asyncio.run(_scenario())


def test_spawn_tool_blocks_when_memory_policy_denies() -> None:
    async def _scenario() -> None:
        manager = SubagentManager()
        memory = FakeMemory({"allowed": False, "reason": "subagent_disabled"})
        tool = SpawnTool(manager, _runner, memory=memory)

        try:
            await tool.run({"task": "analyze"}, ToolContext(session_id="s-policy-block"))
            raise AssertionError("expected ValueError for memory policy block")
        except ValueError as exc:
            assert str(exc) == "subagent_spawn_blocked_by_memory_policy:subagent_disabled"
        assert memory.calls == [("subagent", "s-policy-block")]

    asyncio.run(_scenario())


def test_spawn_tool_blocks_when_memory_policy_check_raises() -> None:
    async def _scenario() -> None:
        manager = SubagentManager()
        tool = SpawnTool(manager, _runner, memory=FakeMemoryPolicyRaises())

        try:
            await tool.run({"task": "analyze"}, ToolContext(session_id="s-policy-error"))
            raise AssertionError("expected ValueError for memory policy exception")
        except ValueError as exc:
            assert str(exc) == "subagent_spawn_blocked_by_memory_policy:policy_check_exception"

    asyncio.run(_scenario())
