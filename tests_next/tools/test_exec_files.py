from __future__ import annotations

import asyncio
from pathlib import Path

from clawlite.tools.exec import ExecTool
from clawlite.tools.files import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from clawlite.tools.base import ToolContext


def test_exec_tool_runs_command() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run({"command": "echo hello"}, ToolContext(session_id="s"))
        assert "exit=0" in out
        assert "hello" in out

    asyncio.run(_scenario())


def test_file_tools_roundtrip(tmp_path: Path) -> None:
    async def _scenario() -> None:
        target = tmp_path / "a.txt"
        writer = WriteFileTool()
        reader = ReadFileTool()
        editor = EditFileTool()
        lister = ListDirTool()
        await writer.run({"path": str(target), "content": "hello world"}, ToolContext(session_id="s"))
        text = await reader.run({"path": str(target)}, ToolContext(session_id="s"))
        assert "hello" in text
        changed = await editor.run({"path": str(target), "search": "world", "replace": "claw"}, ToolContext(session_id="s"))
        assert changed == "ok"
        listed = await lister.run({"path": str(tmp_path)}, ToolContext(session_id="s"))
        assert "a.txt" in listed

    asyncio.run(_scenario())
