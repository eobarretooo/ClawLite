from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


def profile_prompt_hint(
    *,
    load_json_dict: Callable[[Path, dict[str, Any]], dict[str, Any]],
    profile_path: Path,
    default_profile: Callable[[], dict[str, Any]],
    parse_iso_timestamp: Callable[[str], datetime],
) -> str:
    profile = load_json_dict(profile_path, default_profile())
    if not isinstance(profile, dict):
        return ""

    defaults = default_profile()
    lines: list[str] = []

    response_length = str(profile.get("response_length_preference", defaults.get("response_length_preference", "normal")) or "").strip()
    if response_length and response_length != str(defaults.get("response_length_preference", "normal")):
        lines.append(f"- Preferred response length: {response_length}")

    timezone_value = str(profile.get("timezone", defaults.get("timezone", "UTC")) or "").strip()
    if timezone_value and timezone_value != str(defaults.get("timezone", "UTC")):
        lines.append(f"- Timezone: {timezone_value}")

    language = str(profile.get("language", defaults.get("language", "pt-BR")) or "").strip()
    if language and language != str(defaults.get("language", "pt-BR")):
        lines.append(f"- Preferred language: {language}")

    emotional_baseline = str(profile.get("emotional_baseline", defaults.get("emotional_baseline", "neutral")) or "").strip()
    if emotional_baseline and emotional_baseline != str(defaults.get("emotional_baseline", "neutral")):
        lines.append(f"- Emotional baseline: {emotional_baseline}")

    interests_raw = profile.get("interests", [])
    interests = [str(item).strip() for item in interests_raw if str(item).strip()] if isinstance(interests_raw, list) else []
    if interests:
        lines.append(f"- Recurring interests: {', '.join(interests[:5])}")

    upcoming_raw = profile.get("upcoming_events", [])
    if isinstance(upcoming_raw, list):
        formatted: list[str] = []
        now = datetime.now(timezone.utc)
        for item in upcoming_raw[:3]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "") or "").strip()
            happened_at = str(item.get("happened_at", "") or "").strip()
            stamp = parse_iso_timestamp(happened_at)
            if not title or stamp.year <= 1:
                continue
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            if stamp < now - timedelta(days=1):
                continue
            formatted.append(f"{stamp.date().isoformat()} {title[:80]}")
        if formatted:
            lines.append(f"- Upcoming events: {'; '.join(formatted)}")

    if not lines:
        return ""

    return "\n".join(
        [
            "[User Profile]",
            *lines,
            "- Apply these preferences when relevant, without repeating them unless useful.",
        ]
    )


def extract_timezone(text: str) -> str | None:
    clean = str(text or "").lower()
    if not clean:
        return None
    offset_match = re.search(r"\butc\s*([+-]\d{1,2})\b", clean)
    if offset_match:
        return f"UTC{offset_match.group(1)}"
    if "sao paulo" in clean or "são paulo" in clean or re.search(r"\bsp\b", clean):
        return "America/Sao_Paulo"
    return None


def extract_topics(
    text: str,
    *,
    tokens: Callable[[str], list[str]],
    profile_topic_stopwords: set[str] | frozenset[str],
) -> list[str]:
    topics: list[str] = []
    for token in tokens(text):
        if len(token) < 4:
            continue
        if token in profile_topic_stopwords:
            continue
        if token.isdigit():
            continue
        if token not in topics:
            topics.append(token)
    return topics[:8]


def update_profile_from_text(
    text: str,
    *,
    load_json_dict: Callable[[Path, dict[str, Any]], dict[str, Any]],
    write_json_dict: Callable[[Path, dict[str, Any]], None],
    profile_path: Path,
    default_profile: Callable[[], dict[str, Any]],
    extract_timezone_fn: Callable[[str], str | None],
    extract_topics_fn: Callable[[str], list[str]],
    detect_emotional_tone: Callable[[str], str],
    utcnow_iso: Callable[[], str],
) -> None:
    clean = str(text or "").strip()
    if not clean:
        return
    profile = load_json_dict(profile_path, default_profile())
    changed = False
    lowered = clean.lower()

    if "prefiro respostas curtas" in lowered:
        if profile.get("response_length_preference") != "curto":
            profile["response_length_preference"] = "curto"
            changed = True

    timezone_value = extract_timezone_fn(clean)
    if timezone_value and profile.get("timezone") != timezone_value:
        profile["timezone"] = timezone_value
        changed = True

    topics = extract_topics_fn(clean)
    recurring_patterns = dict(profile.get("recurring_patterns", {}))
    if not isinstance(recurring_patterns, dict):
        recurring_patterns = {}
    interests = list(profile.get("interests", []))
    if not isinstance(interests, list):
        interests = []

    for topic in topics:
        topic_data = recurring_patterns.get(topic, {})
        if not isinstance(topic_data, dict):
            topic_data = {}
        previous_count = int(topic_data.get("count", 0) or 0)
        topic_data["count"] = previous_count + 1
        topic_data["last_seen"] = utcnow_iso()
        recurring_patterns[topic] = topic_data
        if topic_data["count"] >= 2 and topic not in interests:
            interests.append(topic)
            changed = True

    if recurring_patterns != profile.get("recurring_patterns"):
        profile["recurring_patterns"] = recurring_patterns
        changed = True
    if interests != profile.get("interests"):
        profile["interests"] = interests
        changed = True

    baseline = detect_emotional_tone(clean)
    if baseline != "neutral" and profile.get("emotional_baseline") != baseline:
        profile["emotional_baseline"] = baseline
        changed = True

    if changed:
        if not str(profile.get("learned_at", "")).strip():
            profile["learned_at"] = utcnow_iso()
        profile["updated_at"] = utcnow_iso()
        write_json_dict(profile_path, profile)


