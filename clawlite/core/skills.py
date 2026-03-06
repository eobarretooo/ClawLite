from __future__ import annotations

import json
import os
import platform
import re
import shlex
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable


_KEY_VALUE_RE = re.compile(r"^(?P<key>[A-Za-z0-9_.-]+)\s*:\s*(?P<value>.*)$")
_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_SOURCE_PRIORITY = {"builtin": 10, "marketplace": 20, "workspace": 30}


def _to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_inline_value(raw: str) -> object:
    value = raw.strip()
    if not value:
        return ""
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        return value[1:-1]
    low = value.lower()
    if low in {"true", "false"}:
        return low == "true"
    if value[0] in "[{":
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _serialize_frontmatter_value(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _extract_frontmatter_block(text: str) -> tuple[str, str] | None:
    raw = text[1:] if text.startswith("\ufeff") else text
    lines = raw.splitlines()
    if not lines:
        return None
    if lines[0].strip() != "---":
        return None

    end_idx = -1
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx == -1:
        return None

    front = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1 :])
    return front, body


def _extract_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """
    Parse markdown frontmatter without requiring PyYAML.
    Returns: (metadata, body_without_frontmatter)
    """
    data: dict[str, object] = {}
    split = _extract_frontmatter_block(text)
    if split is None:
        return data, text
    front, body = split

    current_key = ""
    current_value: list[str] = []

    def flush() -> None:
        nonlocal current_key, current_value
        if not current_key:
            return
        joined = "\n".join(current_value).rstrip()
        data[current_key] = _parse_inline_value(joined)
        current_key = ""
        current_value = []

    for raw_line in front.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _KEY_VALUE_RE.match(line)
        if match and line[: len(line) - len(line.lstrip())] == "":
            flush()
            current_key = match.group("key").strip()
            current_value = [match.group("value")]
            continue
        if current_key and line.startswith((" ", "\t")):
            current_value.append(line.lstrip())
            continue
        if current_key and not match:
            current_value.append(line)
    flush()
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


def _coerce_list(value: object, *, normalize_os: bool = False) -> tuple[list[str], list[str]]:
    if value is None:
        return [], []
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return [], []
        if raw.startswith("["):
            try:
                decoded = json.loads(raw)
            except json.JSONDecodeError:
                decoded = [item.strip() for item in raw.split(",") if item.strip()]
            value = decoded
        else:
            value = [item.strip() for item in raw.split(",") if item.strip()]

    if not isinstance(value, list):
        return [], ["requirements:expected_list"]

    out: list[str] = []
    issues: list[str] = []
    for item in value:
        text = str(item).strip()
        if not text:
            continue
        out.append(_normalize_os_name(text) if normalize_os else text)
    return out, issues


def _extract_runtime_metadata(meta: dict[str, object]) -> tuple[dict[str, object], list[str]]:
    raw = meta.get("metadata")
    if raw is None:
        return {}, []
    if isinstance(raw, Mapping):
        payload = dict(raw)
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}, []
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return {}, ["metadata:invalid_json"]
        payload = decoded if isinstance(decoded, dict) else {}
    else:
        return {}, ["metadata:invalid_type"]

    nested = payload.get("clawlite") or payload.get("nanobot") or payload.get("openclaw") or {}
    if isinstance(nested, Mapping):
        return dict(nested), []
    if nested:
        return {}, ["metadata:runtime_namespace_invalid_type"]
    return {}, []


