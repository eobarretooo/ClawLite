from __future__ import annotations

import asyncio
import json
from pathlib import Path

from clawlite.tools.base import ToolContext
from clawlite.tools.process import ProcessTool


def _loads(payload: str) -> dict:
    return json.loads(payload)


def test_process_start_list_poll_completed_command(tmp_path: Path) -> None:
    async def _scenario() -> None:
        tool = ProcessTool(workspace_path=tmp_path, restrict_to_workspace=True)
        started = _loads(
            await tool.run(
                {"action": "start", "command": "python3 -c \"print('done')\""},
                ToolContext(session_id="s"),
            )
        )
        session_id = started["sessionId"]

        listed = _loads(await tool.run({"action": "list"}, ToolContext(session_id="s")))
        assert any(row["sessionId"] == session_id for row in listed["sessions"])

        polled = _loads(
            await tool.run(
                {"action": "poll", "sessionId": session_id, "timeout": 2000},
                ToolContext(session_id="s"),
            )
        )
        assert polled["status"] == "completed"
        assert polled["exitCode"] == 0

    asyncio.run(_scenario())


def test_process_log_slicing(tmp_path: Path) -> None:
    async def _scenario() -> None:
        tool = ProcessTool(workspace_path=tmp_path, restrict_to_workspace=True)
        started = _loads(
            await tool.run(
                {"action": "start", "command": "python3 -c \"print('abcdef')\""},
                ToolContext(session_id="s"),
            )
        )
        session_id = started["sessionId"]
        await tool.run({"action": "poll", "sessionId": session_id, "timeout": 2000}, ToolContext(session_id="s"))

        log_payload = _loads(
            await tool.run(
                {"action": "log", "sessionId": session_id, "offset": 1, "limit": 3},
                ToolContext(session_id="s"),
            )
        )
        assert log_payload["log"] == "bcd"

    asyncio.run(_scenario())


def test_process_kill_running_process(tmp_path: Path) -> None:
    async def _scenario() -> None:
        tool = ProcessTool(workspace_path=tmp_path, restrict_to_workspace=True)
        started = _loads(
            await tool.run(
                {"action": "start", "command": "python3 -c \"import time; time.sleep(30)\""},
                ToolContext(session_id="s"),
            )
        )
        session_id = started["sessionId"]

        killed = _loads(await tool.run({"action": "kill", "sessionId": session_id}, ToolContext(session_id="s")))
        assert killed["status"] == "ok"
        assert killed["killed"] is True

        polled = _loads(await tool.run({"action": "poll", "sessionId": session_id}, ToolContext(session_id="s")))
        assert polled["status"] in {"failed", "completed"}

    asyncio.run(_scenario())


def test_process_remove_finished_session(tmp_path: Path) -> None:
    async def _scenario() -> None:
        tool = ProcessTool(workspace_path=tmp_path, restrict_to_workspace=True)
        started = _loads(
            await tool.run(
                {"action": "start", "command": "python3 -c \"print('x')\""},
                ToolContext(session_id="s"),
            )
        )
        session_id = started["sessionId"]
        await tool.run({"action": "poll", "sessionId": session_id, "timeout": 2000}, ToolContext(session_id="s"))

        removed = _loads(await tool.run({"action": "remove", "sessionId": session_id}, ToolContext(session_id="s")))
        assert removed["status"] == "ok"

        listed = _loads(await tool.run({"action": "list"}, ToolContext(session_id="s")))
        assert not any(row["sessionId"] == session_id for row in listed["sessions"])

    asyncio.run(_scenario())


def test_process_clear_output(tmp_path: Path) -> None:
    async def _scenario() -> None:
        tool = ProcessTool(workspace_path=tmp_path, restrict_to_workspace=True)
        started = _loads(
            await tool.run(
                {"action": "start", "command": "python3 -c \"print('clear-me')\""},
                ToolContext(session_id="s"),
            )
        )
        session_id = started["sessionId"]
        await tool.run({"action": "poll", "sessionId": session_id, "timeout": 2000}, ToolContext(session_id="s"))

        cleared = _loads(await tool.run({"action": "clear", "session_id": session_id}, ToolContext(session_id="s")))
        assert cleared["status"] == "ok"

        log_payload = _loads(await tool.run({"action": "log", "sessionId": session_id}, ToolContext(session_id="s")))
        assert log_payload["log"] == ""

    asyncio.run(_scenario())


def test_process_unknown_action_and_missing_session_handling(tmp_path: Path) -> None:
    async def _scenario() -> None:
        tool = ProcessTool(workspace_path=tmp_path, restrict_to_workspace=True)

        unknown = _loads(await tool.run({"action": "noop"}, ToolContext(session_id="s")))
        assert unknown["status"] == "failed"
        assert unknown["error"] == "unknown_action"

        missing_id = _loads(await tool.run({"action": "poll"}, ToolContext(session_id="s")))
        assert missing_id["status"] == "failed"
        assert missing_id["error"] == "session_id_required"

        missing_session = _loads(
            await tool.run({"action": "poll", "sessionId": "proc_missing"}, ToolContext(session_id="s"))
        )
        assert missing_session["status"] == "failed"
        assert missing_session["error"] == "session_not_found"

    asyncio.run(_scenario())
