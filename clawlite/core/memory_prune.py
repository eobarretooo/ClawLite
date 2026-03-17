from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from clawlite.core.memory_layers import write_category_items_to_path


def prune_jsonl_records_for_ids(
    *,
    path: Path,
    record_ids: set[str],
    locked_file: Callable[..., Any],
    flush_and_fsync: Callable[[Any], None],
) -> int:
    if not record_ids or not path.exists():
        return 0
    deleted = 0
    with locked_file(path, "r+", exclusive=True) as fh:
        lines = fh.read().splitlines()
        kept_lines: list[str] = []
        for line in lines:
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                kept_lines.append(raw)
                continue
            if not isinstance(payload, dict):
                kept_lines.append(raw)
                continue
            row_id = str(payload.get("id", "")).strip()
            if row_id and row_id in record_ids:
                deleted += 1
                continue
            kept_lines.append(raw)

        fh.seek(0)
        fh.truncate()
        if kept_lines:
            fh.write("\n".join(kept_lines) + "\n")
        flush_and_fsync(fh)
    return deleted


def prune_curated_facts_for_ids(
    *,
    curated_path: Path | None,
    record_ids: set[str],
    read_curated_facts_from: Callable[[Path], list[dict[str, object]]],
    write_curated_facts_to: Callable[[Path, list[dict[str, object]]], None],
) -> int:
    if not record_ids or curated_path is None or not curated_path.exists():
        return 0
    facts = read_curated_facts_from(curated_path)
    kept_facts: list[dict[str, object]] = []
    deleted = 0
    for fact in facts:
        row_id = str(fact.get("id", "")).strip()
        if row_id and row_id in record_ids:
            deleted += 1
            continue
        kept_facts.append(fact)
    write_curated_facts_to(curated_path, kept_facts)
    return deleted


def prune_item_and_category_layers(
    *,
    items_path: Path,
    record_ids: set[str],
    utcnow_iso: Callable[[], str],
    atomic_write_text_locked: Callable[[Path, str], None],
    update_category_summary: Callable[[str], None],
) -> int:
    if not record_ids or not items_path.exists():
        return 0
    deleted = 0
    for item_file in items_path.glob("*.json"):
        try:
            payload = json.loads(item_file.read_text(encoding="utf-8") or "{}")
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        category = str(payload.get("category", item_file.stem) or item_file.stem)
        rows = payload.get("items", [])
        if not isinstance(rows, list):
            continue
        kept: list[dict[str, Any]] = []
        removed_here = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("id", "")).strip()
            if row_id and row_id in record_ids:
                removed_here += 1
                continue
            kept.append(row)
        if removed_here <= 0:
            continue
        deleted += removed_here
        write_category_items_to_path(
            item_path=item_file,
            category=category,
            rows=kept,
            utcnow_iso=utcnow_iso,
            atomic_write_text_locked=atomic_write_text_locked,
        )
        update_category_summary(category)
    return deleted


def delete_records_by_ids_in_scope(
    *,
    scope: dict[str, Path],
    record_ids: set[str],
    memory_home: Path,
    prune_history_records: Callable[[Path, set[str]], int],
    prune_curated_facts: Callable[[Path | None, set[str]], int],
    prune_root_item_layers: Callable[[set[str]], int],
    prune_root_resource_layers: Callable[[set[str]], int],
    prune_scope_item_layers: Callable[[dict[str, Path], set[str]], int],
    prune_scope_resource_layers: Callable[[dict[str, Path], set[str]], int],
) -> dict[str, int]:
    history_deleted = prune_history_records(scope["history"], record_ids)
    curated_deleted = prune_curated_facts(scope.get("curated"), record_ids)
    if scope["root"] == memory_home:
        layer_deleted = prune_root_item_layers(record_ids)
        layer_deleted += prune_root_resource_layers(record_ids)
    else:
        layer_deleted = prune_scope_item_layers(scope, record_ids)
        layer_deleted += prune_scope_resource_layers(scope, record_ids)
    return {
        "history_deleted": int(history_deleted),
        "curated_deleted": int(curated_deleted),
        "layer_deleted": int(layer_deleted),
    }