def _extract_requirement_map(meta: dict[str, object]) -> tuple[dict[str, list[str]], list[str]]:
    out = {"bins": [], "env": [], "os": []}
    issues: list[str] = []

    legacy_bins, legacy_issues = _coerce_list(meta.get("requires"))
    out["bins"].extend(legacy_bins)
    issues.extend(legacy_issues)

    metadata_runtime, metadata_issues = _extract_runtime_metadata(meta)
    issues.extend(metadata_issues)
    if metadata_runtime:
        runtime_requires = metadata_runtime.get("requires", {})
        if isinstance(runtime_requires, Mapping):
            bins, bins_issues = _coerce_list(runtime_requires.get("bins"))
            env, env_issues = _coerce_list(runtime_requires.get("env"))
            os_items, os_issues = _coerce_list(runtime_requires.get("os"), normalize_os=True)
            out["bins"].extend(bins)
            out["env"].extend(env)
            out["os"].extend(os_items)
            issues.extend(bins_issues)
            issues.extend(env_issues)
            issues.extend(os_issues)
        elif runtime_requires:
            issues.append("requirements:metadata_requires_invalid_type")

        runtime_os, runtime_os_issues = _coerce_list(metadata_runtime.get("os"), normalize_os=True)
        out["os"].extend(runtime_os)
        issues.extend(runtime_os_issues)

    explicit_requirements = meta.get("requirements")
    if explicit_requirements is not None:
        decoded = explicit_requirements
        if isinstance(decoded, str):
            try:
                decoded = json.loads(decoded)
            except json.JSONDecodeError:
                issues.append("requirements:invalid_json")
                decoded = None
        if isinstance(decoded, Mapping):
            bins, bins_issues = _coerce_list(decoded.get("bins"))
            env, env_issues = _coerce_list(decoded.get("env"))
            os_items, os_issues = _coerce_list(decoded.get("os"), normalize_os=True)
            out["bins"].extend(bins)
            out["env"].extend(env)
            out["os"].extend(os_items)
            issues.extend(bins_issues)
            issues.extend(env_issues)
            issues.extend(os_issues)
        elif decoded is not None:
            issues.append("requirements:invalid_type")

    env_issue = "requirements:invalid_env_name"
    for item in list(out["env"]):
        if _ENV_NAME_RE.fullmatch(item):
            continue
        issues.append(f"{env_issue}:{item}")

    for key in out:
        dedupe: list[str] = []
        seen: set[str] = set()
        for item in out[key]:
            if item in seen:
                continue
            seen.add(item)
            dedupe.append(item)
        out[key] = dedupe
    unique_issues: list[str] = []
    seen_issues: set[str] = set()
    for issue in issues:
        if issue in seen_issues:
            continue
        seen_issues.add(issue)
        unique_issues.append(issue)
    return out, unique_issues


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


