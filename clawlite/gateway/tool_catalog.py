from __future__ import annotations

from typing import Any, Mapping

CATALOG_CONTRACT_VERSION = "2026-03-24"

REQUIRED_TOOL_ALIASES: dict[str, str] = {
    "bash": "exec",
    "apply-patch": "apply_patch",
    "read_file": "read",
    "write_file": "write",
    "edit_file": "edit",
    "memory_recall": "memory_search",
}

_GROUP_ORDER: tuple[tuple[str, str], ...] = (
    ("fs", "Files"),
    ("runtime", "Runtime"),
    ("web", "Web"),
    ("memory", "Memory"),
    ("sessions", "Sessions"),
    ("ui", "UI"),
    ("messaging", "Messaging"),
    ("automation", "Automation"),
    ("nodes", "Nodes"),
    ("agents", "Agents"),
    ("media", "Media"),
    ("other", "Other"),
)

_GROUP_BY_TOOL_ID: dict[str, str] = {
    "read": "fs",
    "read_file": "fs",
    "write": "fs",
    "write_file": "fs",
    "edit": "fs",
    "edit_file": "fs",
    "apply_patch": "fs",
    "list_dir": "fs",
    "exec": "runtime",
    "process": "runtime",
    "web_fetch": "web",
    "web_search": "web",
    "memory_recall": "memory",
    "memory_search": "memory",
    "memory_get": "memory",
    "memory_learn": "memory",
    "memory_forget": "memory",
    "memory_analyze": "memory",
    "sessions_list": "sessions",
    "sessions_history": "sessions",
    "sessions_send": "sessions",
    "sessions_spawn": "sessions",
    "subagents": "sessions",
    "session_status": "sessions",
    "message": "messaging",
    "cron": "automation",
    "agents_list": "agents",
    "spawn": "agents",
    "run_skill": "agents",
    "mcp": "nodes",
}

WS_METHODS: list[str] = [
    "connect",
    "ping",
    "health",
    "status",
    "chat.send",
    "message.send",
    "tools.catalog",
]


def parse_include_schema_flag(values: Mapping[str, Any] | None) -> bool:
    if not values:
        return False
    for key in ("include_schema", "includeSchema"):
        if key not in values:
            continue
        value = values.get(key)
        if isinstance(value, bool):
            return value
        normalized = str(value or "").strip().lower()
        if normalized in {"1", "true", "t", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "f", "no", "n", "off", ""}:
            return False
    return False


def _normalize_timeout_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        timeout_s = float(value)
    except (TypeError, ValueError):
        return None
    if timeout_s <= 0:
        return None
    return timeout_s


def build_tools_catalog_payload(tool_schema_rows: list[dict[str, Any]], *, include_schema: bool) -> dict[str, Any]:
    tools_by_id: dict[str, dict[str, Any]] = {}
    normalized_schema: list[dict[str, Any]] = []

    for row in tool_schema_rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "") or "").strip()
        if not name:
            continue
        description = str(row.get("description", "") or "").strip()
        cacheable = bool(row.get("cacheable", False))
        default_timeout_s = _normalize_timeout_value(row.get("default_timeout_s"))
        tools_by_id[name] = {
            "id": name,
            "label": name,
            "description": description,
            "cacheable": cacheable,
            "default_timeout_s": default_timeout_s,
        }
        normalized_row = dict(row)
        normalized_row["cacheable"] = cacheable
        normalized_row["default_timeout_s"] = default_timeout_s
        normalized_schema.append(normalized_row)

    grouped: dict[str, list[dict[str, Any]]] = {group_id: [] for group_id, _ in _GROUP_ORDER}
    for tool_id, payload in tools_by_id.items():
        group_id = _GROUP_BY_TOOL_ID.get(tool_id, "other")
        grouped.setdefault(group_id, []).append(payload)

    groups: list[dict[str, Any]] = []
    for group_id, group_label in _GROUP_ORDER:
        tools = sorted(grouped.get(group_id, []), key=lambda row: row["id"])
        if not tools:
            continue
        groups.append(
            {
                "id": group_id,
                "label": group_label,
                "count": len(tools),
                "tools": tools,
            }
        )

    largest_group = max(groups, key=lambda row: int(row.get("count", 0) or 0), default=None)
    summary = {
        "group_count": len(groups),
        "alias_count": len(REQUIRED_TOOL_ALIASES),
        "ws_method_count": len(WS_METHODS),
        "cacheable_count": sum(1 for tool in tools_by_id.values() if bool(tool.get("cacheable", False))),
        "custom_timeout_count": sum(1 for tool in tools_by_id.values() if tool.get("default_timeout_s") is not None),
        "largest_group": {
            "id": str((largest_group or {}).get("id", "") or ""),
            "label": str((largest_group or {}).get("label", "") or ""),
            "count": int((largest_group or {}).get("count", 0) or 0),
        },
    }

    catalog: dict[str, Any] = {
        "contract_version": CATALOG_CONTRACT_VERSION,
        "tool_count": sum(len(group["tools"]) for group in groups),
        "aliases": dict(REQUIRED_TOOL_ALIASES),
        "groups": groups,
        "ws_methods": list(WS_METHODS),
        "summary": summary,
    }
    if include_schema:
        catalog["schema"] = sorted(normalized_schema, key=lambda row: str(row.get("name", "") or ""))
    return catalog
