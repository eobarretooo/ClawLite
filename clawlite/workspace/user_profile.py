from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


_FIELD_RE = re.compile(r"^(Name|What to call them|Pronouns|Timezone|Context|Preferences):\s*(.*)$", re.IGNORECASE)
_PLACEHOLDER_VALUES = {
    "",
    "(optional)",
    "[optional]",
    "optional",
    "n/a",
    "na",
    "none",
    "unknown",
    "{{user_name}}",
    "{{user_timezone}}",
    "{{user_context}}",
    "{{user_preferences}}",
}
_DEFAULT_NAME_VALUES = {"owner", "user"}
_DEFAULT_CONTEXT = "personal operations and software projects"
_DEFAULT_PREFERENCES = {"clear answers", "direct actions", "concise updates"}


@dataclass(slots=True)
class WorkspaceUserProfile:
    name: str = ""
    preferred_name: str = ""
    pronouns: str = ""
    timezone: str = ""
    context: str = ""
    preferences: list[str] = field(default_factory=list)
    working_style: list[str] = field(default_factory=list)
    source_path: str = ""
    raw_text: str = ""

    def prompt_hint(self) -> str:
        lines = ["[Structured User Profile]"]
        preferred_name = self.preferred_name or self.name
        if preferred_name:
            lines.append(f"- Preferred name: {preferred_name}")
        if self.pronouns:
            lines.append(f"- Pronouns: {self.pronouns}")
        if self.timezone:
            lines.append(f"- Timezone: {self.timezone}")
        if self.context:
            lines.append(f"- Context: {self.context}")
        if self.preferences:
            lines.append(f"- Preferences: {', '.join(self.preferences)}")
        if self.working_style:
            lines.append(f"- Working style: {', '.join(self.working_style)}")
        return "\n".join(lines) if len(lines) > 1 else ""


def _split_preferences(value: str) -> list[str]:
    clean = str(value or "").strip()
    if not clean:
        return []
    parts = re.split(r"[;,]\s*|\s{2,}", clean)
    out: list[str] = []
    for part in parts:
        item = " ".join(part.split()).strip(" -")
        if item and item not in out:
            out.append(item)
    return out


def _clean_field_value(value: str) -> str:
    clean = " ".join(str(value or "").split()).strip()
    lowered = clean.lower()
    return "" if lowered in _PLACEHOLDER_VALUES else clean


def _strip_default_template_profile(profile: WorkspaceUserProfile) -> WorkspaceUserProfile:
    name = " ".join(profile.name.split()).strip().lower()
    preferred_name = " ".join(profile.preferred_name.split()).strip().lower()
    context = " ".join(profile.context.split()).strip().lower()
    prefs = {item.lower() for item in profile.preferences}
    looks_like_template = (
        name in _DEFAULT_NAME_VALUES
        or preferred_name in _PLACEHOLDER_VALUES
        or context == _DEFAULT_CONTEXT
        or _DEFAULT_PREFERENCES.issubset(prefs)
    )
    if not looks_like_template:
        return profile

    if name in _DEFAULT_NAME_VALUES:
        profile.name = ""
    if preferred_name in _PLACEHOLDER_VALUES:
        profile.preferred_name = ""
    if " ".join(profile.pronouns.split()).strip().lower() in _PLACEHOLDER_VALUES:
        profile.pronouns = ""
    if " ".join(profile.timezone.split()).strip().lower() == "utc":
        profile.timezone = ""
    if context == _DEFAULT_CONTEXT:
        profile.context = ""
    if _DEFAULT_PREFERENCES.issubset(prefs):
        profile.preferences = []
    return profile


def parse_user_profile_markdown(text: str, *, source_path: str = "") -> WorkspaceUserProfile:
    profile = WorkspaceUserProfile(source_path=str(source_path or ""), raw_text=str(text or ""))
    in_working_style = False

    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            if in_working_style:
                in_working_style = False
            continue

        if line.startswith("## "):
            in_working_style = line.lower() == "## working style"
            continue

        field_match = _FIELD_RE.match(line)
        if field_match:
            label = field_match.group(1).strip().lower()
            value = _clean_field_value(field_match.group(2))
            if label == "name":
                profile.name = value
            elif label == "what to call them":
                profile.preferred_name = value
            elif label == "pronouns":
                profile.pronouns = value
            elif label == "timezone":
                profile.timezone = value
            elif label == "context":
                profile.context = value
            elif label == "preferences":
                profile.preferences = _split_preferences(value)
            continue

        if in_working_style and line.startswith("- "):
            item = _clean_field_value(line[2:])
            if item and item not in profile.working_style:
                profile.working_style.append(item)

    return _strip_default_template_profile(profile)


def load_user_profile_from_path(path: str | Path) -> WorkspaceUserProfile:
    profile_path = Path(path)
    if not profile_path.exists():
        return WorkspaceUserProfile(source_path=str(profile_path))
    text = profile_path.read_text(encoding="utf-8", errors="ignore")
    return parse_user_profile_markdown(text, source_path=str(profile_path))
