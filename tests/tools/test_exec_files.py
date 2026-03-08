from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from clawlite.tools.exec import ExecTool
from clawlite.tools.files import EditFileTool, EditTool, ListDirTool, ReadFileTool, ReadTool, WriteFileTool, WriteTool
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
        if os.name == "nt":
            script = bin_dir / "hello_from_path_append.cmd"
            script.write_text("@echo off\necho path_append_ok\n", encoding="utf-8", newline="\n")
            command = "hello_from_path_append.cmd"
        else:
            script = bin_dir / "hello_from_path_append"
            script.write_text("#!/usr/bin/env sh\necho path_append_ok\n", encoding="utf-8", newline="\n")
            script.chmod(0o755)
            command = "hello_from_path_append"

        out = await ExecTool(path_append=str(bin_dir)).run(
            {"command": command},
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


def test_exec_tool_invalid_command_syntax_returns_deterministic_marker() -> None:
    async def _scenario() -> None:
        out = await ExecTool().run(
            {"command": 'echo "unterminated'},
            ToolContext(session_id="s"),
        )
        assert "exit=-1" in out
        assert "stderr=invalid_command_syntax" in out

    asyncio.run(_scenario())


def test_exec_tool_output_truncation_telemetry_for_stdout_and_stderr() -> None:
    async def _scenario() -> None:
        out = await ExecTool(max_output_chars=256).run(
            {
                "command": "python3 -c \"import sys; print('a' * 1200); sys.stderr.write('b' * 1300)\"",
                "max_output_chars": 256,
            },
            ToolContext(session_id="s"),
        )
        assert "exit=0" in out
        assert "stdout_truncated=true" in out
        assert "stderr_truncated=true" in out
        assert "stdout_original_chars=1200" in out
        assert "stderr_original_chars=1300" in out

    asyncio.run(_scenario())


def test_file_tools_restrict_to_workspace_blocks_outside_path(tmp_path: Path) -> None:
    async def _scenario() -> None:
        outside = tmp_path.parent / "outside.txt"
        writer = WriteFileTool(workspace_path=tmp_path, restrict_to_workspace=True)
        with pytest.raises(PermissionError):
            await writer.run({"path": str(outside), "content": "x"}, ToolContext(session_id="s"))

    asyncio.run(_scenario())


def test_file_alias_tools_reuse_existing_behavior(tmp_path: Path) -> None:
    async def _scenario() -> None:
        target = tmp_path / "alias.txt"
        writer = WriteTool()
        reader = ReadTool()
        editor = EditTool()

        assert writer.name == "write"
        assert reader.name == "read"
        assert editor.name == "edit"

        await writer.run({"path": str(target), "content": "hello alias"}, ToolContext(session_id="s"))
        content = await reader.run({"path": str(target)}, ToolContext(session_id="s"))
        assert content == "hello alias"
        changed = await editor.run(
            {"path": str(target), "search": "alias", "replace": "tool"},
            ToolContext(session_id="s"),
        )
        assert changed == "ok"
        updated = await reader.run({"path": str(target)}, ToolContext(session_id="s"))
        assert updated == "hello tool"

    asyncio.run(_scenario())
