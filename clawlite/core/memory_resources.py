from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable


def create_resource(*, backend: Any, resource: Any) -> str:
    backend.upsert_resource(
        {
            "id": resource.id,
            "name": resource.name,
            "kind": resource.kind,
            "description": resource.description,
            "tags": json.dumps(resource.tags),
            "created_at": resource.created_at,
            "updated_at": resource.updated_at,
        }
    )
    return str(resource.id)


def get_resource(
    *,
    backend: Any,
    resource_id: str,
    resource_context_cls: Callable[..., Any],
) -> Any | None:
    row = backend.fetch_resource(resource_id)
    if row is None:
        return None
    tags: list[str] = []
    try:
        tags = json.loads(row.get("tags") or "[]")
    except Exception:
        pass
    return resource_context_cls(
        id=row["id"],
        name=row["name"],
        kind=row["kind"],
        description=row.get("description", ""),
        tags=tags,
        created_at=row.get("created_at", ""),
        updated_at=row.get("updated_at", ""),
    )


def list_resources(
    *,
    backend: Any,
    resource_context_cls: Callable[..., Any],
) -> list[Any]:
    rows = backend.fetch_all_resources()
    resources: list[Any] = []
    for row in rows:
        resource_id = str(row.get("id", "") or "")
        if not resource_id:
            continue
        resource = get_resource(
            backend=backend,
            resource_id=resource_id,
            resource_context_cls=resource_context_cls,
        )
        if resource is not None:
            resources.append(resource)
    return resources


def fetch_record_by_id(
    *,
    backend: Any,
    record_id: str,
    item_layer_value: str,
    memory_record_cls: Callable[..., Any],
) -> Any | None:
    all_rows = backend.fetch_layer_records(layer=item_layer_value, limit=50000)
    for row in all_rows:
        if row.get("record_id") != record_id:
            continue
        payload = row.get("payload", {})
        if not isinstance(payload, dict) or not payload.get("text"):
            continue
        return memory_record_cls(
            id=str(payload.get("id", record_id)),
            text=str(payload.get("text", "")),
            source=str(payload.get("source", "user")),
            created_at=str(payload.get("created_at", row.get("created_at", ""))),
            category=str(payload.get("category", row.get("category", "context"))),
            user_id=str(payload.get("user_id", "default")),
            layer=str(payload.get("layer", item_layer_value)),
            reasoning_layer=str(payload.get("reasoning_layer", "fact")),
            modality=str(payload.get("modality", "text")),
            updated_at=str(payload.get("updated_at", "")),
            confidence=float(payload.get("confidence", 1.0)),
            decay_rate=float(payload.get("decay_rate", 0.0)),
            emotional_tone=str(payload.get("emotional_tone", "neutral")),
            memory_type=str(payload.get("memory_type", "knowledge")),
            happened_at=str(payload.get("happened_at", "")),
            metadata=payload.get("metadata", {}),
        )
    return None


def get_resource_records(
    *,
    backend: Any,
    resource_id: str,
    fetch_record_by_id_fn: Callable[[str], Any | None],
) -> list[Any]:
    record_ids = backend.fetch_records_by_resource(resource_id)
    results: list[Any] = []
    for rid in record_ids:
        rec = fetch_record_by_id_fn(rid)
        if rec is not None:
            results.append(rec)
    return results


def set_record_ttl(*, backend: Any, record_id: str, ttl_seconds: float) -> None:
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
    backend.set_ttl(record_id, expires_at)


def get_record_ttl(*, backend: Any, record_id: str) -> dict[str, str] | None:
    return backend.get_ttl(record_id)


def purge_expired_records(*, backend: Any) -> int:
    expired_ids = backend.fetch_expired_record_ids()
    if not expired_ids:
        return 0
    deleted = backend.delete_layer_records(set(expired_ids))
    backend.delete_ttl_entries(expired_ids)
    return int(deleted) if isinstance(deleted, int) else len(expired_ids)


__all__ = [
    "create_resource",
    "fetch_record_by_id",
    "get_record_ttl",
    "get_resource",
    "get_resource_records",
    "list_resources",
    "purge_expired_records",
    "set_record_ttl",
]
