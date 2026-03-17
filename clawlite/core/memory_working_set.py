from __future__ import annotations

import re
from typing import Any, Callable


def normalize_user_id(user_id: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(user_id or "default").strip())
    return clean or "default"


def normalize_session_id(session_id: str) -> str:
    return str(session_id or "").strip()


def parent_session_id(
    session_id: str,
    *,
    normalize_session_id_fn: Callable[[str], str],
) -> str:
    clean = normalize_session_id_fn(session_id)
    if not clean:
        return ""
    marker = ":subagent"
    if clean.endswith(marker):
        return clean[: -len(marker)].rstrip(":")
    if marker in clean:
        head, _, _ = clean.rpartition(marker)
        return head.rstrip(":")
    return ""


def working_memory_share_group(
    session_id: str,
    *,
    normalize_session_id_fn: Callable[[str], str],
    parent_session_id_fn: Callable[[str], str],
) -> str:
    clean = normalize_session_id_fn(session_id)
    if not clean:
        return ""
    parent = parent_session_id_fn(clean)
    return parent or clean


def default_working_memory_share_scope(
    session_id: str,
    *,
    parent_session_id_fn: Callable[[str], str],
) -> str:
    return "parent" if parent_session_id_fn(session_id) else "family"


def normalize_working_memory_share_scope(
    value: Any,
    *,
    session_id: str,
    allowed_scopes: set[str] | frozenset[str],
    default_scope_fn: Callable[[str], str],
) -> str:
    clean = str(value or "").strip().lower()
    if clean in allowed_scopes:
        return clean
    return default_scope_fn(session_id)


def normalize_working_memory_promotion_state(value: Any) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    try:
        message_count = int(payload.get("last_promoted_message_count", payload.get("lastPromotedMessageCount", 0)) or 0)
    except Exception:
        message_count = 0
    try:
        total = int(payload.get("total_promotions", payload.get("totalPromotions", 0)) or 0)
    except Exception:
        total = 0
    return {
        "last_promoted_signature": str(
            payload.get("last_promoted_signature", payload.get("lastPromotedSignature", "")) or ""
        ).strip(),
        "last_promoted_at": str(payload.get("last_promoted_at", payload.get("lastPromotedAt", "")) or "").strip(),
        "last_promoted_message_count": max(0, message_count),
        "total_promotions": max(0, total),
    }


def default_working_memory_state() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": "",
        "sessions": {},
    }


