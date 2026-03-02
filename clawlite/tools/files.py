from __future__ import annotations

from pathlib import Path

from clawlite.tools.base import Tool, ToolContext


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
            raise PermissionError(f"path_outside_workspace:{path}")
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
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        path = _safe_path(
            str(arguments.get("path", "")),
            workspace=self.workspace,
            restrict_to_workspace=self.restrict_to_workspace,
        )
        if not path.exists():
            raise FileNotFoundError(str(path))
        return path.read_text(encoding="utf-8", errors="ignore")


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
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
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
            raise FileNotFoundError(str(path))
        old = path.read_text(encoding="utf-8", errors="ignore")
        search = str(arguments.get("search", ""))
        replace = str(arguments.get("replace", ""))
        if search not in old:
            return "no_change"
        new = old.replace(search, replace)
        path.write_text(new, encoding="utf-8")
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
        return "\n".join(rows)
