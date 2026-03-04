from __future__ import annotations

from pathlib import Path

from clawlite.core.memory_backend import resolve_memory_backend


def test_sqlite_memory_backend_roundtrip(tmp_path: Path) -> None:
    backend = resolve_memory_backend("sqlite")
    backend.initialize(tmp_path)

    backend.upsert_layer_record(
        layer="item",
        record_id="rec-1",
        payload={"text": "hello"},
        category="context",
        created_at="2026-03-01T00:00:00+00:00",
        updated_at="2026-03-01T00:00:00+00:00",
    )
    backend.upsert_layer_record(
        layer="resource",
        record_id="rec-2",
        payload={"text": "raw"},
        category="context",
        created_at="2026-03-01T00:00:01+00:00",
        updated_at="2026-03-01T00:00:01+00:00",
    )

    rows = backend.fetch_layer_records(layer="item", limit=10)
    assert len(rows) == 1
    assert rows[0]["record_id"] == "rec-1"
    assert rows[0]["payload"]["text"] == "hello"

    deleted = backend.delete_layer_records({"rec-1"})
    assert deleted >= 1
    assert backend.fetch_layer_records(layer="item", limit=10) == []


def test_pgvector_backend_remains_graceful_when_unsupported(tmp_path: Path) -> None:
    backend = resolve_memory_backend("pgvector", pgvector_url="")
    assert backend.is_supported() is False

    backend.initialize(tmp_path)
    backend.upsert_layer_record(
        layer="item",
        record_id="rec-1",
        payload={"text": "ignored"},
        category="context",
        created_at="",
        updated_at="",
    )
    assert backend.fetch_layer_records(layer="item", limit=5) == []
    assert backend.delete_layer_records(["rec-1"]) == 0
