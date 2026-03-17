from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable


def classify_category_with_llm(
    text: str,
    *,
    run_coro_sync: Callable[[Any], Any],
    normalize_category_label: Callable[[str], str | None],
    model: str = "gemini/gemini-2.5-flash",
) -> str | None:
    prompt = (
        "Classifique a memoria em UMA categoria desta lista: "
        "preferences, relationships, knowledge, context, decisions, skills, events, facts. "
        "Retorne apenas o nome da categoria.\n\n"
        f"MEMORIA:\n{str(text or '').strip()}"
    )
    try:
        import litellm  # type: ignore

        response = run_coro_sync(
            litellm.acompletion(
                model=model,
                temperature=0,
                max_tokens=12,
                messages=[
                    {"role": "system", "content": "Voce responde somente com uma categoria valida."},
                    {"role": "user", "content": prompt},
                ],
            )
        )
        content = ""
        choices = getattr(response, "choices", None)
        if choices is None and isinstance(response, dict):
            choices = response.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            message = first.get("message") if isinstance(first, dict) else getattr(first, "message", None)
            if isinstance(message, dict):
                content = str(message.get("content", "") or "")
            else:
                content = str(getattr(message, "content", "") or "")
        return normalize_category_label(content)
    except Exception:
        return None


def normalize_category_label(raw_label: str, *, memory_categories: set[str] | frozenset[str]) -> str | None:
    normalized = re.sub(r"[^a-z_\s]", " ", str(raw_label or "").strip().lower())
    normalized = " ".join(normalized.split())
    if not normalized:
        return None
    if normalized in memory_categories:
        return normalized

    synonym_map: dict[str, tuple[str, ...]] = {
        "preferences": ("preference", "likes", "dislikes", "style", "habit"),
        "relationships": ("relationship", "contact", "family", "friend", "coworker", "team"),
        "knowledge": ("know", "knowledge", "information", "reference", "learned", "learning"),
        "context": ("context", "note", "background"),
        "decisions": ("decision", "chosen", "resolved", "resolution", "plan"),
        "skills": ("skill", "ability", "capability", "how to", "expertise"),
        "events": ("event", "schedule", "deadline", "meeting", "travel", "trip", "birthday"),
        "facts": ("fact", "factual"),
    }
    for category, aliases in synonym_map.items():
        if normalized == category:
            return category
        if any(alias in normalized for alias in aliases):
            return category
    return None


def extract_entities(
    text: str,
    *,
    entity_url_re: re.Pattern[str],
    entity_email_re: re.Pattern[str],
    entity_date_re: re.Pattern[str],
    entity_time_re: re.Pattern[str],
) -> dict[str, list[str]]:
    raw = str(text or "")
    entities = {
        "urls": entity_url_re.findall(raw),
        "emails": entity_email_re.findall(raw),
        "dates": entity_date_re.findall(raw),
        "times": entity_time_re.findall(raw),
    }
    out: dict[str, list[str]] = {}
    for key, values in entities.items():
        unique: list[str] = []
        for value in values:
            clean = str(value or "").strip()
            if clean and clean not in unique:
                unique.append(clean)
        out[key] = unique
    return out


