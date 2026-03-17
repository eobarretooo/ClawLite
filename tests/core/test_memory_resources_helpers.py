from __future__ import annotations

from dataclasses import dataclass, field

from clawlite.core.memory_resources import (
    create_resource,
    fetch_record_by_id,
    get_resource,
    get_resource_records,
    purge_expired_records,
)


@dataclass
class _Resource:
    name: str
    kind: str = "project"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    id: str = "res-1"
    created_at: str = "2026-03-17T00:00:00+00:00"
    updated_at: str = "2026-03-17T00:00:00+00:00"


@dataclass
class _Record:
    id: str
    text: str
    source: str
    created_at: str
    category: str = "context"
    user_id: str = "default"
    layer: str = "item"
    reasoning_layer: str = "fact"
    modality: str = "text"
    updated_at: str = ""
    confidence: float = 1.0
    decay_rate: float = 0.0
    emotional_tone: str = "neutral"
    memory_type: str = "knowledge"
    happened_at: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


class _Backend:
    def __init__(self) -> None:
        self.resources: dict[str, dict[str, object]] = {}
        self.layer_rows: list[dict[str, object]] = []
        self.resource_links: dict[str, list[str]] = {}
        self.ttl_deleted: list[str] = []

    def upsert_resource(self, payload: dict[str, object]) -> None:
        self.resources[str(payload["id"])] = payload

    def fetch_resource(self, resource_id: str):
        return self.resources.get(resource_id)

    def fetch_all_resources(self):
        return list(self.resources.values())

    def fetch_layer_records(self, *, layer: str, limit: int = 200, category=None):
        del limit, category
        return [row for row in self.layer_rows if row.get("layer") == layer]

    def fetch_records_by_resource(self, resource_id: str):
        return list(self.resource_links.get(resource_id, []))

    def fetch_expired_record_ids(self):
        return ["r1", "r2"]

    def delete_layer_records(self, record_ids):
        return len(record_ids)

    def delete_ttl_entries(self, record_ids):
        self.ttl_deleted.extend(record_ids)


def test_resource_helpers_round_trip_and_lookup_records() -> None:
    backend = _Backend()
    rid = create_resource(backend=backend, resource=_Resource(name="Project X"))
    resource = get_resource(backend=backend, resource_id=rid, resource_context_cls=_Resource)
    assert resource is not None
    assert resource.name == "Project X"

    backend.layer_rows.append(
        {
            "layer": "item",
            "record_id": "r1",
            "created_at": "2026-03-17T00:00:00+00:00",
            "category": "context",
            "payload": {"id": "r1", "text": "hello", "source": "session:a"},
        }
    )
    backend.resource_links[rid] = ["r1"]

    record = fetch_record_by_id(backend=backend, record_id="r1", item_layer_value="item", memory_record_cls=_Record)
    assert record is not None
    assert record.text == "hello"
    records = get_resource_records(backend=backend, resource_id=rid, fetch_record_by_id_fn=lambda record_id: fetch_record_by_id(backend=backend, record_id=record_id, item_layer_value="item", memory_record_cls=_Record))
    assert [row.id for row in records] == ["r1"]


def test_purge_expired_records_deletes_layers_and_ttl_entries() -> None:
    backend = _Backend()
    deleted = purge_expired_records(backend=backend)
    assert deleted == 2
    assert backend.ttl_deleted == ["r1", "r2"]
