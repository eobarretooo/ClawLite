from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import time
import hashlib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

import yaml


_KEY_VALUE_RE = re.compile(r"^(?P<key>[A-Za-z0-9_.-]+)\s*:\s*(?P<value>.*)$")
_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_SOURCE_PRIORITY = {"builtin": 10, "marketplace": 20, "workspace": 30}
_SKILL_STATUS_PRIORITY = {
    "missing_requirements": 10,
    "policy_blocked": 20,
    "invalid_contract": 30,
    "unavailable": 40,
    "ready": 50,
    "disabled": 60,
}
_ACTIVE_CONFIG_CACHE: dict[str, object] = {
    "path": "",
    "profile": "",
    "mtime_ns": -1,
    "profile_mtime_ns": -1,
    "payload": {},
}


def _resolved_home() -> Path:
    home_env = str(os.getenv("HOME", "") or "").strip()
    if home_env:
        return Path(home_env).expanduser()
    userprofile = str(os.getenv("USERPROFILE", "") or "").strip()
    if userprofile:
        return Path(userprofile).expanduser()
    home_drive = str(os.getenv("HOMEDRIVE", "") or "").strip()
    home_path = str(os.getenv("HOMEPATH", "") or "").strip()
    if home_drive and home_path:
        return Path(f"{home_drive}{home_path}").expanduser()
    return Path.home()


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


def _extract_frontmatter_legacy(front: str) -> dict[str, object]:
    data: dict[str, object] = {}
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
    return data


def _extract_frontmatter(text: str) -> tuple[dict[str, object], str]:
    split = _extract_frontmatter_block(text)
    if split is None:
        return {}, text
    front, body = split
    try:
        payload = yaml.safe_load(front)
    except yaml.YAMLError:
        return _extract_frontmatter_legacy(front), body
    if payload is None:
        return {}, body
    if not isinstance(payload, Mapping):
        return {}, body
    return dict(payload), body


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


def _coerce_env_names(value: object) -> tuple[list[str], list[str]]:
    rows, issues = _coerce_list(value)
    out: list[str] = []
    for item in rows:
        if _ENV_NAME_RE.fullmatch(item):
            out.append(item)
            continue
        issues.append(f"requirements:invalid_env_name:{item}")
    return out, issues


def _resolve_active_config_payload(
    config_path: str | Path | None = None,
    *,
    profile: str | None = None,
) -> dict[str, object]:
    from clawlite.config.loader import DEFAULT_CONFIG_PATH, _normalize_profile_name, _profile_path, load_raw_config_payload

    raw_path = str(config_path or "").strip()
    if not raw_path:
        raw_path = os.getenv("CLAWLITE_CONFIG", "").strip()
    path = Path(raw_path).expanduser() if raw_path else DEFAULT_CONFIG_PATH
    try:
        resolved_profile = _normalize_profile_name(profile if profile is not None else os.getenv("CLAWLITE_PROFILE", ""))
    except RuntimeError:
        resolved_profile = ""
    try:
        stat = path.stat()
        mtime_ns = int(stat.st_mtime_ns)
    except OSError:
        mtime_ns = -1
    profile_mtime_ns = -1
    if resolved_profile:
        try:
            profile_mtime_ns = int(_profile_path(path, resolved_profile).stat().st_mtime_ns)
        except OSError:
            profile_mtime_ns = -1
    cache_path = str(path)
    if (
        str(_ACTIVE_CONFIG_CACHE.get("path", "")) == cache_path
        and str(_ACTIVE_CONFIG_CACHE.get("profile", "")) == resolved_profile
        and int(_ACTIVE_CONFIG_CACHE.get("mtime_ns", -2) or -2) == mtime_ns
        and int(_ACTIVE_CONFIG_CACHE.get("profile_mtime_ns", -2) or -2) == profile_mtime_ns
    ):
        cached_payload = _ACTIVE_CONFIG_CACHE.get("payload", {})
        return dict(cached_payload) if isinstance(cached_payload, dict) else {}
    try:
        payload = load_raw_config_payload(path, profile=resolved_profile or None)
    except Exception:
        payload = {}
    normalized = dict(payload) if isinstance(payload, dict) else {}
    _ACTIVE_CONFIG_CACHE["path"] = cache_path
    _ACTIVE_CONFIG_CACHE["profile"] = resolved_profile
    _ACTIVE_CONFIG_CACHE["mtime_ns"] = mtime_ns
    _ACTIVE_CONFIG_CACHE["profile_mtime_ns"] = profile_mtime_ns
    _ACTIVE_CONFIG_CACHE["payload"] = dict(normalized)
    return normalized


def _config_value_present(config: object, dotted_path: str) -> bool:
    current = config
    for part in [segment.strip() for segment in str(dotted_path or "").split(".") if segment.strip()]:
        if not isinstance(current, Mapping) or part not in current:
            return False
        current = current[part]
    if current is None:
        return False
    if isinstance(current, bool):
        return current
    if isinstance(current, str):
        return bool(current.strip())
    if isinstance(current, Mapping):
        return bool(current)
    if isinstance(current, (list, tuple, set)):
        return bool(current)
    return True


def _extract_skill_entries(config: object) -> dict[str, object]:
    if not isinstance(config, Mapping):
        return {}
    skills = config.get("skills")
    if not isinstance(skills, Mapping):
        return {}
    entries = skills.get("entries")
    return dict(entries) if isinstance(entries, Mapping) else {}


def _bundled_allowlist(
    config_path: str | Path | None = None,
    *,
    profile: str | None = None,
) -> set[str] | None:
    config = _resolve_active_config_payload(config_path, profile=profile)
    if not isinstance(config, Mapping):
        return None
    skills = config.get("skills")
    if not isinstance(skills, Mapping):
        return None
    raw = skills.get("allowBundled", skills.get("allow_bundled"))
    rows, _issues = _coerce_list(raw)
    if not rows:
        return None
    return {str(item).strip().lower() for item in rows if str(item).strip()}


def _bundled_skill_allowed(
    skill_key: str,
    source: str,
    *,
    config_path: str | Path | None = None,
    profile: str | None = None,
) -> bool:
    if str(source or "").strip().lower() != "builtin":
        return True
    allowlist = _bundled_allowlist(config_path, profile=profile)
    if allowlist is None:
        return True
    return str(skill_key or "").strip().lower() in allowlist


def _skill_entry_payload(
    skill_key: str,
    *,
    config_path: str | Path | None = None,
    profile: str | None = None,
) -> dict[str, object]:
    entries = _extract_skill_entries(_resolve_active_config_payload(config_path, profile=profile))
    wanted = str(skill_key or "").strip()
    if not wanted:
        return {}
    exact = entries.get(wanted)
    if isinstance(exact, Mapping):
        return dict(exact)
    lowered = wanted.lower()
    for key, value in entries.items():
        if str(key or "").strip().lower() != lowered or not isinstance(value, Mapping):
            continue
        return dict(value)
    return {}


