from __future__ import annotations

import asyncio
import json

from clawlite.core.subagent import SubagentManager
from clawlite.tools.base import ToolContext
from clawlite.tools.cron import CronTool
from clawlite.tools.message import MessageTool
from clawlite.tools.spawn import SpawnTool


class FakeCronAPI:
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
    async def send(self, *, channel: str, target: str, text: str) -> str:
        return f"sent:{channel}:{target}:{text}"


async def _runner(_session_id: str, task: str) -> str:
    return f"done:{task}"


def test_cron_tool_add_and_list() -> None:
    async def _scenario() -> None:
        tool = CronTool(FakeCronAPI())
        added = await tool.run({"action": "add", "expression": "*/2 * * * *", "prompt": "ping"}, ToolContext(session_id="s1"))
        added_payload = json.loads(added)
        assert added_payload["ok"] is True
        assert "job:s1" in added_payload["job_id"]

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
        tool = MessageTool(FakeMsgAPI())
        out = await tool.run({"channel": "telegram", "target": "1", "text": "hello"}, ToolContext(session_id="s"))
        assert out.startswith("sent:telegram")

    asyncio.run(_scenario())


def test_spawn_tool() -> None:
    async def _scenario() -> None:
        manager = SubagentManager()
        tool = SpawnTool(manager, _runner)
        run_id = await tool.run({"task": "analyze"}, ToolContext(session_id="s1"))
        assert run_id

    asyncio.run(_scenario())
