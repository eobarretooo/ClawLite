from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from clawlite.tools.base import ToolContext
from clawlite.tools.files import EditFileTool, FileToolError, ReadFileTool, WriteFileTool


def test_edit_requires_unique_exact_match(tmp_path: Path) -> None:
    async def _scenario() -> None:
        target = tmp_path / "dup.txt"
        target.write_text("alpha\nbeta\nalpha\n", encoding="utf-8")
        editor = EditFileTool()

        with pytest.raises(FileToolError) as exc_info:
            await editor.run(
                {"path": str(target), "search": "alpha", "replace": "ALPHA"},
                ToolContext(session_id="s"),
            )

        assert exc_info.value.code == "search_not_unique"

    asyncio.run(_scenario())


def test_edit_missing_text_returns_fuzzy_diagnostics(tmp_path: Path) -> None:
    async def _scenario() -> None:
        target = tmp_path / "sample.txt"
        target.write_text("line one\nline two\nline three\n", encoding="utf-8")
        editor = EditFileTool()

        with pytest.raises(FileToolError) as exc_info:
            await editor.run(
                {"path": str(target), "search": "line too\n", "replace": "line 2\n"},
                ToolContext(session_id="s"),
            )

        assert exc_info.value.code == "search_not_found"
        assert "best match" in str(exc_info.value)
        assert "search (provided)" in str(exc_info.value)

    asyncio.run(_scenario())


def test_read_large_file_requires_limit_or_override(tmp_path: Path) -> None:
    async def _scenario() -> None:
        target = tmp_path / "large.txt"
        payload = "a" * (600 * 1024)
        target.write_text(payload, encoding="utf-8")
        reader = ReadFileTool()

        with pytest.raises(FileToolError) as exc_info:
            await reader.run({"path": str(target)}, ToolContext(session_id="s"))

        assert exc_info.value.code == "large_file_guard"

        chunk = await reader.run({"path": str(target), "limit": 128}, ToolContext(session_id="s"))
        assert len(chunk) == 128

    asyncio.run(_scenario())


def test_write_large_content_requires_override(tmp_path: Path) -> None:
    async def _scenario() -> None:
        target = tmp_path / "large_write.txt"
        writer = WriteFileTool()
        payload = "b" * (1100 * 1024)

        with pytest.raises(FileToolError) as exc_info:
            await writer.run({"path": str(target), "content": payload}, ToolContext(session_id="s"))

        assert exc_info.value.code == "large_write_guard"

        ok = await writer.run(
            {"path": str(target), "content": payload, "allow_large_file": True},
            ToolContext(session_id="s"),
        )
        assert ok.startswith("ok:")
        assert target.stat().st_size >= 1100 * 1024

    asyncio.run(_scenario())