def _skill_entry_enabled(
    skill_key: str,
    *,
    config_path: str | Path | None = None,
    profile: str | None = None,
) -> bool | None:
    payload = _skill_entry_payload(skill_key, config_path=config_path, profile=profile)
    if "enabled" not in payload:
        return None
    return _to_bool(payload.get("enabled"))


def _resolve_skill_entry_api_key(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, Mapping):
        return ""
    source = str(value.get("source", "") or "").strip().lower()
    env_id = str(value.get("id", "") or "").strip()
    if source == "env" and _ENV_NAME_RE.fullmatch(env_id):
        return str(os.getenv(env_id, "") or "").strip()
    return ""


def _skill_entry_env_overrides(
    skill_key: str,
    primary_env: str = "",
    *,
    config_path: str | Path | None = None,
    profile: str | None = None,
) -> dict[str, str]:
    payload = _skill_entry_payload(skill_key, config_path=config_path, profile=profile)
    overrides: dict[str, str] = {}

    raw_env = payload.get("env")
    if isinstance(raw_env, Mapping):
        for key, value in raw_env.items():
            env_key = str(key or "").strip()
            if not _ENV_NAME_RE.fullmatch(env_key):
                continue
            if os.getenv(env_key):
                continue
            overrides[env_key] = str(value or "")

    primary = str(primary_env or "").strip()
    if primary and _ENV_NAME_RE.fullmatch(primary) and not os.getenv(primary) and primary not in overrides:
        resolved_api_key = _resolve_skill_entry_api_key(payload.get("apiKey", payload.get("api_key")))
        if resolved_api_key:
            overrides[primary] = resolved_api_key

    return overrides


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
    out = {"bins": [], "env": [], "os": [], "any_bins": [], "config": []}
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
            env, env_issues = _coerce_env_names(runtime_requires.get("env"))
            os_items, os_issues = _coerce_list(runtime_requires.get("os"), normalize_os=True)
            any_bins, any_bins_issues = _coerce_list(runtime_requires.get("anyBins", runtime_requires.get("any_bins")))
            config_items, config_issues = _coerce_list(runtime_requires.get("config"))
            out["bins"].extend(bins)
            out["env"].extend(env)
            out["os"].extend(os_items)
            out["any_bins"].extend(any_bins)
            out["config"].extend(config_items)
            issues.extend(bins_issues)
            issues.extend(env_issues)
            issues.extend(os_issues)
            issues.extend(any_bins_issues)
            issues.extend(config_issues)
        elif runtime_requires:
            issues.append("requirements:metadata_requires_invalid_type")

        runtime_os, runtime_os_issues = _coerce_list(metadata_runtime.get("os"), normalize_os=True)
        out["os"].extend(runtime_os)
        issues.extend(runtime_os_issues)
        primary_env = metadata_runtime.get("primaryEnv", metadata_runtime.get("primary_env"))
        primary_env_rows, primary_env_issues = _coerce_env_names(primary_env)
        out["env"].extend(primary_env_rows)
        issues.extend(primary_env_issues)

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
            env, env_issues = _coerce_env_names(decoded.get("env"))
            os_items, os_issues = _coerce_list(decoded.get("os"), normalize_os=True)
            any_bins, any_bins_issues = _coerce_list(decoded.get("anyBins", decoded.get("any_bins")))
            config_items, config_issues = _coerce_list(decoded.get("config"))
            out["bins"].extend(bins)
            out["env"].extend(env)
            out["os"].extend(os_items)
            out["any_bins"].extend(any_bins)
            out["config"].extend(config_items)
            issues.extend(bins_issues)
            issues.extend(env_issues)
            issues.extend(os_issues)
            issues.extend(any_bins_issues)
            issues.extend(config_issues)
        elif decoded is not None:
            issues.append("requirements:invalid_type")

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


def _missing_requirements(
    requirements: dict[str, list[str]],
    *,
    env_overrides: Mapping[str, str] | None = None,
    config_path: str | Path | None = None,
    profile: str | None = None,
) -> list[str]:
    missing: list[str] = []
    resolved_env = env_overrides or {}
    for binary in requirements["bins"]:
        if shutil.which(binary) is None:
            missing.append(f"bin:{binary}")
    any_bins = requirements.get("any_bins", [])
    if any_bins and not any(shutil.which(binary) is not None for binary in any_bins):
        missing.append(f"any_bin:{'|'.join(any_bins)}")
    for env_key in requirements["env"]:
        if os.getenv(env_key):
            continue
        override_value = resolved_env.get(env_key)
        if str(override_value or "").strip():
            continue
        if not os.getenv(env_key):
            missing.append(f"env:{env_key}")
    config_payload = _resolve_active_config_payload(config_path, profile=profile)
    for config_key in requirements.get("config", []):
        if not _config_value_present(config_payload, config_key):
            missing.append(f"config:{config_key}")
    supported_oses = requirements["os"]
    if supported_oses:
        current = _normalize_os_name(platform.system())
        if current not in supported_oses:
            missing.append(f"os:{current} not in {','.join(supported_oses)}")
    return missing


def _managed_skill_slug(path: Path) -> str:
    try:
        return str(path.parent.name or "").strip()
    except Exception:
        return ""


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
    enabled: bool
    pinned: bool
    version: str
    missing: list[str]
    requirements: dict[str, list[str]]
    execution_kind: str
    execution_target: str
    execution_argv: list[str]
    contract_issues: list[str]
    skill_key: str = ""
    primary_env: str = ""
    fallback_hint: str = ""
    version_pin: str = ""


