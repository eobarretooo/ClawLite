from __future__ import annotations

import difflib
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from clawlite.tools.base import Tool, ToolContext
from clawlite.utils.logging import bind_event, setup_logging

setup_logging()


DEFAULT_MAX_READ_BYTES = 512 * 1024
DEFAULT_MAX_EDIT_BYTES = 512 * 1024
DEFAULT_MAX_WRITE_BYTES = 1024 * 1024
MAX_READ_CHUNK_BYTES = 512 * 1024


class FileToolError(Exception):
    def __init__(self, code: str, message: str, *, path: Path | None = None, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path
        self.details = details

    def __str__(self) -> str:
        parts = [f"file_error:{self.code}", f"message={self.message}"]
        if self.path is not None:
            parts.append(f"path={self.path}")
        for key, value in sorted(self.details.items()):
            parts.append(f"{key}={value}")
        return " | ".join(parts)


class FileToolPermissionError(PermissionError):
    def __init__(self, code: str, message: str, *, path: Path | None = None, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path
        self.details = details

    def __str__(self) -> str:
        parts = [f"file_error:{self.code}", f"message={self.message}"]
        if self.path is not None:
            parts.append(f"path={self.path}")
        for key, value in sorted(self.details.items()):
            parts.append(f"{key}={value}")
        return " | ".join(parts)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name: str | None = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            tmp_name = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if tmp_name:
            tmp_path = Path(tmp_name)
            if tmp_path.exists() and tmp_path != path:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass


def _build_not_found_message(search: str, content: str, path: Path) -> str:
    lines = content.splitlines(keepends=True)
    search_lines = search.splitlines(keepends=True)
    window = max(1, len(search_lines))

    best_ratio = 0.0
    best_start = 0
    upper_bound = max(1, len(lines) - window + 1)
    for idx in range(upper_bound):
        candidate_lines = lines[idx : idx + window]
        ratio = difflib.SequenceMatcher(None, search, "".join(candidate_lines)).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_start = idx

    if best_ratio <= 0.5:
        return "search text not found and no close match was detected"

    diff = "\n".join(
        difflib.unified_diff(
            search_lines,
            lines[best_start : best_start + window],
            fromfile="search (provided)",
            tofile=f"{path} (actual, line {best_start + 1})",
            lineterm="",
        )
    )
    return f"search text not found; best match {best_ratio:.0%} at line {best_start + 1}\n{diff}"


def _workspace_path(raw_workspace: str | Path | None) -> Path | None:
    if raw_workspace is None:
        return None
    return Path(raw_workspace).expanduser().resolve()


def _safe_path(
    raw_path: str,
    *,
    workspace: Path | None = None,
    restrict_to_workspace: bool = False,
) -> Path:
    candidate = Path(raw_path).expanduser()
    if workspace is not None and not candidate.is_absolute():
        candidate = workspace / candidate
    path = candidate.resolve()
    if restrict_to_workspace and workspace is not None:
        if path != workspace and workspace not in path.parents:
            raise FileToolPermissionError(
                "path_outside_workspace",
                "resolved path is outside configured workspace",
                path=path,
                workspace=workspace,
            )
    return path


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read text file content."

    def __init__(self, *, workspace_path: str | Path | None = None, restrict_to_workspace: bool = False) -> None:
        self.workspace = _workspace_path(workspace_path)
        self.restrict_to_workspace = bool(restrict_to_workspace)

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_READ_CHUNK_BYTES},
                "allow_large_file": {"type": "boolean", "default": False},
            },
            "required": ["path"],
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        path = _safe_path(
            str(arguments.get("path", "")),
            workspace=self.workspace,
            restrict_to_workspace=self.restrict_to_workspace,
        )
        if not path.exists():
            raise FileNotFoundError(f"file_error:not_found | path={path}")
        if not path.is_file():
            raise FileToolError("not_a_file", "path is not a regular file", path=path)

        offset = int(arguments.get("offset", 0) or 0)
        limit_raw = arguments.get("limit")
        allow_large_file = bool(arguments.get("allow_large_file", False))
        if offset < 0:
            raise FileToolError("invalid_offset", "offset must be >= 0", path=path, offset=offset)

        file_size = path.stat().st_size
        if file_size > DEFAULT_MAX_READ_BYTES and not allow_large_file and limit_raw is None:
            raise FileToolError(
                "large_file_guard",
                "file exceeds default read budget; provide limit or allow_large_file=true",
                path=path,
                file_size=file_size,
                max_bytes=DEFAULT_MAX_READ_BYTES,
            )

        limit = MAX_READ_CHUNK_BYTES if limit_raw is None else int(limit_raw)
        if limit <= 0:
            raise FileToolError("invalid_limit", "limit must be >= 1", path=path, limit=limit)
        if limit > MAX_READ_CHUNK_BYTES:
            raise FileToolError(
                "limit_too_large",
                "limit exceeds maximum read chunk size",
                path=path,
                limit=limit,
                max_limit=MAX_READ_CHUNK_BYTES,
            )

        bind_event("tool.files", session=ctx.session_id, tool=self.name).debug("read file path={}", path)
        with path.open("rb") as handle:
            handle.seek(offset)
            chunk = handle.read(limit)
        return chunk.decode("utf-8", errors="ignore")


