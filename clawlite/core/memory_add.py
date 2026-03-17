from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable


def build_pending_record(
    *,
    text: str,
    source: str,
    raw_resource_text: str | None,
    user_id: str,
    shared: bool,
    modality: str,
    metadata: dict[str, Any] | None,
    reasoning_layer: str | None,
    confidence: float | None,
    memory_type: str | None,
    happened_at: str | None,
    decay_rate: float | None,
    normalize_user_id: Callable[[str], str],
    categorize_memory: Callable[[str, str], str],
    normalize_memory_type: Callable[[Any], str],
    infer_memory_type: Callable[[str, str], str],
    infer_happened_at: Callable[[str], str],
    normalize_decay_rate: Callable[..., float],
    default_decay_rate: Callable[..., float],
    memory_scope_key: Callable[..., str],
    prepare_memory_metadata: Callable[..., dict[str, Any]],
    seed_reinforcement_metadata: Callable[..., dict[str, Any]],
    normalize_reasoning_layer: Callable[[Any], str],
    normalize_confidence: Callable[..., float],
    detect_emotional_tone: Callable[[str], str],
    emotional_tracking: bool,
    memory_record_cls: Callable[..., Any],
    metadata_content_hash: Callable[[dict[str, Any] | None], str],
    memory_content_hash: Callable[[str, str], str],
) -> tuple[Any, str, str, str, str, bool]:
    clean = text.strip()
    if not clean:
        raise ValueError("memory text must not be empty")
    clean_user = normalize_user_id(user_id)
    category = categorize_memory(clean, source)
    memory_basis = str(raw_resource_text or clean)
    resolved_memory_type = normalize_memory_type(memory_type or infer_memory_type(memory_basis, source, category=category))
    resolved_happened_at = str(happened_at or infer_happened_at(memory_basis) or "")
    resolved_decay_rate = normalize_decay_rate(
        decay_rate,
        default=default_decay_rate(
            memory_type=resolved_memory_type,
            category=category,
            happened_at=resolved_happened_at,
        ),
    )
    reinforced_at = datetime.now(timezone.utc).isoformat()
    scope_key = memory_scope_key(user_id=clean_user, shared=shared)
    resolved_metadata = prepare_memory_metadata(
        text=memory_basis,
        source=source,
        metadata=metadata,
        memory_type=resolved_memory_type,
        happened_at=resolved_happened_at,
    )
    resolved_metadata = seed_reinforcement_metadata(
        resolved_metadata,
        source=source,
        scope_key=scope_key,
        reinforced_at=reinforced_at,
    )
    row = memory_record_cls(
        id=uuid.uuid4().hex,
        text=clean,
        source=source,
        created_at=reinforced_at,
        category=category,
        user_id=clean_user,
        layer="item",
        reasoning_layer=normalize_reasoning_layer(reasoning_layer),
        modality=str(modality or "text").strip().lower() or "text",
        confidence=normalize_confidence(confidence, default=1.0),
        decay_rate=resolved_decay_rate,
        emotional_tone=detect_emotional_tone(clean) if emotional_tracking else "neutral",
        memory_type=resolved_memory_type,
        happened_at=resolved_happened_at,
        metadata=resolved_metadata,
    )
    content_hash = metadata_content_hash(row.metadata) or memory_content_hash(memory_basis, resolved_memory_type)
    return row, content_hash, scope_key, reinforced_at, str(raw_resource_text or clean), (shared or clean_user != "default")


def finalize_added_record(
    *,
    row: Any,
    created_new: bool,
    clean_text: str,
    resource_id: str | None,
    diagnostics: dict[str, Any],
    generate_embedding: Callable[[str], list[float] | None],
    append_embedding: Callable[..., None],
    update_profile_from_record: Callable[[Any], None],
    prune_history: Callable[[], None],
    link_record_resource: Callable[[str, str], None],
) -> Any:
    if created_new:
        diagnostics["reinforcement_creates"] = int(diagnostics.get("reinforcement_creates", 0) or 0) + 1
        embedding = generate_embedding(clean_text)
        if embedding is not None:
            try:
                append_embedding(
                    record_id=row.id,
                    embedding=embedding,
                    created_at=row.created_at,
                    source=row.source,
                )
            except Exception:
                pass
    else:
        diagnostics["reinforcement_hits"] = int(diagnostics.get("reinforcement_hits", 0) or 0) + 1
    update_profile_from_record(row)
    prune_history()
    if resource_id:
        try:
            link_record_resource(row.id, resource_id)
        except Exception:
            pass
    return row


__all__ = [
    "build_pending_record",
    "finalize_added_record",
]
