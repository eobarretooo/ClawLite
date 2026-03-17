from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable


def load_category_items_from_path(
    *,
    item_path: Path,
    category: str,
    decrypt_text_for_category: Callable[[str, str], str],
) -> list[dict[str, Any]]:
    if not item_path.exists():
        return []
    try:
        payload = json.loads(item_path.read_text(encoding="utf-8") or "{}")
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    rows = payload.get("items", [])
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict) and str(row.get("id", "")).strip():
            decoded = dict(row)
            decoded["text"] = decrypt_text_for_category(str(decoded.get("text", "") or ""), category)
            out.append(decoded)
    return out


def build_category_items_payload(
    *,
    category: str,
    rows: list[dict[str, Any]],
    updated_at: str,
) -> dict[str, Any]:
    return {
        "version": 1,
        "category": str(category or "context"),
        "updated_at": str(updated_at or ""),
        "items": rows,
    }


def write_category_items_to_path(
    *,
    item_path: Path,
    category: str,
    rows: list[dict[str, Any]],
    utcnow_iso: Callable[[], str],
    atomic_write_text_locked: Callable[[Path, str], None],
) -> None:
    item_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_category_items_payload(
        category=category,
        rows=rows,
        updated_at=utcnow_iso(),
    )
    atomic_write_text_locked(item_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def build_category_summary_text(
    *,
    category: str,
    rows: list[dict[str, Any]],
    updated_at: str,
) -> str:
    sources: Counter[str] = Counter()
    for row in rows:
        sources[str(row.get("source", "unknown") or "unknown")] += 1
    top_sources = [
        f"- {source}: {count}"
        for source, count in sorted(sources.items(), key=lambda item: (-item[1], item[0]))[:5]
    ]
    recent_lines = [
        f"- {str(row.get('id', '') or '')}: {str(row.get('text', '') or '').strip()[:160]}"
        for row in rows[-5:]
    ]
    return "\n".join(
        [
            f"# Category: {category}",
            "",
            f"Updated: {updated_at}",
            f"Total items: {len(rows)}",
            "",
            "## Top Sources",
            *(top_sources or ["- none"]),
            "",
            "## Recent Items",
            *(recent_lines or ["- none"]),
            "",
        ]
    )


def write_category_summary_to_path(
    *,
    category_path: Path,
    category: str,
    rows: list[dict[str, Any]],
    utcnow_iso: Callable[[], str],
    atomic_write_text_locked: Callable[[Path, str], None],
) -> None:
    category_path.parent.mkdir(parents=True, exist_ok=True)
    body = build_category_summary_text(
        category=category,
        rows=rows,
        updated_at=utcnow_iso(),
    )
    atomic_write_text_locked(category_path, body)


def upsert_category_item_rows(
    *,
    record: Any,
    rows: list[dict[str, Any]],
    serialize_hit: Callable[[Any], dict[str, Any]],
    encrypt_text_for_category: Callable[[str, str], str],
) -> tuple[str, list[dict[str, Any]]]:
    category = str(getattr(record, "category", "context") or "context")
    row_payload = serialize_hit(record)
    stored_payload = dict(row_payload)
    stored_payload["text"] = encrypt_text_for_category(str(row_payload.get("text", "") or ""), category)
    updated_rows: list[dict[str, Any]] = []
    found = False
    record_id = str(getattr(record, "id", "") or "")
    for row in rows:
        if str(row.get("id", "")).strip() == record_id:
            updated_rows.append(stored_payload)
            found = True
        else:
            preserved = dict(row)
            preserved["text"] = encrypt_text_for_category(str(preserved.get("text", "") or ""), category)
            updated_rows.append(preserved)
    if not found:
        updated_rows.append(stored_payload)
    return category, updated_rows


__all__ = [
    "build_category_items_payload",
    "build_category_summary_text",
    "load_category_items_from_path",
    "upsert_category_item_rows",
    "write_category_items_to_path",
    "write_category_summary_to_path",
]