class WriteFileTool(Tool):
    name = "write_file"
    description = "Write text file content."

    def __init__(self, *, workspace_path: str | Path | None = None, restrict_to_workspace: bool = False) -> None:
        self.workspace = _workspace_path(workspace_path)
        self.restrict_to_workspace = bool(restrict_to_workspace)

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "allow_large_file": {"type": "boolean", "default": False},
            },
            "required": ["path", "content"],
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        path = _safe_path(
            str(arguments.get("path", "")),
            workspace=self.workspace,
            restrict_to_workspace=self.restrict_to_workspace,
        )
        content = str(arguments.get("content", ""))
        allow_large_file = bool(arguments.get("allow_large_file", False))
        content_bytes = len(content.encode("utf-8"))
        if content_bytes > DEFAULT_MAX_WRITE_BYTES and not allow_large_file:
            raise FileToolError(
                "large_write_guard",
                "content exceeds default write budget; set allow_large_file=true to override",
                path=path,
                content_bytes=content_bytes,
                max_bytes=DEFAULT_MAX_WRITE_BYTES,
            )
        _atomic_write_text(path, content)
        bind_event("tool.files", session=ctx.session_id, tool=self.name).info("write file path={}", path)
        return f"ok:{path}"


class EditFileTool(Tool):
    name = "edit_file"
    description = "Replace text in a file."

    def __init__(self, *, workspace_path: str | Path | None = None, restrict_to_workspace: bool = False) -> None:
        self.workspace = _workspace_path(workspace_path)
        self.restrict_to_workspace = bool(restrict_to_workspace)

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "search": {"type": "string"},
                "replace": {"type": "string"},
                "allow_large_file": {"type": "boolean", "default": False},
            },
            "required": ["path", "search", "replace"],
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        path = _safe_path(
            str(arguments.get("path", "")),
            workspace=self.workspace,
            restrict_to_workspace=self.restrict_to_workspace,
        )
        if not path.exists():
            raise FileNotFoundError(f"file_error:not_found | path={path}")
        if not path.is_file():
            raise FileToolError("not_a_file", "path is not a regular file", path=path)

        file_size = path.stat().st_size
        allow_large_file = bool(arguments.get("allow_large_file", False))
        if file_size > DEFAULT_MAX_EDIT_BYTES and not allow_large_file:
            raise FileToolError(
                "large_edit_guard",
                "file exceeds default edit budget; set allow_large_file=true to override",
                path=path,
                file_size=file_size,
                max_bytes=DEFAULT_MAX_EDIT_BYTES,
            )

        old = path.read_text(encoding="utf-8", errors="ignore")
        search = str(arguments.get("search", ""))
        replace = str(arguments.get("replace", ""))
        if not search:
            raise FileToolError("invalid_search", "search must be a non-empty string", path=path)

        count = old.count(search)
        if count == 0:
            raise FileToolError("search_not_found", _build_not_found_message(search, old, path), path=path)
        if count > 1:
            raise FileToolError(
                "search_not_unique",
                "search appears multiple times; provide more unique context",
                path=path,
                occurrences=count,
            )

        new = old.replace(search, replace, 1)
        _atomic_write_text(path, new)
        bind_event("tool.files", session=ctx.session_id, tool=self.name).info("edit file path={}", path)
        return "ok"


class ListDirTool(Tool):
    name = "list_dir"
    description = "List files from directory."

    def __init__(self, *, workspace_path: str | Path | None = None, restrict_to_workspace: bool = False) -> None:
        self.workspace = _workspace_path(workspace_path)
        self.restrict_to_workspace = bool(restrict_to_workspace)

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"path": {"type": "string", "default": "."}},
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        raw = str(arguments.get("path", "."))
        path = _safe_path(
            raw,
            workspace=self.workspace,
            restrict_to_workspace=self.restrict_to_workspace,
        )
        if not path.exists() or not path.is_dir():
            raise NotADirectoryError(str(path))
        rows = sorted(item.name for item in path.iterdir())
        bind_event("tool.files", session=ctx.session_id, tool=self.name).debug("list dir path={} count={}", path, len(rows))
        return "\n".join(rows)
