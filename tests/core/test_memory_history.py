from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from clawlite.core.memory_history import (
    append_or_reinforce_history_record,
    read_history_records,
    stored_history_payload,
    upsert_history_record_by_id,
)


@dataclass
class _Record:
    id: str
    text: str
    source: str
    created_at: str
    category: str = "context"
    metadata: dict[str, object] = field(default_factory=dict)


@contextlib.contextmanager
def _locked_file(path: Path, mode: str, exclusive: bool = False):
    del exclusive
    with path.open(mode, encoding="utf-8") as fh:
        yield fh


def _flush_and_fsync(fh) -> None:
    fh.flush()


def test_read_history_records_repairs_corrupt_lines(tmp_path: Path) -> None:
    history_path = tmp_path / "memory.jsonl"
    history_path.write_text(
        "\n".join(
            [
                json.dumps({"id": "r1", "text": "alpha", "source": "session:a", "created_at": "2026-03-17T00:00:00+00:00"}),
                "{broken",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    diagnostics = {"history_read_corrupt_lines": 0, "history_repaired_files": 0, "last_error": ""}

    rows = read_history_records(
        history_path=history_path,
        locked_file=_locked_file,
        record_from_payload=lambda payload: _Record(**payload),
        decrypt_text_for_category=lambda text, category: text,
        repair_history_file_fn=lambda valid_lines: history_path.write_text(("\n".join(valid_lines) + "\n") if valid_lines else "", encoding="utf-8"),
        diagnostics=diagnostics,
    )

    assert [row.id for row in rows] == ["r1"]
    assert diagnostics["history_read_corrupt_lines"] == 1
    repaired_lines = [line for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert repaired_lines == [json.dumps({"id": "r1", "text": "alpha", "source": "session:a", "created_at": "2026-03-17T00:00:00+00:00"})]


def test_append_or_reinforce_and_upsert_history_record_by_id(tmp_path: Path) -> None:
    history_path = tmp_path / "memory.jsonl"
    original = _Record(id="r1", text="alpha", source="session:a", created_at="2026-03-17T00:00:00+00:00")
    history_path.write_text(json.dumps(stored_history_payload(record=original, encrypt_text_for_category=lambda text, category: text)) + "\n", encoding="utf-8")

    incoming = _Record(id="r2", text="alpha expanded", source="session:a", created_at="2026-03-17T01:00:00+00:00")
    reinforced, created = append_or_reinforce_history_record(
        history_path=history_path,
        record=incoming,
        content_hash="same-hash",
        scope_key="session:a",
        source="session:a",
        reinforced_at="2026-03-17T01:00:00+00:00",
        ensure_file=lambda path: path.touch(exist_ok=True),
        locked_file=_locked_file,
        flush_and_fsync=_flush_and_fsync,
        record_from_payload=lambda payload: _Record(**payload),
        decrypt_text_for_category=lambda text, category: text,
        record_content_hash=lambda record: "same-hash",
        record_scope_key=lambda record: record.source,
        reinforce_record=lambda existing, incoming, source, scope_key, reinforced_at: _Record(
            id=existing.id,
            text=incoming.text,
            source=source,
            created_at=existing.created_at,
            metadata={"reinforced_at": reinforced_at, "scope_key": scope_key},
        ),
        stored_history_payload_fn=lambda record: stored_history_payload(record=record, encrypt_text_for_category=lambda text, category: text),
    )

    assert created is False
    assert reinforced.id == "r1"
    assert reinforced.text == "alpha expanded"

    updated = _Record(id="r1", text="final", source="session:a", created_at="2026-03-17T00:00:00+00:00")
    assert upsert_history_record_by_id(
        history_path=history_path,
        record=updated,
        append_if_missing=False,
        ensure_file=lambda path: path.touch(exist_ok=True),
        locked_file=_locked_file,
        flush_and_fsync=_flush_and_fsync,
        stored_history_payload_fn=lambda record: stored_history_payload(record=record, encrypt_text_for_category=lambda text, category: text),
    )

    lines = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [row["id"] for row in lines] == ["r1"]
    assert lines[0]["text"] == "final"