def normalize_entity_value(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def entity_match_score(
    query_entities: dict[str, list[str]],
    memory_entities: dict[str, list[str]],
    *,
    entity_match_weights: dict[str, float],
    entity_match_max_boost: float,
    normalize_entity_value_fn: Callable[[str], str],
) -> float:
    score = 0.0
    for entity_type, weight in entity_match_weights.items():
        query_values_raw = query_entities.get(entity_type, []) if isinstance(query_entities, dict) else []
        memory_values_raw = memory_entities.get(entity_type, []) if isinstance(memory_entities, dict) else []
        query_values = {
            normalize_entity_value_fn(item)
            for item in query_values_raw
            if normalize_entity_value_fn(item)
        }
        memory_values = {
            normalize_entity_value_fn(item)
            for item in memory_values_raw
            if normalize_entity_value_fn(item)
        }
        if not query_values or not memory_values:
            continue
        overlap = len(query_values.intersection(memory_values))
        if overlap <= 0:
            continue
        score += min(float(weight), float(weight) * float(overlap))
    return max(0.0, min(entity_match_max_boost, round(score, 6)))


def heuristic_category(
    text: str,
    source: str,
    *,
    extract_entities_fn: Callable[[str], dict[str, list[str]]],
) -> str:
    normalized = str(text or "").lower()
    source_norm = str(source or "").lower()
    entities = extract_entities_fn(text)
    has_date_time = bool(entities["dates"] or entities["times"])
    has_knowledge_entities = bool(entities["urls"] or entities["emails"])
    if any(token in normalized for token in ("prefer", "preference", "always", "never", "gosto", "prefiro")):
        return "preferences"
    if any(token in normalized for token in ("decide", "decision", "we will", "vamos", "escolhemos", "resolved")):
        return "decisions"
    if any(token in normalized for token in ("can ", "how to", "skill", "know how", "sei ", "consigo")):
        return "skills"
    if any(token in normalized for token in ("name is", "works at", "friend", "wife", "husband", "team", "cliente", "parceiro")):
        return "relationships"
    if has_date_time or any(
        token in normalized
        for token in (
            "deadline",
            "meeting",
            "appointment",
            "schedule",
            "trip",
            "travel",
            "birthday",
            "tomorrow",
            "next week",
            "flight",
        )
    ):
        return "events"
    if has_knowledge_entities or any(
        token in normalized
        for token in (
            "learn",
            "learned",
            "know",
            "knowledge",
            "documentation",
            "docs",
            "guide",
            "tutorial",
            "reference",
        )
    ):
        return "knowledge"
    if source_norm.startswith("curated:") or "fact" in normalized or "timezone" in normalized:
        return "facts"
    return "context"


def categorize_memory(
    text: str,
    source: str,
    *,
    memory_auto_categorize: bool,
    memory_categories: set[str] | frozenset[str],
    classify_category_with_llm_fn: Callable[[str], str | None],
    heuristic_category_fn: Callable[[str, str], str],
) -> str:
    if not memory_auto_categorize:
        return "context"
    by_llm = classify_category_with_llm_fn(text)
    if by_llm in memory_categories:
        return by_llm
    return heuristic_category_fn(text, source)


def memory_content_hash(text: str, memory_type: str) -> str:
    normalized = " ".join(str(text or "").strip().lower().split())
    content = f"{memory_type}:{normalized}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def infer_memory_type(
    text: str,
    source: str,
    *,
    category: str = "",
    infer_happened_at_fn: Callable[[str], str],
) -> str:
    normalized = str(text or "").strip().lower()
    source_norm = str(source or "").strip().lower()
    category_norm = str(category or "").strip().lower()
    happened_at = infer_happened_at_fn(text)

    if source_norm.startswith("tool:") or source_norm.startswith("process:") or " tool " in f" {normalized} ":
        return "tool"
    if category_norm in {"preferences", "relationships"}:
        return "profile"
    if category_norm == "skills":
        return "skill"
    if category_norm == "events":
        return "event"
    if any(token in normalized for token in ("prefer", "preference", "timezone", "language", "my name", "sou ", "i am ")):
        return "profile"
    if any(token in normalized for token in ("every ", "usually", "often", "habit", "always", "normalmente", "costumo")):
        return "behavior"
    if happened_at or any(
        token in normalized
        for token in ("meeting", "deadline", "trip", "travel", "launch", "release", "weekend", "tomorrow", "today", "yesterday")
    ):
        return "event"
    if any(token in normalized for token in ("how to", "workflow", "runbook", "guide", "tutorial", "playbook", "can use", "sei fazer")):
        return "skill"
    return "knowledge"


def infer_happened_at(text: str, *, now_utc: Callable[[], datetime]) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""

    exact_dt = re.search(r"\b(\d{4}-\d{2}-\d{2})[tT ](\d{1,2}:\d{2})(?::\d{2})?\b", raw)
    if exact_dt:
        date_part = exact_dt.group(1)
        time_part = exact_dt.group(2)
        return f"{date_part}T{time_part}:00+00:00"

    exact_date = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", raw)
    if exact_date:
        return f"{exact_date.group(1)}T00:00:00+00:00"

    lowered = raw.lower()
    today = now_utc().date()
    if "tomorrow" in lowered:
        return datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).isoformat()
    if "yesterday" in lowered:
        return datetime.combine(today - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).isoformat()
    if "today" in lowered:
        return datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc).isoformat()
    return ""


def prepare_memory_metadata(
    *,
    text: str,
    source: str,
    metadata: dict[str, Any] | None,
    memory_type: str,
    happened_at: str,
    normalize_memory_metadata: Callable[[Any], dict[str, Any]],
    extract_entities_fn: Callable[[str], dict[str, list[str]]],
    source_session_key_fn: Callable[[str], str],
    memory_content_hash_fn: Callable[[str, str], str],
) -> dict[str, Any]:
    prepared = normalize_memory_metadata(metadata)
    entities = extract_entities_fn(text)
    non_empty_entities = {key: value for key, value in entities.items() if value}
    if non_empty_entities and "entities" not in prepared:
        prepared["entities"] = non_empty_entities
    if happened_at and "happened_at_hint" not in prepared:
        prepared["happened_at_hint"] = happened_at
    source_session = source_session_key_fn(source)
    if source_session and "source_session" not in prepared:
        prepared["source_session"] = source_session
    prepared.setdefault("content_hash", memory_content_hash_fn(text, memory_type))
    return prepared


__all__ = [
    "categorize_memory",
    "classify_category_with_llm",
    "entity_match_score",
    "extract_entities",
    "heuristic_category",
    "infer_happened_at",
    "infer_memory_type",
    "memory_content_hash",
    "normalize_category_label",
    "normalize_entity_value",
    "prepare_memory_metadata",
]
