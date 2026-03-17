from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from pathlib import Path

from clawlite.core.memory_artifacts import append_resource_layer, upsert_item_layer


@dataclass
class _Record:
    id: str
    text: str
    source: str
    created_at: str
    category: str = "context"
    reasoning_layer: str = "fact"
    confidence: float = 1.0
    updated_at: str = ""


@contextlib.contextmanager
def _locked_file(path: Path, mode: str, exclusive: bool = False):
    del exclusive
    with path.open(mode, encoding="utf-8") as fh:
        yield fh


def _flush_and_fsync(fh) -> None:
    fh.flush()


def test_append_resource_layer_writes_jsonl_and_backend_payload(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []
    record = _Record(id="r1", text="hello", source="session:a", created_at="2026-03-17T00:00:00+00:00")
    target = tmp_path / "conv_2026_03_17.jsonl"

    append_resource_layer(
        record=record,
        raw_text="resource text",
        resource_layer_value="resource",
        encrypt_text_for_category=lambda text, category: f"enc:{category}:{text}",
        normalize_reasoning_layer=lambda value: value or "fact",
        normalize_confidence=lambda value: float(value or 0.0),
        resource_file_for_timestamp=lambda stamp: target,
        ensure_file=lambda path: path.touch(exist_ok=True),
        locked_file=_locked_file,
        flush_and_fsync=_flush_and_fsync,
        backend_upsert_layer_record=lambda **kwargs: calls.append(kwargs),
    )

    rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[0]["text"] == "enc:context:resource text"
    assert rows[0]["layer"] == "resource"
    assert calls[0]["layer"] == "resource"
    assert calls[0]["payload"]["id"] == "r1"


def test_upsert_item_layer_writes_items_and_backend_rows(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []
    summary_updates: list[str] = []
    persisted: dict[str, list[dict[str, object]]] = {}
    record = _Record(id="r1", text="hello", source="session:a", created_at="2026-03-17T00:00:00+00:00")

    upsert_item_layer(
        record=record,
        load_category_items=lambda category: [],
        serialize_hit=lambda row: {"id": row.id, "text": row.text, "source": row.source, "category": row.category},
        encrypt_text_for_category=lambda text, category: f"enc:{category}:{text}",
        write_category_items=lambda category, rows: persisted.setdefault(category, rows),
        update_category_summary=summary_updates.append,
        category_file_path=lambda category: tmp_path / f"{category}.md",
        utcnow_iso=lambda: "2026-03-17T00:30:00+00:00",
        backend_upsert_layer_record=lambda **kwargs: calls.append(kwargs),
        item_layer_value="item",
        category_layer_value="category",
    )

    assert persisted["context"][0]["text"] == "enc:context:hello"
    assert summary_updates == ["context"]
    assert [call["layer"] for call in calls] == ["item", "category"]
    assert calls[1]["payload"]["total_items"] == 1
