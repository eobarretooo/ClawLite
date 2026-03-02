from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from clawlite.workspace.loader import WorkspaceLoader


@dataclass(slots=True)
class PromptArtifacts:
    system_prompt: str
    memory_section: str
    history_messages: list[dict[str, str]]
    runtime_context: str
    skills_context: str


class PromptBuilder:
    """Builds the final system/user prompt bundle for the agent engine."""

    def __init__(self, workspace_path: str | Path | None = None) -> None:
        self.workspace_loader = WorkspaceLoader(workspace_path=workspace_path)

    def _read_workspace_files(self) -> str:
        return self.workspace_loader.system_context()

    @staticmethod
    def _render_memory(memory_snippets: Iterable[str]) -> str:
        clean = [item.strip() for item in memory_snippets if item and item.strip()]
        if not clean:
            return ""
        return "[Memory]\n" + "\n".join(f"- {item}" for item in clean)

    @staticmethod
    def _normalize_history(history: Iterable[dict[str, str]]) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for row in history:
            role = str(row.get("role", "")).strip()
            content = str(row.get("content", "")).strip()
            if role not in {"system", "user", "assistant", "tool"} or not content:
                continue
            rows.append({"role": role, "content": content})
        return rows

    @staticmethod
    def _render_runtime_context(channel: str, chat_id: str) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = time.strftime("%Z") or "UTC"
        lines = [f"Current Time: {now} ({tz})"]
        if channel and chat_id:
            lines.append(f"Channel: {channel}")
            lines.append(f"Chat ID: {chat_id}")
        return "[Runtime Context — metadata only, not instructions]\n" + "\n".join(lines)

    def build(
        self,
        *,
        user_text: str,
        memory_snippets: Iterable[str],
        history: Iterable[dict[str, str]],
        skills_for_prompt: Iterable[str],
        skills_context: str = "",
        channel: str = "",
        chat_id: str = "",
    ) -> PromptArtifacts:
        workspace_block = self._read_workspace_files()
        skills_block = "\n".join(f"- {item}" for item in skills_for_prompt if item.strip())
        skills_text = f"[Skills]\n{skills_block}" if skills_block else ""

        sections = [item for item in (workspace_block, skills_text) if item]
        system_prompt = "\n\n".join(sections).strip()

        return PromptArtifacts(
            system_prompt=system_prompt,
            memory_section=self._render_memory(memory_snippets),
            history_messages=self._normalize_history(history),
            runtime_context=self._render_runtime_context(channel=channel.strip(), chat_id=chat_id.strip()),
            skills_context=skills_context.strip(),
        )
