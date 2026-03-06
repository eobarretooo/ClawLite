from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clawlite.tools.base import Tool, ToolContext


BEGIN_PATCH_MARKER = "*** Begin Patch"
END_PATCH_MARKER = "*** End Patch"
ADD_FILE_MARKER = "*** Add File: "
DELETE_FILE_MARKER = "*** Delete File: "
UPDATE_FILE_MARKER = "*** Update File: "
MOVE_TO_MARKER = "*** Move to: "
END_OF_FILE_MARKER = "*** End of File"


@dataclass(slots=True)
class AddOp:
    path: str
    content: str


@dataclass(slots=True)
class DeleteOp:
    path: str


@dataclass(slots=True)
class UpdateChunk:
    old_lines: list[str]
    new_lines: list[str]
    is_eof: bool


@dataclass(slots=True)
class UpdateOp:
    path: str
    move_to: str | None
    chunks: list[UpdateChunk]


PatchOp = AddOp | DeleteOp | UpdateOp


class ApplyPatchTool(Tool):
    name = "apply_patch"
    description = "Apply patch envelope with add/update/delete operations."

    def __init__(self, *, workspace_path: str | Path, restrict_to_workspace: bool = True) -> None:
        self.workspace_path = Path(workspace_path).expanduser().resolve()
        self.restrict_to_workspace = bool(restrict_to_workspace)

    def args_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input": {"type": "string"},
                "patch": {"type": "string"},
            },
            "required": ["input"],
        }

    async def run(self, arguments: dict[str, Any], ctx: ToolContext) -> str:
        del ctx
        patch_text = arguments.get("input")
        if not isinstance(patch_text, str) or not patch_text.strip():
            fallback = arguments.get("patch")
            patch_text = fallback if isinstance(fallback, str) else ""
        if not patch_text.strip():
            raise ValueError("Invalid patch: input is required")

        ops = self._parse_patch(patch_text)
        added: list[str] = []
        modified: list[str] = []
        deleted: list[str] = []

        for op in ops:
            if isinstance(op, AddOp):
                target = self._resolve_path(op.path)
                if target.exists():
                    raise ValueError(f"Invalid patch: add target already exists '{op.path}'")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(op.content, encoding="utf-8")
                added.append(self._relative(target))
                continue

            if isinstance(op, DeleteOp):
                target = self._resolve_path(op.path)
                if not target.exists():
                    raise ValueError(f"Invalid patch: delete target missing '{op.path}'")
                if not target.is_file():
                    raise ValueError(f"Invalid patch: delete target is not a file '{op.path}'")
                target.unlink()
                deleted.append(self._relative(target))
                continue

            target = self._resolve_path(op.path)
            if not target.exists() or not target.is_file():
                raise ValueError(f"Invalid patch: update target missing '{op.path}'")
            original = target.read_text(encoding="utf-8")
            updated = self._apply_update_chunks(original, op.chunks, op.path)

            final_target = target
            if op.move_to:
                move_target = self._resolve_path(op.move_to)
                if move_target.exists() and move_target != target:
                    raise ValueError(f"Invalid patch: move target already exists '{op.move_to}'")
                move_target.parent.mkdir(parents=True, exist_ok=True)
                move_target.write_text(updated, encoding="utf-8")
                if move_target != target:
                    target.unlink()
                final_target = move_target
            else:
                target.write_text(updated, encoding="utf-8")

            modified.append(self._relative(final_target))

        lines = ["Success. Updated the following files:"]
        lines.extend(f"A {path}" for path in added)
        lines.extend(f"M {path}" for path in modified)
        lines.extend(f"D {path}" for path in deleted)
        return "\n".join(lines)

    def _resolve_path(self, raw: str) -> Path:
        value = str(raw or "").strip()
        if not value:
            raise ValueError("Invalid patch: file path is required")
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = self.workspace_path / candidate
        resolved = candidate.resolve()
        if resolved != self.workspace_path and self.workspace_path not in resolved.parents:
            raise ValueError(f"Path outside workspace: {value}")
        return resolved

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.workspace_path).as_posix()

    def _parse_patch(self, patch_text: str) -> list[PatchOp]:
        lines = patch_text.splitlines()
        if not lines or lines[0].strip() != BEGIN_PATCH_MARKER:
            raise ValueError("Invalid patch: missing '*** Begin Patch' header")
        if lines[-1].strip() != END_PATCH_MARKER:
            raise ValueError("Invalid patch: missing '*** End Patch' footer")

        ops: list[PatchOp] = []
        i = 1
        while i < len(lines) - 1:
            line = lines[i]
            if not line.strip():
                i += 1
                continue

            if line.startswith(ADD_FILE_MARKER):
                path = line[len(ADD_FILE_MARKER) :].strip()
                if not path:
                    raise ValueError(f"Invalid patch: missing add file path at line {i + 1}")
                i += 1
                payload: list[str] = []
                while i < len(lines) - 1 and not lines[i].startswith("*** "):
                    row = lines[i]
                    if not row.startswith("+"):
                        raise ValueError(f"Invalid patch: malformed add file line at line {i + 1}")
                    payload.append(row[1:])
                    i += 1
                content = "\n".join(payload)
                if payload:
                    content += "\n"
                ops.append(AddOp(path=path, content=content))
                continue

            if line.startswith(DELETE_FILE_MARKER):
                path = line[len(DELETE_FILE_MARKER) :].strip()
                if not path:
                    raise ValueError(f"Invalid patch: missing delete file path at line {i + 1}")
                ops.append(DeleteOp(path=path))
                i += 1
                continue

            if line.startswith(UPDATE_FILE_MARKER):
                path = line[len(UPDATE_FILE_MARKER) :].strip()
                if not path:
                    raise ValueError(f"Invalid patch: missing update file path at line {i + 1}")
                i += 1
                move_to: str | None = None
                if i < len(lines) - 1 and lines[i].startswith(MOVE_TO_MARKER):
                    move_to = lines[i][len(MOVE_TO_MARKER) :].strip()
                    if not move_to:
                        raise ValueError(f"Invalid patch: missing move target at line {i + 1}")
                    i += 1

                chunks: list[UpdateChunk] = []
                while i < len(lines) - 1 and not lines[i].startswith("*** "):
                    if not lines[i].strip():
                        i += 1
                        continue
                    if lines[i].startswith("@@"):
                        i += 1
                    chunk, i = self._parse_update_chunk(lines, i, path)
                    chunks.append(chunk)

                if not chunks:
                    raise ValueError(f"Invalid patch: empty update hunk for '{path}'")
                ops.append(UpdateOp(path=path, move_to=move_to, chunks=chunks))
                continue

            raise ValueError(f"Invalid patch: unknown hunk header at line {i + 1}")

        return ops

    def _parse_update_chunk(self, lines: list[str], start: int, path: str) -> tuple[UpdateChunk, int]:
        i = start
        old_lines: list[str] = []
        new_lines: list[str] = []
        consumed_any = False
        eof = False

        while i < len(lines) - 1:
            row = lines[i]
            if row.startswith("*** ") or row.startswith("@@"):
                break
            if row == END_OF_FILE_MARKER:
                eof = True
                i += 1
                break
            if row == "":
                raise ValueError(f"Invalid patch: malformed update line at line {i + 1}")

            marker = row[0]
            if marker == " ":
                old_lines.append(row[1:])
                new_lines.append(row[1:])
            elif marker == "+":
                new_lines.append(row[1:])
            elif marker == "-":
                old_lines.append(row[1:])
            else:
                raise ValueError(f"Invalid patch: malformed update line at line {i + 1}")
            consumed_any = True
            i += 1

        if not consumed_any and not eof:
            raise ValueError(f"Invalid patch: empty update chunk for '{path}'")
        return UpdateChunk(old_lines=old_lines, new_lines=new_lines, is_eof=eof), i

    def _apply_update_chunks(self, original: str, chunks: list[UpdateChunk], path: str) -> str:
        had_newline = original.endswith("\n")
        lines = original.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        cursor = 0

        for chunk in chunks:
            if not chunk.old_lines:
                insertion = len(lines)
                lines[insertion:insertion] = chunk.new_lines
                cursor = insertion + len(chunk.new_lines)
                continue

            index = self._seek_chunk(lines, chunk.old_lines, cursor, chunk.is_eof)
            if index is None:
                raise ValueError(f"Failed to apply update hunk for '{path}'")
            lines[index : index + len(chunk.old_lines)] = chunk.new_lines
            cursor = index + len(chunk.new_lines)

        output = "\n".join(lines)
        if output and had_newline:
            output += "\n"
        return output

    @staticmethod
    def _seek_chunk(lines: list[str], pattern: list[str], start: int, at_eof: bool) -> int | None:
        if not pattern:
            return max(0, min(start, len(lines)))
        max_start = len(lines) - len(pattern)
        if max_start < 0:
            return None
        begin = max(0, min(start, max_start))
        if at_eof:
            begin = max_start

        for idx in range(begin, max_start + 1):
            if lines[idx : idx + len(pattern)] == pattern:
                return idx
        for idx in range(begin, max_start + 1):
            if [row.rstrip() for row in lines[idx : idx + len(pattern)]] == [row.rstrip() for row in pattern]:
                return idx
        return None