def normalize_working_memory_entry(
    payload: Any,
    *,
    session_id: str,
    fallback_user_id: str,
    normalize_session_id_fn: Callable[[str], str],
    normalize_user_id_fn: Callable[[str], str],
    parent_session_id_fn: Callable[[str], str],
    normalize_working_memory_share_scope_fn: Callable[[Any, str], str],
    normalize_memory_metadata_fn: Callable[[Any], dict[str, Any]],
    utcnow_iso: Callable[[], str],
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    clean_session_id = normalize_session_id_fn(str(payload.get("session_id", session_id) or session_id))
    if not clean_session_id:
        clean_session_id = normalize_session_id_fn(session_id)
    role = str(payload.get("role", "") or "").strip().lower() or "user"
    content = " ".join(str(payload.get("content", payload.get("text", "")) or "").split())
    if not content:
        return None
    created_at = str(payload.get("created_at", payload.get("createdAt", "")) or "").strip() or utcnow_iso()
    parent_id = normalize_session_id_fn(str(payload.get("parent_session_id", payload.get("parentSessionId", "")) or ""))
    if not parent_id:
        parent_id = parent_session_id_fn(clean_session_id)
    share_group = normalize_session_id_fn(str(payload.get("share_group", payload.get("shareGroup", "")) or ""))
    if not share_group:
        share_group = parent_id or clean_session_id
    share_scope = normalize_working_memory_share_scope_fn(
        payload.get("share_scope", payload.get("shareScope", "")),
        clean_session_id,
    )
    metadata = normalize_memory_metadata_fn(payload.get("metadata", {}))
    return {
        "session_id": clean_session_id,
        "role": role,
        "content": content,
        "created_at": created_at,
        "user_id": normalize_user_id_fn(str(payload.get("user_id", payload.get("userId", fallback_user_id)) or fallback_user_id)),
        "share_group": share_group,
        "share_scope": share_scope,
        "parent_session_id": parent_id,
        "metadata": metadata,
    }


def normalize_working_memory_session(
    session_id: str,
    payload: Any,
    *,
    normalize_session_id_fn: Callable[[str], str],
    normalize_user_id_fn: Callable[[str], str],
    parent_session_id_fn: Callable[[str], str],
    normalize_working_memory_share_scope_fn: Callable[[Any, str], str],
    normalize_working_memory_promotion_state_fn: Callable[[Any], dict[str, Any]],
    normalize_working_memory_entry_fn: Callable[[Any, str, str], dict[str, Any] | None],
    max_messages_per_session: int,
) -> dict[str, Any] | None:
    clean_session_id = normalize_session_id_fn(session_id)
    if not clean_session_id:
        return None
    raw = payload if isinstance(payload, dict) else {}
    parent_id = normalize_session_id_fn(str(raw.get("parent_session_id", raw.get("parentSessionId", "")) or ""))
    if not parent_id:
        parent_id = parent_session_id_fn(clean_session_id)
    share_group = normalize_session_id_fn(str(raw.get("share_group", raw.get("shareGroup", "")) or ""))
    if not share_group:
        share_group = parent_id or clean_session_id
    share_scope = normalize_working_memory_share_scope_fn(
        raw.get("share_scope", raw.get("shareScope", "")),
        clean_session_id,
    )
    updated_at = str(raw.get("updated_at", raw.get("updatedAt", "")) or "").strip()
    user_id = normalize_user_id_fn(str(raw.get("user_id", raw.get("userId", "default")) or "default"))
    promotion = normalize_working_memory_promotion_state_fn(raw.get("promotion", {}))
    messages_raw = raw.get("messages", [])
    messages: list[dict[str, Any]] = []
    if isinstance(messages_raw, list):
        for item in messages_raw:
            normalized = normalize_working_memory_entry_fn(item, clean_session_id, user_id)
            if normalized is not None:
                messages.append(normalized)
    if messages:
        messages = sorted(messages, key=lambda item: str(item.get("created_at", "") or ""))[-max_messages_per_session:]
        if not updated_at:
            updated_at = str(messages[-1].get("created_at", "") or "")
        user_id = str(messages[-1].get("user_id", user_id) or user_id)
    return {
        "session_id": clean_session_id,
        "user_id": user_id,
        "share_group": share_group,
        "share_scope": share_scope,
        "parent_session_id": parent_id,
        "promotion": promotion,
        "updated_at": updated_at,
        "messages": messages,
    }


def normalize_working_memory_state_payload(
    payload: Any,
    *,
    normalize_working_memory_session_fn: Callable[[str, Any], dict[str, Any] | None],
    max_sessions: int,
) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    sessions_raw = raw.get("sessions", {})
    sessions: dict[str, dict[str, Any]] = {}
    if isinstance(sessions_raw, dict):
        for key, value in sessions_raw.items():
            normalized = normalize_working_memory_session_fn(str(key or ""), value)
            if normalized is not None:
                sessions[normalized["session_id"]] = normalized
    if len(sessions) > max_sessions:
        ordered = sorted(sessions.values(), key=lambda item: str(item.get("updated_at", "") or ""))
        sessions = {item["session_id"]: item for item in ordered[-max_sessions:]}
    updated_at = str(raw.get("updated_at", raw.get("updatedAt", "")) or "").strip()
    if not updated_at and sessions:
        updated_at = max(str(item.get("updated_at", "") or "") for item in sessions.values())
    return {
        "version": 1,
        "updated_at": updated_at,
        "sessions": sessions,
    }


def working_memory_related_sessions(
    sessions: dict[str, dict[str, Any]],
    primary: dict[str, Any],
    *,
    include_shared_subagents: bool,
    normalize_working_memory_session_fn: Callable[[str, Any], dict[str, Any] | None],
    normalize_working_memory_share_scope_fn: Callable[[Any, str], str],
) -> list[dict[str, Any]]:
    if not include_shared_subagents:
        return [primary]
    primary_session_id = str(primary.get("session_id", "") or "")
    share_group = str(primary.get("share_group", "") or "")
    parent_id = str(primary.get("parent_session_id", "") or "")
    share_scope = normalize_working_memory_share_scope_fn(primary.get("share_scope", ""), primary_session_id)
    related = [primary]
    if share_scope == "private" or not share_group:
        return related

    for other_session_id, payload in sessions.items():
        if str(other_session_id or "") == primary_session_id:
            continue
        normalized = normalize_working_memory_session_fn(str(other_session_id or ""), payload)
        if normalized is None:
            continue
        if str(normalized.get("share_group", "") or "") != share_group:
            continue
        other_id = str(normalized.get("session_id", "") or "")
        other_scope = normalize_working_memory_share_scope_fn(normalized.get("share_scope", ""), other_id)
        is_parent = bool(parent_id and other_id == parent_id)
        is_child = bool(primary_session_id and str(normalized.get("parent_session_id", "") or "") == primary_session_id)
        is_sibling = bool(parent_id and str(normalized.get("parent_session_id", "") or "") == parent_id)

        if is_parent:
            related.append(normalized)
            continue
        if is_child and share_scope == "family" and other_scope in {"parent", "family"}:
            related.append(normalized)
            continue
        if is_sibling and share_scope == "family" and other_scope == "family":
            related.append(normalized)
    return related


def working_memory_recent_direct_messages(
    entry: dict[str, Any],
    *,
    normalize_working_memory_entry_fn: Callable[[Any, str, str], dict[str, Any] | None],
) -> list[dict[str, Any]]:
    messages_raw = entry.get("messages", [])
    if not isinstance(messages_raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in messages_raw:
        normalized = normalize_working_memory_entry_fn(
            item,
            str(entry.get("session_id", "") or ""),
            str(entry.get("user_id", "default") or "default"),
        )
        if normalized is not None:
            out.append(normalized)
    return out


def is_working_episode_record(
    row: Any,
    *,
    normalize_memory_metadata_fn: Callable[[Any], dict[str, Any]],
) -> bool:
    metadata = normalize_memory_metadata_fn(getattr(row, "metadata", {}))
    if bool(metadata.get("working_memory_promoted", False)):
        return True
    return str(getattr(row, "source", "") or "").startswith("working-session:")


def working_episode_context(
    row: Any,
    *,
    normalize_memory_metadata_fn: Callable[[Any], dict[str, Any]],
    normalize_session_id_fn: Callable[[str], str],
    parent_session_id_fn: Callable[[str], str],
    working_memory_share_group_fn: Callable[[str], str],
    normalize_working_memory_share_scope_fn: Callable[[Any, str], str],
) -> dict[str, str]:
    metadata = normalize_memory_metadata_fn(getattr(row, "metadata", {}))
    session_id = normalize_session_id_fn(
        str(metadata.get("working_memory_session_id", metadata.get("session_id", "")) or "")
    )
    if not session_id and str(getattr(row, "source", "") or "").startswith("working-session:"):
        session_id = normalize_session_id_fn(str(getattr(row, "source", "") or "")[len("working-session:") :])
    parent_id = normalize_session_id_fn(
        str(metadata.get("working_memory_parent_session_id", metadata.get("parent_session_id", "")) or "")
    )
    if not parent_id:
        parent_id = parent_session_id_fn(session_id)
    share_group = normalize_session_id_fn(
        str(metadata.get("working_memory_share_group", metadata.get("share_group", "")) or "")
    )
    if not share_group:
        share_group = working_memory_share_group_fn(session_id)
    share_scope = normalize_working_memory_share_scope_fn(
        metadata.get("working_memory_share_scope", metadata.get("share_scope", "")),
        session_id,
    )
    return {
        "session_id": session_id,
        "parent_session_id": parent_id,
        "share_group": share_group,
        "share_scope": share_scope,
    }


def working_episode_visible_in_session(
    row: Any,
    *,
    session_id: str,
    normalize_session_id_fn: Callable[[str], str],
    is_working_episode_record_fn: Callable[[Any], bool],
    working_episode_context_fn: Callable[[Any], dict[str, str]],
    parent_session_id_fn: Callable[[str], str],
    working_memory_share_group_fn: Callable[[str], str],
) -> bool:
    clean_session_id = normalize_session_id_fn(session_id)
    if not is_working_episode_record_fn(row) or not clean_session_id:
        return True
    row_ctx = working_episode_context_fn(row)
    row_session_id = str(row_ctx.get("session_id", "") or "")
    row_parent_session_id = str(row_ctx.get("parent_session_id", "") or "")
    row_share_group = str(row_ctx.get("share_group", "") or "")
    row_share_scope = str(row_ctx.get("share_scope", "") or "")
    if not row_session_id:
        return True
    if row_session_id == clean_session_id:
        return True
    current_parent = parent_session_id_fn(clean_session_id)
    current_group = working_memory_share_group_fn(clean_session_id)
    if not row_share_group or row_share_group != current_group:
        return False
    if row_share_scope == "private":
        return False
    if clean_session_id == row_parent_session_id:
        return row_share_scope in {"parent", "family"}
    if current_parent and row_session_id == current_parent:
        return row_share_scope == "family"
    if row_parent_session_id == clean_session_id:
        return row_share_scope == "family"
    if current_parent and row_parent_session_id == current_parent:
        return row_share_scope == "family"
    return False


def episodic_session_boost(
    row: Any,
    *,
    session_id: str,
    normalize_session_id_fn: Callable[[str], str],
    is_working_episode_record_fn: Callable[[Any], bool],
    working_episode_context_fn: Callable[[Any], dict[str, str]],
    working_episode_visible_in_session_fn: Callable[[Any, str], bool],
    parent_session_id_fn: Callable[[str], str],
) -> float:
    clean_session_id = normalize_session_id_fn(session_id)
    if not clean_session_id or not is_working_episode_record_fn(row):
        return 0.0
    row_ctx = working_episode_context_fn(row)
    row_session_id = str(row_ctx.get("session_id", "") or "")
    row_parent_session_id = str(row_ctx.get("parent_session_id", "") or "")
    row_share_scope = str(row_ctx.get("share_scope", "") or "")
    if row_session_id == clean_session_id:
        return 0.6
    if not working_episode_visible_in_session_fn(row, clean_session_id):
        return 0.0
    current_parent = parent_session_id_fn(clean_session_id)
    if clean_session_id == row_parent_session_id:
        return 0.38 if row_share_scope == "parent" else 0.46
    if row_parent_session_id == clean_session_id:
        return 0.34 if row_share_scope == "family" else 0.0
    if current_parent and row_parent_session_id == current_parent and row_share_scope == "family":
        return 0.28
    return 0.14


def episodic_digest_label(
    *,
    active_session_id: str,
    target_session_id: str,
    normalize_session_id_fn: Callable[[str], str],
    parent_session_id_fn: Callable[[str], str],
) -> str:
    clean_active = normalize_session_id_fn(active_session_id)
    clean_target = normalize_session_id_fn(target_session_id)
    if not clean_target:
        return "unknown"
    if clean_target == clean_active:
        return "current"
    parent = parent_session_id_fn(clean_active)
    if clean_target == parent:
        return "parent"
    if parent_session_id_fn(clean_target) == clean_active:
        return "child"
    if parent and parent_session_id_fn(clean_target) == parent:
        return "sibling"
    return "related"


def working_memory_episode_summary(
    session_id: str,
    messages: list[dict[str, Any]],
    *,
    promotion_window: int,
    normalize_session_id_fn: Callable[[str], str],
    extract_topics_fn: Callable[[str], list[str]],
    compact_whitespace_fn: Callable[[str], str],
) -> str:
    clean_session_id = normalize_session_id_fn(session_id) or "unknown"
    recent = messages[-promotion_window:]
    user_rows = [str(item.get("content", "") or "") for item in recent if str(item.get("role", "") or "") == "user"]
    assistant_rows = [str(item.get("content", "") or "") for item in recent if str(item.get("role", "") or "") == "assistant"]
    topics: list[str] = []
    for item in recent:
        for topic in extract_topics_fn(str(item.get("content", "") or "")):
            if topic not in topics:
                topics.append(topic)
    details = [f"Session episode for {clean_session_id} captured {len(recent)} recent messages."]
    if topics:
        details.append(f"Topics: {', '.join(topics[:6])}.")
    if user_rows:
        details.append(f"Latest user intent: {compact_whitespace_fn(user_rows[-1])[:180]}.")
    if assistant_rows:
        details.append(f"Latest assistant outcome: {compact_whitespace_fn(assistant_rows[-1])[:180]}.")
    return " ".join(detail for detail in details if detail).strip()


__all__ = [
    "default_working_memory_share_scope",
    "default_working_memory_state",
    "episodic_digest_label",
    "episodic_session_boost",
    "is_working_episode_record",
    "normalize_session_id",
    "normalize_user_id",
    "normalize_working_memory_entry",
    "normalize_working_memory_promotion_state",
    "normalize_working_memory_session",
    "normalize_working_memory_share_scope",
    "normalize_working_memory_state_payload",
    "parent_session_id",
    "working_episode_context",
    "working_episode_visible_in_session",
    "working_memory_episode_summary",
    "working_memory_recent_direct_messages",
    "working_memory_related_sessions",
    "working_memory_share_group",
]
