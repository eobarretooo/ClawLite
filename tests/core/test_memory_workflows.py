from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from clawlite.core.memory_workflows import consolidate, ingest_file, memorize


@dataclass
class _WorkflowRecord:
    id: str
    text: str
    source: str


def test_ingest_file_reads_text_and_passes_resource_id(tmp_path: Path) -> None:
    note = tmp_path / "note.md"
    note.write_text("alpha launch notes", encoding="utf-8")
    calls: list[tuple[str, dict[str, object]]] = []

    result = ingest_file(
        path=str(note),
        source="session:file",
        resource_id="res-1",
        add_record=lambda text, **kwargs: calls.append((text, kwargs)) or SimpleNamespace(id="rec-1"),
    )

    assert result == {"ok": True, "modality": "text", "record_id": "rec-1", "reason": ""}
    assert calls == [("alpha launch notes", {"source": "session:file", "modality": "text", "resource_id": "res-1"})]


def test_consolidate_workflow_routes_scoped_users_to_scope_helper(tmp_path: Path) -> None:
    result = consolidate(
        messages=[{"role": "user", "content": "remember alpha"}],
        source="session:a",
        user_id="user-a",
        shared=False,
        metadata={"x": 1},
        reasoning_layer="fact",
        confidence=0.9,
        memory_type="knowledge",
        happened_at="",
        decay_rate=0.0,
        normalize_user_id=lambda value: str(value).strip().lower(),
        scope_paths=lambda **kwargs: {"checkpoints": tmp_path / "cp.json", "curated": tmp_path / "curated.json"},
        consolidate_in_scope_fn=lambda **kwargs: kwargs["scope"]["checkpoints"].name,
        consolidate_messages=lambda *args, **kwargs: None,
        checkpoints_path=tmp_path / "root-checkpoints.json",
        read_curated_facts=lambda: [],
        write_curated_facts=lambda facts: None,
        add_record=lambda *args, **kwargs: None,
        max_checkpoint_sources=10,
        max_checkpoint_signatures=20,
    )

    assert result == "cp.json"


def test_memorize_workflow_supports_message_and_add_paths() -> None:
    async def _scenario() -> None:
        consolidated = await memorize(
            text=None,
            messages=[{"role": "user", "content": "remember timezone UTC-3"}],
            source="session:a",
            user_id="default",
            shared=False,
            include_shared=False,
            file_path=None,
            url=None,
            modality="text",
            metadata=None,
            reasoning_layer=None,
            confidence=None,
            memory_type=None,
            happened_at=None,
            decay_rate=None,
            cleanup_expired_ephemeral_records=lambda: 0,
            diagnostics={},
            privacy_block_reason=lambda text: None,
            append_privacy_audit_event=lambda **kwargs: None,
            consolidate_fn=lambda messages, **kwargs: _WorkflowRecord(id="rec-msg", text="joined", source="session:a"),
            add_fn=lambda text, **kwargs: _WorkflowRecord(id="rec-add", text=text, source="session:b"),
            memory_text_from_file=lambda *args, **kwargs: "",
            memory_text_from_url=lambda *args, **kwargs: "",
        )
        assert consolidated["status"] == "ok"
        assert consolidated["mode"] == "consolidate"
        assert consolidated["record"]["id"] == "rec-msg"

        added = await memorize(
            text=None,
            messages=None,
            source="session:b",
            user_id="default",
            shared=False,
            include_shared=False,
            file_path=str(Path("notes.txt")),
            url=None,
            modality="text",
            metadata=None,
            reasoning_layer=None,
            confidence=None,
            memory_type=None,
            happened_at=None,
            decay_rate=None,
            cleanup_expired_ephemeral_records=lambda: 0,
            diagnostics={},
            privacy_block_reason=lambda text: None,
            append_privacy_audit_event=lambda **kwargs: None,
            consolidate_fn=lambda messages, **kwargs: None,
            add_fn=lambda text, **kwargs: _WorkflowRecord(id="rec-add", text=text, source="session:b"),
            memory_text_from_file=lambda *args, **kwargs: "loaded from file",
            memory_text_from_url=lambda *args, **kwargs: "",
        )
        assert added["status"] == "ok"
        assert added["mode"] == "add"
        assert added["record"]["id"] == "rec-add"

    asyncio.run(_scenario())