class SkillsLoader:
    """Loads SKILL.md from builtin/workspace/marketplace skill roots."""

    def __init__(
        self,
        builtin_root: str | Path | None = None,
        *,
        config_path: str | Path | None = None,
        config_profile: str | None = None,
        state_path: str | Path | None = None,
        watch_debounce_ms: int = 250,
        watch_interval_s: float | None = None,
        now_monotonic=None,
    ) -> None:
        default_builtin = Path(__file__).resolve().parents[1] / "skills"
        user_home = _resolved_home()
        self.roots = [
            Path(builtin_root) if builtin_root else default_builtin,
            user_home / ".clawlite" / "workspace" / "skills",
            user_home / ".clawlite" / "marketplace" / "skills",
        ]
        self.config_path = Path(config_path).expanduser() if config_path is not None else None
        self.config_profile = str(config_profile or "").strip()
        self.state_path = (
            Path(state_path)
            if state_path is not None
            else (user_home / ".clawlite" / "state" / "skills-state.json")
        )
        self.watch_debounce_ms = max(0, int(watch_debounce_ms or 0))
        default_watch_interval = max(0.1, float(self.watch_debounce_ms) / 1000.0) if self.watch_debounce_ms else 0.5
        self.watch_interval_s = max(0.05, float(watch_interval_s or default_watch_interval))
        self._now_monotonic = now_monotonic or time.monotonic
        self._discovery_signature: tuple[tuple[str, bool, int], ...] | None = None
        self._discovered_specs: list[SkillSpec] | None = None
        self._name_index: dict[str, SkillSpec] | None = None
        self._last_refresh_monotonic = 0.0
        self._pending_signature: tuple[tuple[str, bool, int], ...] | None = None
        self._watcher_task: asyncio.Task[None] | None = None
        self._watcher_stop_event: asyncio.Event | None = None
        self._watcher_state: dict[str, object] = {
            "enabled": True,
            "backend": "polling",
            "running": False,
            "interval_s": self.watch_interval_s,
            "ticks": 0,
            "last_error": "",
            "last_result": "",
            "last_tick_monotonic": 0.0,
            "last_refresh_monotonic": 0.0,
            "debounced": False,
            "pending": False,
        }

    @staticmethod
    def _default_state_payload() -> dict[str, object]:
        return {
            "version": 1,
            "entries": {},
        }

    @staticmethod
    def _flush_and_fsync(handle) -> None:
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except Exception:
            pass

    def _atomic_write_state(self, payload: dict[str, object]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_path.parent / f".{self.state_path.name}.{uuid.uuid4().hex}.tmp"
        try:
            with temp_path.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
                self._flush_and_fsync(fh)
            os.replace(temp_path, self.state_path)
            dir_fd = -1
            try:
                dir_fd = os.open(str(self.state_path.parent), os.O_RDONLY)
                os.fsync(dir_fd)
            except Exception:
                pass
            finally:
                if dir_fd >= 0:
                    try:
                        os.close(dir_fd)
                    except Exception:
                        pass
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    def _load_state_payload(self) -> dict[str, object]:
        if not self.state_path.exists():
            return self._default_state_payload()
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return self._default_state_payload()
        if not isinstance(payload, dict):
            return self._default_state_payload()
        entries = payload.get("entries")
        if not isinstance(entries, dict):
            payload["entries"] = {}
        payload.setdefault("version", 1)
        return payload

    def _entry_state(self, name: str) -> dict[str, object]:
        payload = self._load_state_payload()
        entries = payload.get("entries", {})
        if not isinstance(entries, dict):
            return {}
        raw = entries.get(str(name).strip().lower())
        return dict(raw) if isinstance(raw, dict) else {}

    def _roots_signature(self) -> tuple[tuple[str, bool, int], ...]:
        signature: list[tuple[str, bool, int]] = []
        for root in self.roots:
            exists = root.exists()
            if not exists:
                signature.append((str(root), False, 0))
                continue
            skill_files = sorted(root.rglob("SKILL.md"))
            if not skill_files:
                signature.append((str(root), True, root.stat().st_mtime_ns))
                continue
            for path in skill_files:
                try:
                    stat = path.stat()
                except Exception:
                    continue
                file_sig = f"{path.relative_to(root)}:{stat.st_mtime_ns}:{stat.st_size}"
                digest = int(hashlib.sha1(file_sig.encode("utf-8")).hexdigest()[:15], 16)
                signature.append((str(path), True, digest))
        return tuple(signature)

    def _refresh_runtime_status(self, spec: SkillSpec) -> SkillSpec:
        env_overrides = _skill_entry_env_overrides(
            spec.skill_key or spec.name,
            spec.primary_env,
            config_path=self.config_path,
            profile=self.config_profile,
        )
        missing = _missing_requirements(
            spec.requirements,
            env_overrides=env_overrides,
            config_path=self.config_path,
            profile=self.config_profile,
        )
        if not _bundled_skill_allowed(
            spec.skill_key or spec.name,
            spec.source,
            config_path=self.config_path,
            profile=self.config_profile,
        ):
            missing = [*missing, "policy:bundled_not_allowed"]
        available = (not missing) and (not spec.contract_issues)
        entry_state = self._entry_state(spec.name)
        config_enabled = _skill_entry_enabled(
            spec.skill_key or spec.name,
            config_path=self.config_path,
            profile=self.config_profile,
        )
        enabled = bool(entry_state.get("enabled", True)) and (True if config_enabled is None else bool(config_enabled))
        pinned = bool(entry_state.get("pinned", False))
        version_pin = str(entry_state.get("version_pin", "") or "").strip()
        if (
            spec.missing == missing
            and spec.available == available
            and spec.enabled == enabled
            and spec.pinned == pinned
            and spec.version_pin == version_pin
        ):
            return spec
        return replace(spec, missing=missing, available=available, enabled=enabled, pinned=pinned, version_pin=version_pin)

    def _rebuild_discovery_cache(self, *, signature: tuple[tuple[str, bool, int], ...]) -> None:
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
        self._last_refresh_monotonic = float(self._now_monotonic())
        self._pending_signature = None

    def _ensure_discovery_cache(self, *, force: bool = False) -> None:
        signature = self._roots_signature()
        if (
            not force
            and
            self._discovery_signature == signature
            and self._discovered_specs is not None
            and self._name_index is not None
        ):
            return
        if self._discovered_specs is None or self._name_index is None or self._discovery_signature is None:
            self._rebuild_discovery_cache(signature=signature)
            return
        if force:
            self._rebuild_discovery_cache(signature=signature)
            return
        now = float(self._now_monotonic())
        debounce_s = float(self.watch_debounce_ms) / 1000.0
        if debounce_s > 0 and now < (self._last_refresh_monotonic + debounce_s):
            self._pending_signature = signature
            return
        self._rebuild_discovery_cache(signature=signature)

    def invalidate(self) -> None:
        self._pending_signature = self._roots_signature()

    @staticmethod
    def _load_watchfiles_awatch():
        try:
            from watchfiles import awatch  # type: ignore
        except Exception:
            return None
        return awatch

    def _watch_targets(self) -> list[Path]:
        targets: list[Path] = []
        seen: set[str] = set()
        for root in self.roots:
            candidate = root
            while not candidate.exists():
                parent = candidate.parent
                if parent == candidate:
                    candidate = None
                    break
                candidate = parent
            if candidate is None or not candidate.exists():
                continue
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            targets.append(candidate)
        return targets

    def _watcher_tick(self) -> None:
        self._watcher_state["ticks"] = int(self._watcher_state.get("ticks", 0) or 0) + 1
        self._watcher_state["last_tick_monotonic"] = float(self._now_monotonic())

    def _watcher_record_failure(self, exc: Exception, *, result: str = "failed_refresh") -> None:
        self._watcher_state["last_error"] = str(exc)
        self._watcher_state["last_result"] = result
        self._watcher_state["debounced"] = False
        self._watcher_state["pending"] = False

    def _watcher_apply_report(self, report: dict[str, object]) -> None:
        self._watcher_state["last_error"] = ""
        self._watcher_state["last_refresh_monotonic"] = float(report.get("refreshed_at_monotonic", 0.0) or 0.0)
        self._watcher_state["debounced"] = bool(report.get("debounced", False))
        self._watcher_state["pending"] = bool(report.get("pending", False))
        self._watcher_state["last_result"] = "refreshed" if report.get("refreshed", False) else "idle"

    async def _watcher_refresh_once(self, *, stop_event: asyncio.Event, retry_pending: bool) -> None:
        try:
            report = self.refresh(force=False)
        except Exception as exc:
            self._watcher_record_failure(exc)
            return
        self._watcher_apply_report(report)

        if not retry_pending or stop_event.is_set() or not report.get("pending", False):
            return

        debounce_s = max(0.0, float(self.watch_debounce_ms) / 1000.0)
        wait_s = debounce_s
        if debounce_s > 0:
            ready_at = float(self._last_refresh_monotonic) + debounce_s
            wait_s = max(0.0, ready_at - float(self._now_monotonic()))
        if wait_s > 0:
            await asyncio.sleep(wait_s)
        if stop_event.is_set():
            return
        try:
            report = self.refresh(force=False)
        except Exception as exc:
            self._watcher_record_failure(exc)
            return
        self._watcher_apply_report(report)

    async def _watcher_loop_poll(self, *, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            self._watcher_tick()
            await self._watcher_refresh_once(stop_event=stop_event, retry_pending=False)
            await asyncio.sleep(self.watch_interval_s)

    async def _watcher_loop_watchfiles(self, *, stop_event: asyncio.Event, awatch) -> None:
        targets = self._watch_targets()
        if not targets:
            await self._watcher_loop_poll(stop_event=stop_event)
            return

        async for _changes in awatch(*[str(path) for path in targets], stop_event=stop_event):
            if stop_event.is_set():
                break
            self._watcher_tick()
            await self._watcher_refresh_once(stop_event=stop_event, retry_pending=True)

    def _watcher_done_callback(self, task: asyncio.Task[None]) -> None:
        self._watcher_state["running"] = False
        try:
            task.result()
        except asyncio.CancelledError:
            self._watcher_state["last_result"] = "cancelled"
        except Exception as exc:
            self._watcher_state["last_result"] = "failed"
            self._watcher_state["last_error"] = str(exc)
        else:
            self._watcher_state["last_result"] = "stopped"

    async def start_watcher(self) -> dict[str, object]:
        task = self._watcher_task
        if task is not None and not task.done():
            self._watcher_state["running"] = True
            return self.watcher_status()
        if task is not None and task.done():
            self._watcher_done_callback(task)

        stop_event = asyncio.Event()
        self._watcher_stop_event = stop_event
        awatch = self._load_watchfiles_awatch()
        backend = "watchfiles" if awatch is not None and self._watch_targets() else "polling"
        self._watcher_state["running"] = True
        self._watcher_state["backend"] = backend
        self._watcher_state["interval_s"] = self.watch_interval_s
        self._watcher_state["last_error"] = ""
        self._watcher_state["last_result"] = "starting"

        async def _loop() -> None:
            if backend == "watchfiles" and awatch is not None:
                try:
                    await self._watcher_loop_watchfiles(stop_event=stop_event, awatch=awatch)
                except Exception as exc:
                    self._watcher_record_failure(exc, result="watchfiles_failed")
                    self._watcher_state["backend"] = "polling"
                    if not stop_event.is_set():
                        await self._watcher_loop_poll(stop_event=stop_event)
                return
            await self._watcher_loop_poll(stop_event=stop_event)

        self._watcher_task = asyncio.create_task(_loop())
        self._watcher_task.add_done_callback(self._watcher_done_callback)
        return self.watcher_status()

    async def stop_watcher(self) -> dict[str, object]:
        stop_event = self._watcher_stop_event
        task = self._watcher_task
        if stop_event is not None:
            stop_event.set()
        self._watcher_state["running"] = False
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                self._watcher_state["last_error"] = str(exc)
                self._watcher_state["last_result"] = "failed"
        self._watcher_task = None
        self._watcher_stop_event = None
        if not str(self._watcher_state.get("last_result", "") or "").strip():
            self._watcher_state["last_result"] = "stopped"
        return self.watcher_status()

    def watcher_status(self) -> dict[str, object]:
        task = self._watcher_task
        task_state = "stopped"
        if task is not None:
            if not task.done():
                task_state = "running"
            elif task.cancelled():
                task_state = "cancelled"
            elif task.exception() is not None:
                task_state = "failed"
            else:
                task_state = "done"
        return {
            "enabled": True,
            "backend": str(self._watcher_state.get("backend", "polling") or "polling"),
            "running": bool(task is not None and not task.done() and self._watcher_state.get("running", False)),
            "task_state": task_state,
            "interval_s": self.watch_interval_s,
            "watch_debounce_ms": self.watch_debounce_ms,
            "ticks": int(self._watcher_state.get("ticks", 0) or 0),
            "last_error": str(self._watcher_state.get("last_error", "") or ""),
            "last_result": str(self._watcher_state.get("last_result", "") or ""),
            "last_tick_monotonic": float(self._watcher_state.get("last_tick_monotonic", 0.0) or 0.0),
            "last_refresh_monotonic": float(self._watcher_state.get("last_refresh_monotonic", 0.0) or 0.0),
            "pending": bool(self._watcher_state.get("pending", False)),
            "debounced": bool(self._watcher_state.get("debounced", False)),
        }

    @staticmethod
    def _source_label(root: Path, index: int) -> str:
        if index == 0:
            return "builtin"
        if "workspace" in str(root):
            return "workspace"
        return "marketplace"

    def _parse_header(self, path: Path, *, source: str) -> SkillSpec | None:
        text = path.read_text(encoding="utf-8", errors="ignore")
        meta, body = _extract_frontmatter(text)
        raw_name = str(meta.get("name", "")).strip()
        name = raw_name or path.parent.name
        description = str(meta.get("description", "")).strip()
        always = _to_bool(meta.get("always", "false"))
        requires, _ = _coerce_list(meta.get("requires"))
        command = str(meta.get("command", "")).strip()
        script = str(meta.get("script", "")).strip()
        homepage = str(meta.get("homepage", "")).strip()
        fallback_hint = str(meta.get("fallback_hint", "")).strip()

        if not name:
            return None

        req_map, req_issues = _extract_requirement_map(meta)
        runtime_meta, _runtime_issues = _extract_runtime_metadata(meta)
        skill_key = name
        primary_env = ""
        if runtime_meta:
            raw_skill_key = str(runtime_meta.get("skillKey", runtime_meta.get("skill_key", "")) or "").strip()
            if raw_skill_key:
                skill_key = raw_skill_key
            primary_env_rows, primary_env_issues = _coerce_env_names(
                runtime_meta.get("primaryEnv", runtime_meta.get("primary_env"))
            )
            if primary_env_rows:
                primary_env = primary_env_rows[0]
            req_issues.extend(primary_env_issues)
        missing = _missing_requirements(
            req_map,
            env_overrides=_skill_entry_env_overrides(
                skill_key,
                primary_env,
                config_path=self.config_path,
                profile=self.config_profile,
            ),
            config_path=self.config_path,
            profile=self.config_profile,
        )
        if not _bundled_skill_allowed(
            skill_key,
            source,
            config_path=self.config_path,
            profile=self.config_profile,
        ):
            missing = [*missing, "policy:bundled_not_allowed"]
        execution_kind, execution_target, execution_argv, contract_issues = _build_execution_contract(meta)
        metadata_as_text = {key: _serialize_frontmatter_value(value) for key, value in meta.items()}
        version = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
        all_contract_issues: list[str] = []
        if "name" in meta and not raw_name:
            all_contract_issues.append("metadata:empty_name")
        for issue in [*req_issues, *contract_issues]:
            if issue not in all_contract_issues:
                all_contract_issues.append(issue)

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
            enabled=True,
            pinned=False,
            version=version,
            missing=missing,
            requirements=req_map,
            execution_kind=execution_kind,
            execution_target=execution_target,
            execution_argv=execution_argv,
            contract_issues=all_contract_issues,
            skill_key=skill_key,
            primary_env=primary_env,
            fallback_hint=fallback_hint,
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

    def refresh(self, *, force: bool = False) -> dict[str, object]:
        before = self._discovery_signature
        before_refresh_at = self._last_refresh_monotonic
        self._ensure_discovery_cache(force=force)
        report = {
            "refreshed": bool(force or before != self._discovery_signature),
            "debounced": bool(not force and self._pending_signature is not None),
            "pending": self._pending_signature is not None,
            "watch_debounce_ms": self.watch_debounce_ms,
            "refreshed_at_monotonic": self._last_refresh_monotonic,
            "previous_refresh_at_monotonic": before_refresh_at,
        }
        self._watcher_state["last_refresh_monotonic"] = float(report["refreshed_at_monotonic"] or 0.0)
        self._watcher_state["debounced"] = bool(report["debounced"])
        self._watcher_state["pending"] = bool(report["pending"])
        return report

    def set_enabled(self, name: str, enabled: bool) -> SkillSpec | None:
        spec = self.get(name)
        if spec is None:
            return None
        payload = self._load_state_payload()
        entries = payload.setdefault("entries", {})
        if not isinstance(entries, dict):
            entries = {}
            payload["entries"] = entries
        key = spec.name.strip().lower()
        row = dict(entries.get(key) or {}) if isinstance(entries.get(key), dict) else {}
        row["enabled"] = bool(enabled)
        row.setdefault("pinned", False)
        row["name"] = spec.name
        entries[key] = row
        self._atomic_write_state(payload)
        return self.get(spec.name)

    def set_pinned(self, name: str, pinned: bool) -> SkillSpec | None:
        spec = self.get(name)
        if spec is None:
            return None
        payload = self._load_state_payload()
        entries = payload.setdefault("entries", {})
        if not isinstance(entries, dict):
            entries = {}
            payload["entries"] = entries
        key = spec.name.strip().lower()
        row = dict(entries.get(key) or {}) if isinstance(entries.get(key), dict) else {}
        row["enabled"] = bool(row.get("enabled", True))
        row["pinned"] = bool(pinned)
        row["name"] = spec.name
        entries[key] = row
        self._atomic_write_state(payload)
        return self.get(spec.name)

    def set_version_pin(self, name: str, version: str) -> SkillSpec | None:
        """Pin a skill to a specific version string. Pass empty string to clear."""
        spec = self.get(name)
        if spec is None:
            return None
        clean_version = str(version or "").strip()
        payload = self._load_state_payload()
        entries = payload.setdefault("entries", {})
        if not isinstance(entries, dict):
            entries = {}
            payload["entries"] = entries
        key = spec.name.strip().lower()
        row = dict(entries.get(key) or {}) if isinstance(entries.get(key), dict) else {}
        row.setdefault("enabled", True)
        row.setdefault("pinned", False)
        row["name"] = spec.name
        if clean_version:
            row["version_pin"] = clean_version
        else:
            row.pop("version_pin", None)
        entries[key] = row
        self._atomic_write_state(payload)
        return self.get(spec.name)

    def clear_version_pin(self, name: str) -> SkillSpec | None:
        """Remove the version pin for a skill."""
        return self.set_version_pin(name, "")

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
        managed_status_counts: dict[str, int] = {
            "ready": 0,
            "disabled": 0,
            "missing_requirements": 0,
            "policy_blocked": 0,
            "invalid_contract": 0,
            "unavailable": 0,
        }

        available_count = 0
        unavailable_count = 0
        always_on_available_count = 0
        always_on_unavailable_count = 0
        enabled_count = 0
        disabled_count = 0
        pinned_count = 0
        runnable_count = 0
        contract_total = 0

        skill_rows: list[dict[str, object]] = []
        managed_rows: list[dict[str, object]] = []

        for row in rows:
            if row.enabled:
                enabled_count += 1
            else:
                disabled_count += 1
            if row.pinned:
                pinned_count += 1
            runnable = bool(row.available and row.enabled and row.execution_kind in {"command", "script"})
            runtime_requirements = self._runtime_requirements_for_spec(row)

            if row.available:
                available_count += 1
                if runnable:
                    runnable_count += 1
                if row.always and row.enabled:
                    always_on_available_count += 1
            else:
                unavailable_count += 1
                if row.always and row.enabled:
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

            skill_row: dict[str, object] = {
                "name": row.name,
                "skill_key": row.skill_key or row.name,
                "primary_env": row.primary_env,
                "available": row.available,
                "enabled": row.enabled,
                "pinned": row.pinned,
                "version": row.version,
                "version_pin": row.version_pin,
                "runnable": runnable,
                "source": row.source,
                "execution_kind": row.execution_kind,
                "runtime_requirements": runtime_requirements,
                "missing": sorted(row.missing),
                "contract_issues": sorted(row.contract_issues),
            }
            if not row.available and row.fallback_hint:
                skill_row["fallback_hint"] = row.fallback_hint
            skill_rows.append(skill_row)

            if row.source == "marketplace":
                managed_status = skills_doctor_status(skill_row)
                managed_status_counts[managed_status] = managed_status_counts.get(managed_status, 0) + 1
                managed_rows.append(
                    {
                        "slug": _managed_skill_slug(row.path),
                        "name": row.name,
                        "skill_key": row.skill_key or row.name,
                        "status": managed_status,
                        "enabled": row.enabled,
                        "available": row.available,
                        "version": row.version,
                        "version_pin": row.version_pin,
                        "hint": skills_doctor_hint(skill_row),
                    }
                )

        for prefix in ("bin", "env", "os", "other"):
            missing_groups[prefix]["items"] = sorted(str(item) for item in missing_groups[prefix]["items"])

        managed_rows = sorted(
            managed_rows,
            key=lambda item: (
                int(_SKILL_STATUS_PRIORITY.get(str(item.get("status", "") or ""), 999)),
                str(item.get("name", "") or "").lower(),
            ),
        )
        managed_blocked_count = sum(
            managed_status_counts.get(status, 0)
            for status in ("missing_requirements", "policy_blocked", "invalid_contract", "unavailable")
        )
        managed_report = skills_managed_report(self)

        return {
            "summary": {
                "total": len(rows),
                "available": available_count,
                "unavailable": unavailable_count,
                "enabled": enabled_count,
                "disabled": disabled_count,
                "pinned": pinned_count,
                "runnable": runnable_count,
                "always_on_available": always_on_available_count,
                "always_on_unavailable": always_on_unavailable_count,
            },
            "execution_kinds": execution_kinds,
            "sources": source_counts,
            "watcher": self.watcher_status(),
            "missing_requirements": missing_groups,
            "managed": {
                "count": int(managed_report.get("total_count", len(managed_rows)) or 0),
                "ready_count": int(managed_report.get("ready_count", managed_status_counts.get("ready", 0)) or 0),
                "blocked_count": int(managed_report.get("blocked_count", managed_blocked_count) or 0),
                "disabled_count": int(
                    managed_report.get("disabled_count", managed_status_counts.get("disabled", 0)) or 0
                ),
                "status_counts": dict(managed_report.get("status_counts", {}) or {}),
                "items": list(managed_report.get("skills", []) or [])[:5],
            },
            "contract_issues": {
                "total": contract_total,
                "by_key": {key: contract_issue_counts[key] for key in sorted(contract_issue_counts)},
            },
            "skills": sorted(skill_rows, key=lambda item: str(item["name"]).lower()),
        }

    @staticmethod
    def _runtime_requirements_for_spec(spec: SkillSpec) -> list[str]:
        if spec.execution_kind != "script":
            return []
        script_name = str(spec.script or "").strip().lower()
        if script_name == "coding_agent":
            return ["tool:sessions_spawn"]
        if script_name == "gh_issues":
            return ["tool:exec"]
        if script_name == "summarize":
            return ["provider", "tool:web_fetch|read|read_file"]
        return []

    def always_on(self, *, only_available: bool = True) -> list[SkillSpec]:
        rows = self.discover(include_unavailable=not only_available)
        return [item for item in rows if item.enabled and item.always and (item.available or not only_available)]

    def get(self, name: str) -> SkillSpec | None:
        self._ensure_discovery_cache()
        assert self._name_index is not None
        wanted = name.strip().lower()
        row = self._name_index.get(wanted)
        if row is None:
            return None
        return self._refresh_runtime_status(row)

    def resolved_env_overrides(self, spec_or_name: SkillSpec | str) -> dict[str, str]:
        spec = spec_or_name if isinstance(spec_or_name, SkillSpec) else self.get(str(spec_or_name))
        if spec is None:
            return {}
        return _skill_entry_env_overrides(
            spec.skill_key or spec.name,
            spec.primary_env,
            config_path=self.config_path,
            profile=self.config_profile,
        )

    def build_skills_summary(self) -> str:
        """Return XML summary of all available skills (name + description only).

        Use this to inject into agent context without bloating the prompt with full skill content.
        Call load_skill_full(name) to get the complete SKILL.md on demand.
        """
        skills = self.discover(include_unavailable=True)
        if not skills:
            return "<skills></skills>"
        lines = ["<skills>"]
        for skill in skills:
            name = str(skill.name or "").strip()
            desc = str(skill.description or "").strip()
            available = str(skill.available).lower()
            desc_safe = desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f'  <skill name="{name}" available="{available}">{desc_safe}</skill>')
        lines.append("</skills>")
        return "\n".join(lines)

    def load_skill_full(self, name: str) -> str:
        """Load complete SKILL.md content for a specific skill (on-demand full load).

        Returns empty string if skill not found.
        """
        normalized = str(name or "").strip().lower().replace(" ", "-")
        for root in self.roots:
            if not root.is_dir():
                continue
            skill_md = root / normalized / "SKILL.md"
            if skill_md.is_file():
                return skill_md.read_text(encoding="utf-8", errors="replace")
        return ""

    def load_skill_content(self, name: str) -> str | None:
        spec = self.get(name)
        if spec is None:
            return None
        return spec.body

    def load_skills_for_context(self, skill_names: Iterable[str]) -> str:
        parts: list[str] = []
        for name in skill_names:
            spec = self.get(name)
            if spec is None or not spec.enabled or not spec.body:
                continue
            parts.append(f"### Skill: {spec.name}\n\n{spec.body}")
        return "\n\n---\n\n".join(parts)

    def render_for_prompt(self, selected: Iterable[str] | None = None, *, include_unavailable: bool = False) -> list[str]:
        selected_set = {item.strip() for item in (selected or []) if item.strip()}
        lines = ["<available_skills>"]
        for skill in self.discover(include_unavailable=include_unavailable):
            if not skill.enabled:
                continue
            if not skill.available and not include_unavailable:
                continue
            if selected_set and skill.name not in selected_set and not skill.always:
                continue
            lines.append("<skill>")
            lines.append(f"<name>{_escape_xml(skill.name)}</name>")
            lines.append(f"<description>{_escape_xml(skill.description or 'no description')}</description>")
            lines.append(f"<location>{_escape_xml(str(skill.path))}</location>")
            lines.append(f"<version>{_escape_xml(skill.version)}</version>")
            if include_unavailable and not skill.available:
                missing = ", ".join([*skill.missing, *skill.contract_issues])
                lines.append(f"<requires>{_escape_xml(missing)}</requires>")
            lines.append("</skill>")
        lines.append("</available_skills>")
        return ["\n".join(lines)]


def _managed_skill_report_payload(row: SkillSpec) -> dict[str, object]:
    doctor_row = {
        "name": row.name,
        "skill_key": row.skill_key or row.name,
        "primary_env": row.primary_env,
        "enabled": row.enabled,
        "available": row.available,
        "missing": list(row.missing or []),
        "contract_issues": list(row.contract_issues or []),
        "fallback_hint": row.fallback_hint,
    }
    return {
        "slug": _managed_skill_slug(row.path),
        "name": row.name,
        "skill_key": row.skill_key or row.name,
        "primary_env": row.primary_env,
        "description": row.description,
        "available": row.available,
        "enabled": row.enabled,
        "pinned": row.pinned,
        "status": skills_doctor_status(doctor_row),
        "hint": skills_doctor_hint(doctor_row),
        "version": row.version,
        "version_pin": row.version_pin,
        "missing": sorted(str(item) for item in list(row.missing or [])),
        "homepage": row.homepage,
        "fallback_hint": row.fallback_hint,
        "path": str(row.path),
    }


def _managed_marketplace_specs(loader: SkillsLoader) -> list[SkillSpec]:
    marketplace_root = loader.roots[2]
    if not marketplace_root.exists():
        return []
    rows: list[SkillSpec] = []
    for path in sorted(marketplace_root.rglob("SKILL.md")):
        spec = loader._parse_header(path, source="marketplace")
        if spec is None:
            continue
        rows.append(loader._refresh_runtime_status(spec))
    return rows


def _managed_marketplace_root(loader: SkillsLoader) -> Path:
    return loader.roots[2].parent


def _run_clawhub_command(loader: SkillsLoader, *action_args: str) -> tuple[int, dict[str, object]]:
    managed_root = _managed_marketplace_root(loader)
    skills_root = managed_root / "skills"
    npx_path = shutil.which("npx")
    if not npx_path:
        return 1, {
            "ok": False,
            "returncode": 1,
            "error": "skills_manager_requires_npx",
            "managed_root": str(managed_root),
            "skills_root": str(skills_root),
        }

    managed_root.mkdir(parents=True, exist_ok=True)
    command = [npx_path, "--yes", "clawhub@latest", *action_args, "--workdir", str(managed_root)]
    completed = subprocess.run(command, capture_output=True, text=True)
    payload: dict[str, object] = {
        "ok": completed.returncode == 0,
        "returncode": int(completed.returncode),
        "command": command,
        "managed_root": str(managed_root),
        "skills_root": str(skills_root),
        "stdout": str(completed.stdout or "").strip(),
        "stderr": str(completed.stderr or "").strip(),
    }
    if completed.returncode != 0:
        payload["error"] = "skills_manager_command_failed"
    return completed.returncode, payload


def skills_managed_report(
    loader: SkillsLoader,
    *,
    status: str = "",
    query: str = "",
) -> dict[str, object]:
    wanted_status = str(status or "").strip().lower()
    wanted_query = str(query or "").strip().lower()
    managed_root = loader.roots[2].parent
    all_rows = [
        _managed_skill_report_payload(row)
        for row in _managed_marketplace_specs(loader)
    ]
    all_rows = sorted(
        all_rows,
        key=lambda item: (
            int(_SKILL_STATUS_PRIORITY.get(str(item.get("status", "") or ""), 999)),
            str(item.get("name", "") or "").lower(),
        ),
    )
    status_counts: dict[str, int] = {}
    for row in all_rows:
        resolved_status = str(row.get("status", "") or "").strip().lower()
        if not resolved_status:
            continue
        status_counts[resolved_status] = status_counts.get(resolved_status, 0) + 1

    filtered_rows = list(all_rows)
    if wanted_status:
        filtered_rows = [row for row in filtered_rows if str(row.get("status", "") or "").strip().lower() == wanted_status]
    if wanted_query:
        filtered_rows = [
            row
            for row in filtered_rows
            if wanted_query
            in " ".join(
                [
                    str(row.get("slug", "") or ""),
                    str(row.get("name", "") or ""),
                    str(row.get("skill_key", "") or ""),
                    str(row.get("description", "") or ""),
                    str(row.get("hint", "") or ""),
                ]
            ).lower()
        ]

    blocked_count = sum(
        int(status_counts.get(key, 0) or 0)
        for key in ("missing_requirements", "policy_blocked", "invalid_contract", "unavailable")
    )
    return {
        "ok": True,
        "action": "managed",
        "managed_root": str(managed_root),
        "skills_root": str(managed_root / "skills"),
        "count": len(filtered_rows),
        "total_count": len(all_rows),
        "ready_count": int(status_counts.get("ready", 0) or 0),
        "blocked_count": blocked_count,
        "disabled_count": int(status_counts.get("disabled", 0) or 0),
        "status_filter": wanted_status,
        "query": wanted_query,
        "status_counts": {key: status_counts[key] for key in sorted(status_counts)},
        "skills": filtered_rows,
    }


def skills_sync_report(loader: SkillsLoader) -> dict[str, object]:
    rc, payload = _run_clawhub_command(loader, "update", "--all")
    payload["action"] = "sync"
    if rc == 0:
        payload["refresh"] = loader.refresh(force=True)
        managed = skills_managed_report(loader)
        payload["managed"] = managed
        payload["managed_count"] = int(managed.get("total_count", managed.get("count", 0)) or 0)
        payload["ready_count"] = int(managed.get("ready_count", 0) or 0)
        payload["blocked_count"] = int(managed.get("blocked_count", 0) or 0)
        payload["disabled_count"] = int(managed.get("disabled_count", 0) or 0)
        payload["status_counts"] = dict(managed.get("status_counts", {}) or {})
        payload["skills"] = list(managed.get("skills", []) or [])
    return payload


def skills_doctor_status(row: Mapping[str, object]) -> str:
    if not bool(row.get("enabled", True)):
        return "disabled"
    if list(row.get("contract_issues", []) or []):
        return "invalid_contract"
    missing = list(row.get("missing", []) or [])
    if "policy:bundled_not_allowed" in missing:
        return "policy_blocked"
    if missing:
        return "missing_requirements"
    if bool(row.get("available", False)):
        return "ready"
    return "unavailable"


def skills_doctor_hint(row: Mapping[str, object]) -> str:
    contract_issues = list(row.get("contract_issues", []) or [])
    if contract_issues:
        return "Fix the SKILL.md frontmatter contract so only one valid execution path is declared."

    missing = [str(item or "") for item in list(row.get("missing", []) or []) if str(item or "").strip()]
    if "policy:bundled_not_allowed" in missing:
        skill_key = str(row.get("skill_key", "") or row.get("name", "")).strip()
        return f"Allow the builtin skill via skills.allowBundled or install a workspace/marketplace override for {skill_key}."

    env_items = [item.split(":", 1)[1] for item in missing if item.startswith("env:")]
    if env_items:
        primary_env = str(row.get("primary_env", "") or "").strip()
        if primary_env and primary_env in env_items:
            skill_key = str(row.get("skill_key", "") or row.get("name", "")).strip()
            return f"Export {primary_env}, set skills.entries.{skill_key}.apiKey manually, or run clawlite skills config {skill_key}."
        return f"Set the required environment variables: {', '.join(env_items)}."

    config_items = [item.split(":", 1)[1] for item in missing if item.startswith("config:")]
    if config_items:
        return f"Set the required config keys: {', '.join(config_items)}."

    bin_items = [item.split(":", 1)[1] for item in missing if item.startswith("bin:")]
    any_bin_items = [item.split(":", 1)[1] for item in missing if item.startswith("any_bin:")]
    if bin_items or any_bin_items:
        fallback_hint = str(row.get("fallback_hint", "") or "").strip()
        if fallback_hint:
            return fallback_hint
        parts = [*bin_items, *[f"one of {item}" for item in any_bin_items]]
        return f"Install the required binaries: {', '.join(parts)}."

    os_items = [item.split(":", 1)[1] for item in missing if item.startswith("os:")]
    if os_items:
        return f"Run this skill on a supported OS or disable it locally: {', '.join(os_items)}."

    return "No action required."


def skills_doctor_report(
    diagnostics: Mapping[str, object],
    *,
    include_all: bool = False,
    status: str = "",
    source: str = "",
    query: str = "",
) -> dict[str, object]:
    rows = list(diagnostics.get("skills", []) or [])
    wanted_status = str(status or "").strip().lower()
    wanted_source = str(source or "").strip().lower()
    wanted_query = str(query or "").strip().lower()
    doctor_rows: list[dict[str, object]] = []
    status_counts: dict[str, int] = {
        "ready": 0,
        "disabled": 0,
        "missing_requirements": 0,
        "policy_blocked": 0,
        "invalid_contract": 0,
        "unavailable": 0,
    }
    recommendations: list[str] = []

    for row in rows:
        row_payload = dict(row) if isinstance(row, Mapping) else {}
        resolved_status = skills_doctor_status(row_payload)
        status_counts[resolved_status] = status_counts.get(resolved_status, 0) + 1
        hint = skills_doctor_hint(row_payload)
        doctor_row = {
            "name": row_payload.get("name", ""),
            "skill_key": row_payload.get("skill_key", ""),
            "primary_env": row_payload.get("primary_env", ""),
            "source": str(row_payload.get("source", "") or ""),
            "status": resolved_status,
            "enabled": bool(row_payload.get("enabled", True)),
            "available": bool(row_payload.get("available", False)),
            "missing": list(row_payload.get("missing", []) or []),
            "contract_issues": list(row_payload.get("contract_issues", []) or []),
            "runtime_requirements": list(row_payload.get("runtime_requirements", []) or []),
            "hint": hint,
        }
        if row_payload.get("fallback_hint"):
            doctor_row["fallback_hint"] = row_payload.get("fallback_hint")
        source_name = str(doctor_row.get("source", "") or "").strip().lower()
        if wanted_status and resolved_status != wanted_status:
            continue
        if wanted_source and source_name != wanted_source:
            continue
        if wanted_query:
            haystack = " ".join(
                [
                    str(doctor_row.get("name", "") or ""),
                    str(doctor_row.get("skill_key", "") or ""),
                    str(doctor_row.get("primary_env", "") or ""),
                    source_name,
                    " ".join(str(item or "") for item in doctor_row.get("missing", []) or []),
                    " ".join(str(item or "") for item in doctor_row.get("contract_issues", []) or []),
                    " ".join(str(item or "") for item in doctor_row.get("runtime_requirements", []) or []),
                    str(doctor_row.get("hint", "") or ""),
                    str(doctor_row.get("fallback_hint", "") or ""),
                ]
            ).lower()
            if wanted_query not in haystack:
                continue
        if include_all or wanted_status or wanted_source or resolved_status not in {"ready", "disabled"}:
            doctor_rows.append(doctor_row)
            if hint != "No action required." and hint not in recommendations:
                recommendations.append(hint)

    blocking = (
        status_counts.get("missing_requirements", 0)
        + status_counts.get("policy_blocked", 0)
        + status_counts.get("invalid_contract", 0)
    )
    return {
        "ok": blocking == 0,
        "action": "skills_doctor",
        "summary": dict(diagnostics.get("summary", {}) or {}),
        "watcher": dict(diagnostics.get("watcher", {}) or {}),
        "status_counts": status_counts,
        "status_filter": wanted_status,
        "source_filter": wanted_source,
        "query": wanted_query,
        "count": len(doctor_rows),
        "recommendations": recommendations,
        "skills": doctor_rows,
    }


def skills_validate_report(
    loader: SkillsLoader,
    *,
    force: bool = True,
    include_all: bool = False,
    status: str = "",
    source: str = "",
    query: str = "",
) -> dict[str, object]:
    refresh = loader.refresh(force=force)
    diagnostics = loader.diagnostics_report()
    doctor = skills_doctor_report(
        diagnostics,
        include_all=include_all,
        status=status,
        source=source,
        query=query,
    )
    return {
        "ok": bool(doctor.get("ok", False)),
        "action": "skills_validate",
        "refresh": refresh,
        "summary": dict(diagnostics.get("summary", {}) or {}),
        "watcher": dict(diagnostics.get("watcher", {}) or {}),
        "contract_issues": dict(diagnostics.get("contract_issues", {}) or {}),
        "missing_requirements": dict(diagnostics.get("missing_requirements", {}) or {}),
        "doctor": doctor,
        "status_counts": dict(doctor.get("status_counts", {}) or {}),
        "status_filter": str(doctor.get("status_filter", "") or ""),
        "source_filter": str(doctor.get("source_filter", "") or ""),
        "query": str(doctor.get("query", "") or ""),
        "count": int(doctor.get("count", 0) or 0),
        "recommendations": list(doctor.get("recommendations", []) or []),
        "skills": list(doctor.get("skills", []) or []),
    }
