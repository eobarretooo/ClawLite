from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
from typing import Any


@dataclass
class DiscoveredSkill:
    name: str
    path: str
    source: str
    description: str
    always: bool
    requires_bins: list[str]
    requires_env: list[str]
    available: bool


def _extract_frontmatter(content: str) -> str:
    text = str(content or "")
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    return parts[1]


def _parse_frontmatter(frontmatter: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_section: str | None = None
    current_subsection: str | None = None

    for raw_line in frontmatter.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        if stripped.startswith("- "):
            value = stripped[2:].strip().strip("\"'")
            if current_section and current_subsection:
                section = data.setdefault(current_section, {})
                if isinstance(section, dict):
                    section.setdefault(current_subsection, [])
                    if isinstance(section[current_subsection], list):
                        section[current_subsection].append(value)
            elif current_section:
                section = data.setdefault(current_section, [])
                if isinstance(section, list):
                    section.append(value)
            continue

        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip().strip("\"'")

        if indent == 0:
            current_section = key
            current_subsection = None
            if value:
                data[key] = value
            else:
                data.setdefault(key, {})
            continue

        if current_section and indent >= 2:
            section = data.setdefault(current_section, {})
            if not isinstance(section, dict):
                continue
            if value:
                section[key] = value
                current_subsection = None
            else:
                section.setdefault(key, [])
                current_subsection = key

    return data


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    raw = str(value or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _requirements_met(bins: list[str], envs: list[str]) -> bool:
    for name in bins:
        if not shutil.which(name):
            return False
    for key in envs:
        if not os.environ.get(key):
            return False
    return True


def _workspace_skills_roots(workspace_path: str | Path | None = None) -> list[tuple[Path, str]]:
    roots: list[tuple[Path, str]] = []
    if workspace_path:
        ws_root = Path(workspace_path).expanduser()
        roots.append((ws_root / "skills", "workspace"))
    roots.append((Path.home() / ".clawlite" / "workspace" / "skills", "workspace"))
    roots.append((Path.home() / ".clawlite" / "marketplace" / "skills", "marketplace"))
    return roots


def discover_skill_docs(workspace_path: str | Path | None = None) -> list[DiscoveredSkill]:
    rows: dict[str, DiscoveredSkill] = {}
    for root, source in _workspace_skills_roots(workspace_path):
        if not root.exists() or not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            skill_file = child / "SKILL.md"
            if not skill_file.exists():
                continue
            try:
                content = skill_file.read_text(encoding="utf-8")
            except Exception:
                continue

            frontmatter = _parse_frontmatter(_extract_frontmatter(content))
            name = str(frontmatter.get("name") or child.name).strip().lower()
            description = str(frontmatter.get("description") or "").strip() or f"Skill '{name}'"
            always = _as_bool(frontmatter.get("always"), False)

            requires_obj = frontmatter.get("requires", {})
            bins: list[str] = []
            envs: list[str] = []
            if isinstance(requires_obj, dict):
                bins = _as_str_list(requires_obj.get("bins"))
                envs = _as_str_list(requires_obj.get("env"))
            available = _requirements_met(bins, envs)

            rows[name] = DiscoveredSkill(
                name=name,
                path=str(skill_file),
                source=source,
                description=description,
                always=always,
                requires_bins=bins,
                requires_env=envs,
                available=available,
            )
    return sorted(rows.values(), key=lambda row: row.name)


def always_loaded_skills(workspace_path: str | Path | None = None) -> list[DiscoveredSkill]:
    return [row for row in discover_skill_docs(workspace_path) if row.always and row.available]


def build_skills_summary(workspace_path: str | Path | None = None, max_items: int = 40) -> str:
    rows = discover_skill_docs(workspace_path)
    if not rows:
        return ""

    always = [row for row in rows if row.always and row.available][:max_items]
    optional = [row for row in rows if not row.always][:max_items]
    lines: list[str] = []

    if always:
        lines.append("Always-loaded skills:")
        for row in always:
            lines.append(f"- {row.name}: {row.description[:140]} ({row.source})")

    if optional:
        if lines:
            lines.append("")
        lines.append("Discoverable skills (SKILL.md):")
        for row in optional:
            availability = "available" if row.available else "missing-requirements"
            requires = []
            if row.requires_bins:
                requires.append(f"bins={','.join(row.requires_bins)}")
            if row.requires_env:
                requires.append(f"env={','.join(row.requires_env)}")
            req = f" | requires: {'; '.join(requires)}" if requires else ""
            lines.append(f"- {row.name}: {availability}{req}")

    return "\n".join(lines).strip()
