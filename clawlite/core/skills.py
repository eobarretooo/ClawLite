from __future__ import annotations

import json
import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


def _to_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _extract_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """
    Parse markdown frontmatter without requiring PyYAML.
    Returns: (metadata, body_without_frontmatter)
    """
    data: dict[str, str] = {}
    body = text
    if not text.startswith("---\n"):
        return data, body
    marker = "\n---\n"
    end = text.find(marker, 4)
    if end == -1:
        return data, body
    front = text[4:end]
    body = text[end + len(marker) :]
    for line in front.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip("'").strip('"')
    return data, body


def _normalize_os_name(name: str) -> str:
    raw = name.strip().lower()
    if raw in {"darwin", "mac", "macos"}:
        return "darwin"
    if raw in {"linux"}:
        return "linux"
    if raw in {"windows", "win32", "win"}:
        return "windows"
    return raw


def _extract_requirement_map(meta: dict[str, str]) -> dict[str, list[str]]:
    out = {"bins": [], "env": [], "os": []}

    raw_requires = meta.get("requires", "")
    if raw_requires:
        out["bins"].extend([item.strip() for item in raw_requires.split(",") if item.strip()])

    raw_metadata = meta.get("metadata", "")
    if raw_metadata:
        try:
            payload = json.loads(raw_metadata)
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            nested = payload.get("nanobot") or payload.get("openclaw") or payload.get("clawlite") or {}
            if isinstance(nested, dict):
                requires = nested.get("requires", {})
                if isinstance(requires, dict):
                    bins = requires.get("bins", [])
                    env = requires.get("env", [])
                    if isinstance(bins, list):
                        out["bins"].extend(str(item).strip() for item in bins if str(item).strip())
                    if isinstance(env, list):
                        out["env"].extend(str(item).strip() for item in env if str(item).strip())
                os_list = nested.get("os", [])
                if isinstance(os_list, list):
                    out["os"].extend(_normalize_os_name(str(item)) for item in os_list if str(item).strip())

    for key in out:
        dedupe: list[str] = []
        seen: set[str] = set()
        for item in out[key]:
            if item in seen:
                continue
            seen.add(item)
            dedupe.append(item)
        out[key] = dedupe
    return out


def _missing_requirements(requirements: dict[str, list[str]]) -> list[str]:
    missing: list[str] = []
    for binary in requirements["bins"]:
        if shutil.which(binary) is None:
            missing.append(f"bin:{binary}")
    for env_key in requirements["env"]:
        if not os.getenv(env_key):
            missing.append(f"env:{env_key}")
    supported_oses = requirements["os"]
    if supported_oses:
        current = _normalize_os_name(platform.system())
        if current not in supported_oses:
            missing.append(f"os:{current} not in {','.join(supported_oses)}")
    return missing


@dataclass(slots=True)
class SkillSpec:
    name: str
    description: str
    always: bool
    requires: list[str]  # kept for backward compatibility
    path: Path
    source: str
    command: str
    script: str
    homepage: str
    body: str
    metadata: dict[str, str]
    available: bool
    missing: list[str]


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
    def _source_label(root: Path, index: int) -> str:
        if index == 0:
            return "builtin"
        if "workspace" in str(root):
            return "workspace"
        return "marketplace"

    @staticmethod
    def _parse_header(path: Path, *, source: str) -> SkillSpec | None:
        text = path.read_text(encoding="utf-8", errors="ignore")
        meta, body = _extract_frontmatter(text)
        name = meta.get("name", "").strip() or path.parent.name
        description = meta.get("description", "").strip()
        always = _to_bool(meta.get("always", "false"))
        requires = [item.strip() for item in meta.get("requires", "").split(",") if item.strip()]
        command = meta.get("command", "").strip()
        script = meta.get("script", "").strip()
        homepage = meta.get("homepage", "").strip()

        if not name:
            return None

        req_map = _extract_requirement_map(meta)
        missing = _missing_requirements(req_map)

        return SkillSpec(
            name=name,
            description=description,
            always=always,
            requires=requires,
            path=path,
            source=source,
            command=command,
            script=script,
            homepage=homepage,
            body=body.strip(),
            metadata=meta,
            available=not missing,
            missing=missing,
        )

    def discover(self, *, include_unavailable: bool = True) -> list[SkillSpec]:
        found: dict[str, SkillSpec] = {}
        for idx, root in enumerate(self.roots):
            if not root.exists():
                continue
            source = self._source_label(root, idx)
            for path in root.rglob("SKILL.md"):
                spec = self._parse_header(path, source=source)
                if spec is None:
                    continue
                found[spec.name] = spec
        rows = sorted(found.values(), key=lambda item: item.name.lower())
        if include_unavailable:
            return rows
        return [item for item in rows if item.available]

    def always_on(self, *, only_available: bool = True) -> list[SkillSpec]:
        rows = self.discover(include_unavailable=not only_available)
        return [item for item in rows if item.always and (item.available or not only_available)]

    def get(self, name: str) -> SkillSpec | None:
        wanted = name.strip().lower()
        for row in self.discover(include_unavailable=True):
            if row.name.lower() == wanted:
                return row
        return None

    def load_skill_content(self, name: str) -> str | None:
        spec = self.get(name)
        if spec is None:
            return None
        return spec.body

    def load_skills_for_context(self, skill_names: Iterable[str]) -> str:
        parts: list[str] = []
        for name in skill_names:
            spec = self.get(name)
            if spec is None or not spec.body:
                continue
            parts.append(f"### Skill: {spec.name}\n\n{spec.body}")
        return "\n\n---\n\n".join(parts)

    def render_for_prompt(self, selected: Iterable[str] | None = None, *, include_unavailable: bool = False) -> list[str]:
        selected_set = {item.strip() for item in (selected or []) if item.strip()}
        rows: list[str] = []
        for skill in self.discover(include_unavailable=include_unavailable):
            if not skill.available and not include_unavailable:
                continue
            if selected_set and skill.name not in selected_set and not skill.always:
                continue
            desc = skill.description or "no description"
            availability = "available" if skill.available else f"unavailable({'; '.join(skill.missing)})"
            command = ""
            if skill.command:
                command = f", command={skill.command}"
            elif skill.script:
                command = f", script={skill.script}"
            rows.append(f"{skill.name}: {desc} [{availability}, source={skill.source}{command}]")
        return rows
