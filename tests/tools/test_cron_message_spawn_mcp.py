from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from clawlite.core.subagent import SubagentManager
from clawlite.tools.base import ToolContext
from clawlite.tools.cron import CronTool
from clawlite.tools.mcp import MCPTool
from clawlite.tools.message import MessageTool
from clawlite.tools.spawn import SpawnTool


class FakeCronAPI:
    async def add_job(self, *, session_id: str, expression: str, prompt: str) -> str:
        return f"job:{session_id}:{expression}:{prompt}"

    async def list_jobs(self, *, session_id: str):
        return [{"id": "j1", "expression": "*/2 * * * *"}]


class FakeMsgAPI:
    async def send(self, *, channel: str, target: str, text: str) -> str:
        return f"sent:{channel}:{target}:{text}"


async def _runner(_session_id: str, task: str) -> str:
    return f"done:{task}"


def test_cron_tool_add_and_list() -> None:
    async def _scenario() -> None:
        tool = CronTool(FakeCronAPI())
        added = await tool.run({"action": "add", "expression": "*/2 * * * *", "prompt": "ping"}, ToolContext(session_id="s1"))
        assert "job:s1" in added
        listed = await tool.run({"action": "list"}, ToolContext(session_id="s1"))
        assert "j1" in listed

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


def test_mcp_tool() -> None:
    async def _scenario() -> None:
        fake_response = AsyncMock()
        fake_response.raise_for_status = lambda: None
        fake_response.json = lambda: {"result": {"ok": True}}
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
            out = await MCPTool().run(
                {"url": "https://mcp.local/call", "tool": "skill.test", "arguments": {"x": 1}},
                ToolContext(session_id="s"),
            )
            assert "ok" in out

    asyncio.run(_scenario())
