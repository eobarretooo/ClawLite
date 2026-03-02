from __future__ import annotations

from pathlib import Path

from clawlite.tools.base import Tool, ToolContext


def _safe_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser().resolve()
    return path


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read text file content."

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        path = _safe_path(str(arguments.get("path", "")))
        if not path.exists():
            raise FileNotFoundError(str(path))
        return path.read_text(encoding="utf-8", errors="ignore")


class WriteFileTool(Tool):
    name = "write_file"
    description = "Write text file content."

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
        path = _safe_path(str(arguments.get("path", "")))
        content = str(arguments.get("content", ""))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"ok:{path}"


class EditFileTool(Tool):
    name = "edit_file"
    description = "Replace text in a file."

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
        path = _safe_path(str(arguments.get("path", "")))
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

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"path": {"type": "string", "default": "."}},
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        raw = str(arguments.get("path", "."))
        path = _safe_path(raw)
        if not path.exists() or not path.is_dir():
            raise NotADirectoryError(str(path))
        rows = sorted(item.name for item in path.iterdir())
        return "\n".join(rows)
