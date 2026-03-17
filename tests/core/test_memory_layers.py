from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from clawlite.core.memory_layers import (
    build_category_summary_text,
    load_category_items_from_path,
    upsert_category_item_rows,
    write_category_items_to_path,
)


def test_load_category_items_from_path_decrypts_each_row(tmp_path: Path) -> None:
    item_path = tmp_path / "context.json"
    item_path.write_text(
        json.dumps(
            {
                "items": [
                    {"id": "r1", "text": "enc:alpha", "source": "session:a"},
                    {"id": "r2", "text": "enc:beta", "source": "session:b"},
                ]
            }
        ),
        encoding="utf-8",
    )

    rows = load_category_items_from_path(
        item_path=item_path,
        category="context",
        decrypt_text_for_category=lambda text, category: f"{category}:{text}",
    )

    assert rows[0]["text"] == "context:enc:alpha"
    assert rows[1]["text"] == "context:enc:beta"


def test_write_category_items_to_path_persists_expected_shape(tmp_path: Path) -> None:
    item_path = tmp_path / "items" / "context.json"
    write_category_items_to_path(
        item_path=item_path,
        category="context",
        rows=[{"id": "r1", "text": "alpha"}],
        utcnow_iso=lambda: "2026-03-17T12:00:00+00:00",
        atomic_write_text_locked=lambda path, content: path.write_text(content, encoding="utf-8"),
    )

    payload = json.loads(item_path.read_text(encoding="utf-8"))
    assert payload["category"] == "context"
    assert payload["updated_at"] == "2026-03-17T12:00:00+00:00"
    assert payload["items"][0]["id"] == "r1"


def test_build_category_summary_text_and_upsert_rows_cover_replace_and_append() -> None:
    category, rows = upsert_category_item_rows(
        record=SimpleNamespace(id="r2", category="context", text="new text"),
        rows=[
            {"id": "r1", "text": "old one", "source": "session:a"},
            {"id": "r2", "text": "old two", "source": "session:b"},
        ],
        serialize_hit=lambda record: {"id": record.id, "text": record.text, "source": "session:c"},
        encrypt_text_for_category=lambda text, category: f"{category}:{text}",
    )
    summary = build_category_summary_text(
        category=category,
        rows=rows,
        updated_at="2026-03-17T12:00:00+00:00",
    )

    assert category == "context"
    assert [row["text"] for row in rows] == ["context:old one", "context:new text"]
    assert "Total items: 2" in summary
    assert "- session:c: 1" in summary or "- session:a: 1" in summary
