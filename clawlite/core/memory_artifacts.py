from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from clawlite.core.memory_layers import upsert_category_item_rows


def build_resource_layer_payload(
    *,
    record: Any,
    raw_text: str,
    resource_layer_value: str,
    encrypt_text_for_category: Callable[[str, str], str],
    normalize_reasoning_layer: Callable[[str], str],
    normalize_confidence: Callable[[Any], float],
) -> dict[str, Any]:
    category = str(getattr(record, "category", "context") or "context")
    payload = {
        "id": str(getattr(record, "id", "") or ""),
        "text": encrypt_text_for_category(str(raw_text or "").strip(), category),
        "source": str(getattr(record, "source", "") or ""),
        "category": category,
        "created_at": str(getattr(record, "created_at", "") or ""),
        "layer": resource_layer_value,
        "reasoning_layer": normalize_reasoning_layer(str(getattr(record, "reasoning_layer", "") or "")),
        "confidence": normalize_confidence(getattr(record, "confidence", 1.0)),
    }
    return payload


def append_resource_layer(
    *,
    record: Any,
    raw_text: str,
    resource_layer_value: str,
    encrypt_text_for_category: Callable[[str, str], str],
    normalize_reasoning_layer: Callable[[str], str],
    normalize_confidence: Callable[[Any], float],
    resource_file_for_timestamp: Callable[[str], Path],
    ensure_file: Callable[[Path], None],
    locked_file: Callable[..., Any],
    flush_and_fsync: Callable[[Any], None],
    backend_upsert_layer_record: Callable[..., Any] | None = None,
) -> None:
    payload = build_resource_layer_payload(
        record=record,
        raw_text=raw_text,
        resource_layer_value=resource_layer_value,
        encrypt_text_for_category=encrypt_text_for_category,
        normalize_reasoning_layer=normalize_reasoning_layer,
        normalize_confidence=normalize_confidence,
    )
    if not payload["id"] or not payload["text"]:
        return
    resource_file = resource_file_for_timestamp(str(payload["created_at"] or ""))
    ensure_file(resource_file)
    with locked_file(resource_file, "a", exclusive=True) as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        flush_and_fsync(fh)
    if backend_upsert_layer_record is None:
        return
    try:
        backend_upsert_layer_record(
            layer=resource_layer_value,
            record_id=payload["id"],
            payload=payload,
            category=payload["category"],
            created_at=payload["created_at"],
            updated_at=payload["created_at"],
        )
    except Exception:
        pass


def upsert_item_layer(
    *,
    record: Any,
    load_category_items: Callable[[str], list[dict[str, Any]]],
    serialize_hit: Callable[[Any], dict[str, Any]],
    encrypt_text_for_category: Callable[[str, str], str],
    write_category_items: Callable[[str, list[dict[str, Any]]], None],
    update_category_summary: Callable[[str], None],
    category_file_path: Callable[[str], Path],
    utcnow_iso: Callable[[], str],
    backend_upsert_layer_record: Callable[..., Any] | None,
    item_layer_value: str,
    category_layer_value: str,
) -> None:
    category, updated_rows = upsert_category_item_rows(
        record=record,
        rows=load_category_items(str(getattr(record, "category", "context") or "context")),
        serialize_hit=serialize_hit,
        encrypt_text_for_category=encrypt_text_for_category,
    )
    stored_payload = next(
        (dict(row) for row in updated_rows if str(row.get("id", "")).strip() == str(getattr(record, "id", "") or "").strip()),
        {},
    )
    write_category_items(category, updated_rows)
    update_category_summary(category)
    if backend_upsert_layer_record is None:
        return
    category_path = category_file_path(category)
    now_iso = utcnow_iso()
    try:
        backend_upsert_layer_record(
            layer=item_layer_value,
            record_id=str(getattr(record, "id", "") or ""),
            payload=stored_payload,
            category=category,
            created_at=str(getattr(record, "created_at", "") or ""),
            updated_at=str(getattr(record, "updated_at", "") or getattr(record, "created_at", "") or ""),
        )
        backend_upsert_layer_record(
            layer=category_layer_value,
            record_id=str(getattr(record, "id", "") or ""),
            payload={
                "category": category,
                "path": str(category_path),
                "updated_at": now_iso,
                "total_items": len(updated_rows),
            },
            category=category,
            created_at=str(getattr(record, "created_at", "") or now_iso),
            updated_at=now_iso,
        )
    except Exception:
        pass


__all__ = [
    "append_resource_layer",
    "build_resource_layer_payload",
    "upsert_item_layer",
]
