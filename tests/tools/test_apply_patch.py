from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from clawlite.tools.apply_patch import ApplyPatchTool
from clawlite.tools.base import ToolContext


def test_apply_patch_add_file_success(tmp_path: Path) -> None:
    async def _scenario() -> None:
        tool = ApplyPatchTool(workspace_path=tmp_path, restrict_to_workspace=True)
        patch = "\n".join(
            [
                "*** Begin Patch",
                "*** Add File: notes.txt",
                "+hello",
                "+world",
                "*** End Patch",
            ]
        )

        result = await tool.run({"input": patch}, ToolContext(session_id="s"))
        assert result == "Success. Updated the following files:\nA notes.txt"
        assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "hello\nworld\n"

    asyncio.run(_scenario())


def test_apply_patch_update_file_success(tmp_path: Path) -> None:
    async def _scenario() -> None:
        target = tmp_path / "doc.txt"
        target.write_text("alpha\nbeta\n", encoding="utf-8")
        tool = ApplyPatchTool(workspace_path=tmp_path, restrict_to_workspace=True)
        patch = "\n".join(
            [
                "*** Begin Patch",
                "*** Update File: doc.txt",
                "@@",
                "-beta",
                "+gamma",
                "*** End Patch",
            ]
        )

        result = await tool.run({"input": patch}, ToolContext(session_id="s"))
        assert result == "Success. Updated the following files:\nM doc.txt"
        assert target.read_text(encoding="utf-8") == "alpha\ngamma\n"

    asyncio.run(_scenario())


def test_apply_patch_delete_file_success(tmp_path: Path) -> None:
    async def _scenario() -> None:
        target = tmp_path / "old.txt"
        target.write_text("obsolete", encoding="utf-8")
        tool = ApplyPatchTool(workspace_path=tmp_path, restrict_to_workspace=True)
        patch = "\n".join(
            [
                "*** Begin Patch",
                "*** Delete File: old.txt",
                "*** End Patch",
            ]
        )

        result = await tool.run({"input": patch}, ToolContext(session_id="s"))
        assert result == "Success. Updated the following files:\nD old.txt"
        assert not target.exists()

    asyncio.run(_scenario())


def test_apply_patch_move_file_success(tmp_path: Path) -> None:
    async def _scenario() -> None:
        source = tmp_path / "from.txt"
        source.write_text("hello\n", encoding="utf-8")
        tool = ApplyPatchTool(workspace_path=tmp_path, restrict_to_workspace=True)
        patch = "\n".join(
            [
                "*** Begin Patch",
                "*** Update File: from.txt",
                "*** Move to: nested/to.txt",
                "@@",
                "-hello",
                "+bye",
                "*** End Patch",
            ]
        )

        result = await tool.run({"input": patch}, ToolContext(session_id="s"))
        assert result == "Success. Updated the following files:\nM nested/to.txt"
        assert not source.exists()
        assert (tmp_path / "nested" / "to.txt").read_text(encoding="utf-8") == "bye\n"

    asyncio.run(_scenario())


def test_apply_patch_malformed_patch_rejected(tmp_path: Path) -> None:
    async def _scenario() -> None:
        tool = ApplyPatchTool(workspace_path=tmp_path, restrict_to_workspace=True)
        with pytest.raises(ValueError, match="Invalid patch"):
            await tool.run({"input": "*** Begin Patch\n*** Add File: x\n+1"}, ToolContext(session_id="s"))

    asyncio.run(_scenario())


def test_apply_patch_outside_workspace_rejected(tmp_path: Path) -> None:
    async def _scenario() -> None:
        tool = ApplyPatchTool(workspace_path=tmp_path, restrict_to_workspace=True)
        traversal_patch = "\n".join(
            [
                "*** Begin Patch",
                "*** Add File: ../escape.txt",
                "+bad",
                "*** End Patch",
            ]
        )
        with pytest.raises(ValueError, match="Path outside workspace"):
            await tool.run({"input": traversal_patch}, ToolContext(session_id="s"))

    asyncio.run(_scenario())
