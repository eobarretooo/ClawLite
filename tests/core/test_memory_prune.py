from __future__ import annotations

import contextlib
import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

from clawlite.core.memory_prune import (
    cleanup_expired_ephemeral_records,
    prune_item_and_category_layers,
    prune_jsonl_records_for_ids,
)


@contextlib.contextmanager
def _locked_file(path: Path, mode: str, exclusive: bool = False):
    del exclusive
    with path.open(mode, encoding="utf-8") as fh:
        yield fh


def _flush_and_fsync(fh) -> None:
    fh.flush()


def test_prune_jsonl_records_for_ids_keeps_invalid_lines_and_deletes_matches(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"id": "keep-1", "text": "keep"}),
                "{invalid",
                json.dumps({"id": "drop-1", "text": "drop"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    deleted = prune_jsonl_records_for_ids(
        path=path,
        record_ids={"drop-1"},
        locked_file=_locked_file,
        flush_and_fsync=_flush_and_fsync,
    )

    assert deleted == 1
    lines = path.read_text(encoding="utf-8").splitlines()
    assert "{invalid" in lines
    assert any('"keep-1"' in line for line in lines)
    assert all('"drop-1"' not in line for line in lines)


def test_prune_item_and_category_layers_rewrites_item_payload_and_summary(tmp_path: Path) -> None:
    items_path = tmp_path / "items"
    summaries: list[str] = []
    item_path = items_path / "context.json"
    item_path.parent.mkdir(parents=True, exist_ok=True)
    item_path.write_text(
        json.dumps(
            {
                "version": 1,
                "category": "context",
                "updated_at": "2026-03-17T12:00:00+00:00",
                "items": [
                    {"id": "keep-1", "text": "keep"},
                    {"id": "drop-1", "text": "drop"},
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    deleted = prune_item_and_category_layers(
        items_path=items_path,
        record_ids={"drop-1"},
        utcnow_iso=lambda: "2026-03-17T12:30:00+00:00",
        atomic_write_text_locked=lambda path, text: path.write_text(text, encoding="utf-8"),
        update_category_summary=summaries.append,
    )

    assert deleted == 1
    payload = json.loads(item_path.read_text(encoding="utf-8"))
    assert payload["updated_at"] == "2026-03-17T12:30:00+00:00"
    assert [row["id"] for row in payload["items"]] == ["keep-1"]
    assert summaries == ["context"]


def test_cleanup_expired_ephemeral_records_collects_scope_rows_and_updates_audit(tmp_path: Path) -> None:
    deleted_ids: list[str] = []
    audit_events: list[dict[str, object]] = []
    diagnostics = {"privacy_ttl_deleted": 0}
    base = tmp_path / "scope"
    base.mkdir()
    history_path = base / "history.jsonl"
    curated_path = base / "curated.json"
    history_path.write_text("", encoding="utf-8")
    curated_path.write_text("", encoding="utf-8")
    shared_scope = {
        "history": history_path,
        "curated": curated_path,
    }

    deleted = cleanup_expired_ephemeral_records(
        privacy_settings=lambda: {
            "ephemeral_categories": ["context"],
            "ephemeral_ttl_days": 2,
        },
        iter_existing_scopes=lambda: [shared_scope],
        read_history_records_from=lambda path: [
            SimpleNamespace(id="expired-history", category="context", created_at="2026-03-10T00:00:00+00:00"),
            SimpleNamespace(id="fresh-history", category="context", created_at="2026-03-17T11:00:00+00:00"),
        ]
        if path == shared_scope["history"]
        else [],
        read_curated_facts_from=lambda path: [
            {"id": "expired-curated", "category": "context", "created_at": "2026-03-10T00:00:00+00:00"},
            {"id": "fresh-curated", "category": "context", "created_at": "2026-03-17T11:00:00+00:00"},
        ]
        if path == shared_scope["curated"]
        else [],
        parse_iso_timestamp=lambda value: dt.datetime.fromisoformat(value),
        delete_records_by_ids=lambda record_ids: deleted_ids.extend(sorted(record_ids)) or {"deleted_count": len(record_ids)},
        diagnostics=diagnostics,
        append_privacy_audit_event=lambda **payload: audit_events.append(payload),
        now=dt.datetime.fromisoformat("2026-03-17T12:00:00+00:00"),
    )

    assert deleted == 2
    assert deleted_ids == ["expired-curated", "expired-history"]
    assert diagnostics["privacy_ttl_deleted"] == 2
    assert audit_events == [
        {
            "action": "ttl_cleanup",
            "reason": "ephemeral_ttl_expired",
            "metadata": {
                "deleted_count": 2,
                "ttl_days": 2,
                "categories": ["context"],
            },
        }
    ]
