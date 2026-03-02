from __future__ import annotations

from pathlib import Path
from typing import Iterable

TEMPLATE_FILES = (
    "IDENTITY.md",
    "SOUL.md",
    "USER.md",
    "AGENTS.md",
    "TOOLS.md",
    "HEARTBEAT.md",
    "BOOTSTRAP.md",
    "memory/MEMORY.md",
)

DEFAULT_VARS = {
    "assistant_name": "ClawLite",
    "assistant_emoji": "🦊",
    "assistant_creature": "fox",
    "assistant_vibe": "direct, pragmatic, autonomous",
    "assistant_backstory": "An autonomous personal assistant focused on execution.",
    "user_name": "Owner",
    "user_timezone": "UTC",
    "user_context": "Personal operations and software projects",
    "user_preferences": "Clear answers, direct actions, concise updates",
}


class WorkspaceLoader:
    def __init__(self, workspace_path: str | Path | None = None, template_root: str | Path | None = None) -> None:
        self.workspace = Path(workspace_path) if workspace_path else (Path.home() / ".clawlite" / "workspace")
        self.templates = (
            Path(template_root)
            if template_root
            else Path(__file__).resolve().parent / "templates"
        )

    @staticmethod
    def _render(template: str, variables: dict[str, str]) -> str:
        rendered = template
        for key, value in variables.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        return rendered

    def bootstrap(self, *, variables: dict[str, str] | None = None, overwrite: bool = False) -> list[Path]:
        values = dict(DEFAULT_VARS)
        values.update({k: str(v) for k, v in (variables or {}).items()})
        created: list[Path] = []
        self.workspace.mkdir(parents=True, exist_ok=True)

        for rel in TEMPLATE_FILES:
            src = self.templates / rel
            dst = self.workspace / rel
            if not src.exists():
                continue
            if dst.exists() and not overwrite:
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            text = src.read_text(encoding="utf-8")
            dst.write_text(self._render(text, values), encoding="utf-8")
            created.append(dst)
        return created

    def read(self, filenames: Iterable[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for filename in filenames:
            path = self.workspace / filename
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
            if text:
                out[filename] = text
        return out

    def system_context(self) -> str:
        docs = self.read(["IDENTITY.md", "SOUL.md", "AGENTS.md", "TOOLS.md", "USER.md"])
        parts = [f"## {name}\n{text}" for name, text in docs.items()]
        return "\n\n".join(parts).strip()
