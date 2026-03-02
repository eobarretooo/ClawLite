from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(slots=True)
class SkillSpec:
    name: str
    description: str
    always: bool
    requires: list[str]
    path: Path


class SkillsLoader:
    """Loads SKILL.md from builtin/workspace/marketplace skill roots."""

    def __init__(self, builtin_root: str | Path | None = None) -> None:
        default_builtin = Path(__file__).resolve().parents[1] / "skills"
        self.roots = [
            Path(builtin_root) if builtin_root else default_builtin,
            Path.home() / ".clawlite" / "workspace" / "skills",
            Path.home() / ".clawlite" / "marketplace" / "skills",
        ]

    @staticmethod
    def _parse_header(path: Path) -> SkillSpec | None:
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        name = path.parent.name
        description = ""
        always = False
        requires: list[str] = []

        in_frontmatter = False
        if lines and lines[0].strip() == "---":
            in_frontmatter = True

        for line in lines[1:] if in_frontmatter else lines:
            stripped = line.strip()
            if in_frontmatter and stripped == "---":
                break
            if stripped.startswith("name:"):
                value = stripped.split(":", 1)[1].strip()
                if value:
                    name = value
            elif stripped.startswith("description:"):
                description = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("always:"):
                always = stripped.split(":", 1)[1].strip().lower() == "true"
            elif stripped.startswith("requires:"):
                raw = stripped.split(":", 1)[1].strip()
                requires = [item.strip() for item in raw.split(",") if item.strip()]

        if not name:
            return None

        return SkillSpec(
            name=name,
            description=description,
            always=always,
            requires=requires,
            path=path,
        )

    def discover(self) -> list[SkillSpec]:
        found: dict[str, SkillSpec] = {}
        for root in self.roots:
            if not root.exists():
                continue
            for path in root.rglob("SKILL.md"):
                spec = self._parse_header(path)
                if spec is None:
                    continue
                found[spec.name] = spec
        return sorted(found.values(), key=lambda item: item.name.lower())

    def always_on(self) -> list[SkillSpec]:
        return [item for item in self.discover() if item.always]

    def render_for_prompt(self, selected: Iterable[str] | None = None) -> list[str]:
        selected_set = {item.strip() for item in (selected or []) if item.strip()}
        rows: list[str] = []
        for skill in self.discover():
            if selected_set and skill.name not in selected_set and not skill.always:
                continue
            desc = skill.description or "no description"
            rows.append(f"{skill.name}: {desc}")
        return rows
