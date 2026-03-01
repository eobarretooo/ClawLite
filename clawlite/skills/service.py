from __future__ import annotations

from dataclasses import dataclass

from clawlite.skills.discovery import discover_skill_docs


@dataclass(frozen=True)
class SkillStatus:
    name: str
    source: str
    always: bool
    available: bool
    executable: bool
    description: str


def list_skill_statuses(workspace_path: str | None = None) -> list[SkillStatus]:
    rows: list[SkillStatus] = []
    for item in discover_skill_docs(workspace_path):
        rows.append(
            SkillStatus(
                name=item.name,
                source=item.source,
                always=item.always,
                available=item.available,
                executable=item.executable,
                description=item.description,
            )
        )
    return rows