def _escape_xml(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _build_execution_contract(meta: Mapping[str, object]) -> tuple[str, str, list[str], list[str]]:
    """
    Build a deterministic execution contract from frontmatter.

    Returns: (kind, target, argv, issues)
    - kind: none | command | script | invalid
    """
    command = str(meta.get("command", "")).strip()
    script = str(meta.get("script", "")).strip()
    issues: list[str] = []

    if command and script:
        issues.append("contract:command_and_script_are_mutually_exclusive")
        return "invalid", "", [], issues

    if command:
        if "\n" in command or "\r" in command:
            issues.append("contract:command_contains_newline")
            return "invalid", command, [], issues
        try:
            argv = shlex.split(command)
        except ValueError:
            issues.append("contract:command_parse_error")
            return "invalid", command, [], issues
        if not argv:
            issues.append("contract:empty_command")
            return "invalid", command, [], issues
        return "command", command, argv, issues

    if script:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", script):
            issues.append("contract:invalid_script_name")
            return "invalid", script, [], issues
        return "script", script, [], issues

    return "none", "", [], issues


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
    requirements: dict[str, list[str]]
    execution_kind: str
    execution_target: str
    execution_argv: list[str]
    contract_issues: list[str]


class SkillsLoader:
    """Loads SKILL.md from builtin/workspace/marketplace skill roots."""

    def __init__(self, builtin_root: str | Path | None = None) -> None:
        default_builtin = Path(__file__).resolve().parents[1] / "skills"
        self.roots = [
            Path(builtin_root) if builtin_root else default_builtin,
            Path.home() / ".clawlite" / "workspace" / "skills",
            Path.home() / ".clawlite" / "marketplace" / "skills",
        ]
        self._discovery_signature: tuple[tuple[str, bool, int], ...] | None = None
        self._discovered_specs: list[SkillSpec] | None = None
        self._name_index: dict[str, SkillSpec] | None = None

    def _roots_signature(self) -> tuple[tuple[str, bool, int], ...]:
        signature: list[tuple[str, bool, int]] = []
        for root in self.roots:
            exists = root.exists()
            mtime = root.stat().st_mtime_ns if exists else 0
            signature.append((str(root), exists, mtime))
        return tuple(signature)

    @staticmethod
    def _refresh_runtime_status(spec: SkillSpec) -> SkillSpec:
        missing = _missing_requirements(spec.requirements)
        available = (not missing) and (not spec.contract_issues)
        if spec.missing == missing and spec.available == available:
            return spec
        return replace(spec, missing=missing, available=available)

    def _ensure_discovery_cache(self) -> None:
        signature = self._roots_signature()
        if (
            self._discovery_signature == signature
            and self._discovered_specs is not None
            and self._name_index is not None
        ):
            return

        found: dict[str, SkillSpec] = {}
        for idx, root in enumerate(self.roots):
            if not root.exists():
                continue
            source = self._source_label(root, idx)
            for path in root.rglob("SKILL.md"):
                spec = self._parse_header(path, source=source)
                if spec is None:
                    continue
                current = found.get(spec.name)
                if current is None or self._is_preferred_candidate(spec, current):
                    found[spec.name] = spec

        rows = sorted(found.values(), key=lambda item: item.name.lower())
        self._discovered_specs = rows
        self._name_index = {item.name.lower(): item for item in rows}
        self._discovery_signature = signature

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
        name = str(meta.get("name", "")).strip() or path.parent.name
        description = str(meta.get("description", "")).strip()
        always = _to_bool(meta.get("always", "false"))
        requires, _ = _coerce_list(meta.get("requires"))
        command = str(meta.get("command", "")).strip()
        script = str(meta.get("script", "")).strip()
        homepage = str(meta.get("homepage", "")).strip()

        if not name:
            return None

        req_map, req_issues = _extract_requirement_map(meta)
        missing = _missing_requirements(req_map)
        execution_kind, execution_target, execution_argv, contract_issues = _build_execution_contract(meta)
        metadata_as_text = {key: _serialize_frontmatter_value(value) for key, value in meta.items()}

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
            metadata=metadata_as_text,
            available=(not missing) and (not contract_issues) and (not req_issues),
            missing=missing,
            requirements=req_map,
            execution_kind=execution_kind,
            execution_target=execution_target,
            execution_argv=execution_argv,
            contract_issues=[*req_issues, *contract_issues],
        )

    @staticmethod
    def _is_preferred_candidate(candidate: SkillSpec, current: SkillSpec) -> bool:
        candidate_priority = _SOURCE_PRIORITY.get(candidate.source, 0)
        current_priority = _SOURCE_PRIORITY.get(current.source, 0)
        if candidate_priority != current_priority:
            return candidate_priority > current_priority
        return str(candidate.path) < str(current.path)

    def discover(self, *, include_unavailable: bool = True) -> list[SkillSpec]:
        self._ensure_discovery_cache()
        assert self._discovered_specs is not None
        rows = [self._refresh_runtime_status(item) for item in self._discovered_specs]
        if include_unavailable:
            return rows
        return [item for item in rows if item.available]

    def diagnostics_report(self) -> dict[str, object]:
        rows = self.discover(include_unavailable=True)

        execution_kinds: dict[str, int] = {
            "command": 0,
            "script": 0,
            "none": 0,
            "invalid": 0,
        }
        source_counts: dict[str, int] = {
            "builtin": 0,
            "workspace": 0,
            "marketplace": 0,
        }
        missing_groups: dict[str, dict[str, object]] = {
            "bin": {"count": 0, "items": []},
            "env": {"count": 0, "items": []},
            "os": {"count": 0, "items": []},
            "other": {"count": 0, "items": []},
        }
        missing_seen: dict[str, set[str]] = {
            "bin": set(),
            "env": set(),
            "os": set(),
            "other": set(),
        }
        contract_issue_counts: dict[str, int] = {}

        available_count = 0
        unavailable_count = 0
        always_on_available_count = 0
        always_on_unavailable_count = 0
        contract_total = 0

        skill_rows: list[dict[str, object]] = []

        for row in rows:
            if row.available:
                available_count += 1
                if row.always:
                    always_on_available_count += 1
            else:
                unavailable_count += 1
                if row.always:
                    always_on_unavailable_count += 1

            kind = row.execution_kind if row.execution_kind in execution_kinds else "invalid"
            execution_kinds[kind] += 1

            source = row.source if row.source in source_counts else "marketplace"
            source_counts[source] += 1

            if not row.available:
                for item in row.missing:
                    if item.startswith("bin:"):
                        prefix = "bin"
                    elif item.startswith("env:"):
                        prefix = "env"
                    elif item.startswith("os:"):
                        prefix = "os"
                    else:
                        prefix = "other"
                    if item not in missing_seen[prefix]:
                        missing_seen[prefix].add(item)
                        missing_groups[prefix]["items"].append(item)
                    missing_groups[prefix]["count"] = int(missing_groups[prefix]["count"]) + 1

            for issue in row.contract_issues:
                contract_total += 1
                contract_issue_counts[issue] = contract_issue_counts.get(issue, 0) + 1

            skill_rows.append(
                {
                    "name": row.name,
                    "available": row.available,
                    "source": row.source,
                    "execution_kind": row.execution_kind,
                    "missing": sorted(row.missing),
                    "contract_issues": sorted(row.contract_issues),
                }
            )

        for prefix in ("bin", "env", "os", "other"):
            missing_groups[prefix]["items"] = sorted(str(item) for item in missing_groups[prefix]["items"])

        return {
            "summary": {
                "total": len(rows),
                "available": available_count,
                "unavailable": unavailable_count,
                "always_on_available": always_on_available_count,
                "always_on_unavailable": always_on_unavailable_count,
            },
            "execution_kinds": execution_kinds,
            "sources": source_counts,
            "missing_requirements": missing_groups,
            "contract_issues": {
                "total": contract_total,
                "by_key": {key: contract_issue_counts[key] for key in sorted(contract_issue_counts)},
            },
            "skills": sorted(skill_rows, key=lambda item: str(item["name"]).lower()),
        }

    def always_on(self, *, only_available: bool = True) -> list[SkillSpec]:
        rows = self.discover(include_unavailable=not only_available)
        return [item for item in rows if item.always and (item.available or not only_available)]

    def get(self, name: str) -> SkillSpec | None:
        self._ensure_discovery_cache()
        assert self._name_index is not None
        wanted = name.strip().lower()
        row = self._name_index.get(wanted)
        if row is None:
            return None
        return self._refresh_runtime_status(row)

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
        lines = ["<available_skills>"]
        for skill in self.discover(include_unavailable=include_unavailable):
            if not skill.available and not include_unavailable:
                continue
            if selected_set and skill.name not in selected_set and not skill.always:
                continue
            lines.append("<skill>")
            lines.append(f"<name>{_escape_xml(skill.name)}</name>")
            lines.append(f"<description>{_escape_xml(skill.description or 'no description')}</description>")
            lines.append(f"<location>{_escape_xml(str(skill.path))}</location>")
            if include_unavailable and not skill.available:
                missing = ", ".join([*skill.missing, *skill.contract_issues])
                lines.append(f"<requires>{_escape_xml(missing)}</requires>")
            lines.append("</skill>")
        lines.append("</available_skills>")
        return ["\n".join(lines)]