def delete_records_by_ids(
    *,
    record_ids: set[str],
    iter_existing_scopes: Callable[[], list[dict[str, Path]]],
    delete_records_by_ids_in_scope_fn: Callable[[dict[str, Path], set[str]], dict[str, int]],
    prune_embeddings_for_ids: Callable[[set[str]], int],
    backend_delete_layer_records: Callable[[set[str]], int],
    diagnostics: dict[str, Any],
) -> dict[str, int | list[str]]:
    if not record_ids:
        return {
            "deleted_ids": [],
            "history_deleted": 0,
            "curated_deleted": 0,
            "embeddings_deleted": 0,
            "layer_deleted": 0,
            "backend_deleted": 0,
            "deleted_count": 0,
        }

    history_deleted = 0
    curated_deleted = 0
    embeddings_deleted = 0
    backend_deleted = 0
    layer_deleted = 0

    try:
        for scope in iter_existing_scopes():
            deleted = delete_records_by_ids_in_scope_fn(scope, record_ids)
            history_deleted += int(deleted.get("history_deleted", 0) or 0)
            curated_deleted += int(deleted.get("curated_deleted", 0) or 0)
            layer_deleted += int(deleted.get("layer_deleted", 0) or 0)
    except Exception as exc:
        diagnostics["last_error"] = str(exc)

    try:
        embeddings_deleted = prune_embeddings_for_ids(record_ids)
    except Exception as exc:
        diagnostics["last_error"] = str(exc)

    try:
        backend_deleted = int(backend_delete_layer_records(record_ids) or 0)
    except Exception as exc:
        diagnostics["last_error"] = str(exc)

    deleted_ids = sorted(record_ids)
    return {
        "deleted_ids": deleted_ids,
        "history_deleted": history_deleted,
        "curated_deleted": curated_deleted,
        "embeddings_deleted": embeddings_deleted,
        "layer_deleted": layer_deleted,
        "backend_deleted": backend_deleted,
        "deleted_count": len(deleted_ids),
    }


def cleanup_expired_ephemeral_records(
    *,
    privacy_settings: Callable[[], dict[str, Any]],
    iter_existing_scopes: Callable[[], list[dict[str, Path]]],
    read_history_records_from: Callable[[Path], list[Any]],
    read_curated_facts_from: Callable[[Path], list[dict[str, object]]],
    parse_iso_timestamp: Callable[[str], datetime],
    delete_records_by_ids: Callable[[set[str]], dict[str, Any]],
    diagnostics: dict[str, Any],
    append_privacy_audit_event: Callable[..., None],
    now: datetime | None = None,
) -> int:
    privacy = privacy_settings()
    raw_categories = privacy.get("ephemeral_categories", [])
    if not isinstance(raw_categories, list):
        return 0
    categories = {str(item or "").strip().lower() for item in raw_categories if str(item or "").strip()}
    if not categories:
        return 0
    try:
        ttl_days = int(privacy.get("ephemeral_ttl_days", 0) or 0)
    except Exception:
        ttl_days = 0
    if ttl_days <= 0:
        return 0

    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=ttl_days)
    expired_ids: set[str] = set()

    for scope in iter_existing_scopes():
        history_path = scope["history"]
        if history_path.exists():
            for row in read_history_records_from(history_path):
                row_id = str(getattr(row, "id", "") or "").strip()
                if not row_id:
                    continue
                if str(getattr(row, "category", "context") or "context").strip().lower() not in categories:
                    continue
                if parse_iso_timestamp(str(getattr(row, "created_at", "") or "")) < cutoff:
                    expired_ids.add(row_id)

        curated_path = scope.get("curated")
        if curated_path is None or not curated_path.exists():
            continue
        for row in read_curated_facts_from(curated_path):
            row_id = str(row.get("id", "")).strip()
            if not row_id:
                continue
            if str(row.get("category", "context") or "context").strip().lower() not in categories:
                continue
            if parse_iso_timestamp(str(row.get("created_at", "") or "")) < cutoff:
                expired_ids.add(row_id)

    if not expired_ids:
        return 0

    deleted = delete_records_by_ids(expired_ids)
    deleted_count = int(deleted.get("deleted_count", 0) or 0)
    if deleted_count > 0:
        diagnostics["privacy_ttl_deleted"] = int(diagnostics.get("privacy_ttl_deleted", 0) or 0) + deleted_count
        append_privacy_audit_event(
            action="ttl_cleanup",
            reason="ephemeral_ttl_expired",
            metadata={
                "deleted_count": deleted_count,
                "ttl_days": ttl_days,
                "categories": sorted(categories),
            },
        )
    return deleted_count


__all__ = [
    "cleanup_expired_ephemeral_records",
    "delete_records_by_ids",
    "delete_records_by_ids_in_scope",
    "prune_curated_facts_for_ids",
    "prune_item_and_category_layers",
    "prune_jsonl_records_for_ids",
]
