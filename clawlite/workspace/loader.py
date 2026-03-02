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
        self.templates = Path(template_root) if template_root else Path(__file__).resolve().parent / "templates"

    @staticmethod
    def _render(template: str, variables: dict[str, str]) -> str:
        rendered = template
        for key, value in variables.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        return rendered

    def sync_templates(
        self,
        *,
        variables: dict[str, str] | None = None,
        update_existing: bool = False,
    ) -> dict[str, list[Path]]:
        values = dict(DEFAULT_VARS)
        values.update({k: str(v) for k, v in (variables or {}).items()})

        created: list[Path] = []
        updated: list[Path] = []
        skipped: list[Path] = []

        self.workspace.mkdir(parents=True, exist_ok=True)

        for rel in TEMPLATE_FILES:
            src = self.templates / rel
            dst = self.workspace / rel
            if not src.exists():
                continue

            rendered = self._render(src.read_text(encoding="utf-8"), values)
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(rendered, encoding="utf-8")
                created.append(dst)
                continue

            current = dst.read_text(encoding="utf-8", errors="ignore")
            if current == rendered:
                skipped.append(dst)
                continue

            if update_existing:
                dst.write_text(rendered, encoding="utf-8")
                updated.append(dst)
            else:
                skipped.append(dst)

        return {
            "created": sorted(created),
            "updated": sorted(updated),
            "skipped": sorted(skipped),
        }

    def bootstrap(self, *, variables: dict[str, str] | None = None, overwrite: bool = False) -> list[Path]:
        result = self.sync_templates(variables=variables, update_existing=overwrite)
        return [*result["created"], *result["updated"]]

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

    def bootstrap_path(self) -> Path:
        return self.workspace / "BOOTSTRAP.md"

    def should_run_bootstrap(self) -> bool:
        path = self.bootstrap_path()
        if not path.exists():
            return False
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        return bool(text)

    def bootstrap_prompt(self) -> str:
        path = self.bootstrap_path()
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="ignore").strip()

    def complete_bootstrap(self) -> bool:
        path = self.bootstrap_path()
        if not path.exists():
            return False
        path.unlink()
        return True

    def heartbeat_prompt(self) -> str:
        path = self.workspace / "HEARTBEAT.md"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="ignore").strip()

    def system_context(self, *, include_heartbeat: bool = True, include_bootstrap: bool = True) -> str:
        files = ["IDENTITY.md", "SOUL.md", "AGENTS.md", "TOOLS.md", "USER.md"]
        if include_heartbeat:
            files.append("HEARTBEAT.md")
        if include_bootstrap and self.should_run_bootstrap():
            files.append("BOOTSTRAP.md")

        docs = self.read(files)
        docs = self.read(files)
        parts = [f"## {name}\n{text}" for name, text in docs.items()]
        return "\n\n".join(parts).strip()