def update_profile_upcoming_events(
    record: Any,
    *,
    normalize_memory_type: Callable[[Any], str],
    parse_iso_timestamp: Callable[[str], datetime],
    load_json_dict: Callable[[Path, dict[str, Any]], dict[str, Any]],
    write_json_dict: Callable[[Path, dict[str, Any]], None],
    profile_path: Path,
    default_profile: Callable[[], dict[str, Any]],
    metadata_content_hash: Callable[[dict[str, Any] | None], str],
    compact_whitespace: Callable[[str], str],
    utcnow_iso: Callable[[], str],
) -> None:
    if normalize_memory_type(getattr(record, "memory_type", "knowledge")) != "event":
        return
    happened_at = parse_iso_timestamp(str(getattr(record, "happened_at", "") or ""))
    if happened_at.year <= 1:
        return
    if happened_at.tzinfo is None:
        happened_at = happened_at.replace(tzinfo=timezone.utc)
    if happened_at < datetime.now(timezone.utc) - timedelta(days=1):
        return

    profile = load_json_dict(profile_path, default_profile())
    upcoming_raw = profile.get("upcoming_events", [])
    upcoming_events = list(upcoming_raw) if isinstance(upcoming_raw, list) else []
    event_id = metadata_content_hash(getattr(record, "metadata", {})) or str(getattr(record, "id", "") or "")
    title = compact_whitespace(str(getattr(record, "text", "") or ""))[:160]
    if not title:
        return

    filtered: list[dict[str, Any]] = []
    for item in upcoming_events:
        if not isinstance(item, dict):
            continue
        existing_id = str(item.get("id", "") or "").strip()
        existing_stamp = parse_iso_timestamp(str(item.get("happened_at", "") or ""))
        if existing_stamp.year > 1 and existing_stamp.tzinfo is None:
            existing_stamp = existing_stamp.replace(tzinfo=timezone.utc)
        if existing_stamp.year > 1 and existing_stamp < datetime.now(timezone.utc) - timedelta(days=1):
            continue
        if existing_id == event_id:
            continue
        filtered.append(item)

    filtered.append(
        {
            "id": event_id,
            "memory_id": str(getattr(record, "id", "") or ""),
            "title": title,
            "happened_at": happened_at.isoformat(),
            "source": str(getattr(record, "source", "") or ""),
            "category": str(getattr(record, "category", "events") or "events"),
        }
    )
    filtered.sort(key=lambda item: str(item.get("happened_at", "") or ""))
    filtered = filtered[:12]

    if filtered != upcoming_events:
        profile["upcoming_events"] = filtered
        profile["updated_at"] = utcnow_iso()
        if not str(profile.get("learned_at", "")).strip():
            profile["learned_at"] = utcnow_iso()
        write_json_dict(profile_path, profile)


def update_profile_from_record(
    record: Any,
    *,
    normalize_memory_metadata: Callable[[Any], dict[str, Any]],
    update_profile_from_text_fn: Callable[[str], None],
    update_profile_upcoming_events_fn: Callable[[Any], None],
) -> None:
    metadata = normalize_memory_metadata(getattr(record, "metadata", {}))
    skip_profile_sync = bool(metadata.get("skip_profile_sync", False))
    if not skip_profile_sync:
        update_profile_from_text_fn(str(getattr(record, "text", "") or ""))
    update_profile_upcoming_events_fn(record)


__all__ = [
    "extract_timezone",
    "extract_topics",
    "profile_prompt_hint",
    "update_profile_from_record",
    "update_profile_from_text",
    "update_profile_upcoming_events",
]
