from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

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


def test_exec_tool_path_append(tmp_path: Path) -> None:
    async def _scenario() -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        script = bin_dir / "hello_from_path_append"
        script.write_text("#!/usr/bin/env sh\necho path_append_ok\n", encoding="utf-8")
        script.chmod(0o755)

        out = await ExecTool(path_append=str(bin_dir)).run(
            {"command": "hello_from_path_append"},
            ToolContext(session_id="s"),
        )
        assert "exit=0" in out
        assert "path_append_ok" in out

    asyncio.run(_scenario())


def test_exec_tool_restrict_to_workspace_blocks_outside_path(tmp_path: Path) -> None:
    async def _scenario() -> None:
        out = await ExecTool(workspace_path=tmp_path, restrict_to_workspace=True).run(
            {"command": "cat /etc/passwd"},
            ToolContext(session_id="s"),
        )
        assert "blocked_by_workspace_guard" in out

    asyncio.run(_scenario())


def test_exec_tool_default_policy_blocks_dangerous_command() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run(
            {"command": "rm -rf /tmp/safe-check"},
            ToolContext(session_id="s"),
        )
        assert "blocked_by_policy:deny_pattern" in out

    asyncio.run(_scenario())


def test_exec_tool_allow_patterns_enforced() -> None:
    async def _scenario() -> None:
        out = await ExecTool(allow_patterns=[r"^echo\\s+"]).run(
            {"command": "pwd"},
            ToolContext(session_id="s"),
        )
        assert "blocked_by_policy:not_in_allow_patterns" in out

    asyncio.run(_scenario())


def test_exec_tool_restrict_to_workspace_blocks_absolute_path_in_flag(tmp_path: Path) -> None:
    async def _scenario() -> None:
        out = await ExecTool(workspace_path=tmp_path, restrict_to_workspace=True).run(
            {"command": "echo done --output=/etc/passwd"},
            ToolContext(session_id="s"),
        )
        assert "blocked_by_workspace_guard:path_outside_workspace:/etc/passwd" in out

    asyncio.run(_scenario())


def test_exec_tool_timeout_reports_telemetry() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run(
            {"command": 'sh -c "sleep 2"', "timeout": 0.1},
            ToolContext(session_id="s"),
        )
        assert "stderr=timeout after 0.1s" in out
        assert "telemetry=timeout_s=0.1" in out
        assert "kill_sent=true" in out

    asyncio.run(_scenario())


def test_file_tools_restrict_to_workspace_blocks_outside_path(tmp_path: Path) -> None:
    async def _scenario() -> None:
        outside = tmp_path.parent / "outside.txt"
        writer = WriteFileTool(workspace_path=tmp_path, restrict_to_workspace=True)
        with pytest.raises(PermissionError):
            await writer.run({"path": str(outside), "content": "x"}, ToolContext(session_id="s"))

    asyncio.run(_scenario())
