from __future__ import annotations

import asyncio
import json

import pytest

from clawlite.core.memory import MemoryStore
from clawlite.tools.base import ToolContext
from clawlite.tools.memory import MemoryAnalyzeTool, MemoryForgetTool, MemoryLearnTool, MemoryRecallTool


def test_memory_learn_success(tmp_path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(db_path=tmp_path / "memory.jsonl")
        tool = MemoryLearnTool(store)

        payload = json.loads(await tool.run({"text": "  Keep this note.  "}, ToolContext(session_id="telegram:42")))
        assert payload["status"] == "ok"
        assert payload["ref"].startswith("mem:")
        assert payload["source"] == "memory_learn:telegram:42"
        assert payload["chars"] == len("Keep this note.")

        rows = store.all()
        assert len(rows) == 1
        assert rows[0].id == payload["id"]

    asyncio.run(_scenario())


def test_memory_learn_empty_error(tmp_path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(db_path=tmp_path / "memory.jsonl")
        tool = MemoryLearnTool(store)
        with pytest.raises(ValueError, match="text is required"):
            await tool.run({"text": "   "}, ToolContext(session_id="s1"))

    asyncio.run(_scenario())


def test_memory_recall_with_metadata_default(tmp_path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(db_path=tmp_path / "memory.jsonl")
        row = store.add("Python async checklist", source="seed:test")
        tool = MemoryRecallTool(store)

        payload = json.loads(await tool.run({"query": "python"}, ToolContext(session_id="s1")))
        assert payload["status"] == "ok"
        assert payload["query"] == "python"
        assert payload["count"] >= 1
        first = payload["results"][0]
        assert first["ref"] == f"mem:{row.id[:8]}"
        assert first["text"] == "Python async checklist"
        assert first["id"] == row.id
        assert first["source"] == "seed:test"
        assert first["created_at"]

    asyncio.run(_scenario())


def test_memory_recall_without_metadata(tmp_path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(db_path=tmp_path / "memory.jsonl")
        store.add("Searchable memory payload", source="seed:test")
        tool = MemoryRecallTool(store)

        payload = json.loads(
            await tool.run({"query": "searchable", "include_metadata": False}, ToolContext(session_id="s1"))
        )
        assert payload["count"] >= 1
        first = payload["results"][0]
        assert "id" not in first
        assert "source" not in first
        assert "created_at" not in first

    asyncio.run(_scenario())


def test_memory_recall_limit_clamp(tmp_path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(db_path=tmp_path / "memory.jsonl")
        for idx in range(30):
            store.add(f"alpha item {idx}", source=f"seed:{idx}")
        tool = MemoryRecallTool(store)

        upper = json.loads(await tool.run({"query": "alpha", "limit": 999}, ToolContext(session_id="s1")))
        assert upper["count"] == 20

        lower = json.loads(await tool.run({"query": "alpha", "limit": 0}, ToolContext(session_id="s1")))
        assert lower["count"] == 1

    asyncio.run(_scenario())


def test_memory_forget_requires_selector(tmp_path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(db_path=tmp_path / "memory.jsonl")
        tool = MemoryForgetTool(store)
        with pytest.raises(ValueError, match="selector is required"):
            await tool.run({}, ToolContext(session_id="s1"))

    asyncio.run(_scenario())


def test_memory_forget_dry_run_returns_candidates_without_deletion(tmp_path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(db_path=tmp_path / "memory.jsonl")
        row = store.add("remember alpha preference", source="seed:1")
        tool = MemoryForgetTool(store)

        payload = json.loads(
            await tool.run({"ref": f"mem:{row.id[:8]}", "dry_run": True}, ToolContext(session_id="s1"))
        )
        assert payload["status"] == "ok"
        assert payload["deleted_count"] == 0
        assert payload["history_deleted"] == 0
        assert payload["curated_deleted"] == 0
        assert payload["refs"] == [f"mem:{row.id[:8]}"]
        assert len(store.all()) == 1

    asyncio.run(_scenario())


def test_memory_forget_by_ref_deletes_from_history(tmp_path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(db_path=tmp_path / "memory.jsonl")
        keep = store.add("keep me", source="seed:keep")
        drop = store.add("delete me", source="seed:drop")
        tool = MemoryForgetTool(store)

        payload = json.loads(await tool.run({"ref": f"mem:{drop.id[:8]}"}, ToolContext(session_id="s1")))
        assert payload["status"] == "ok"
        assert payload["deleted_count"] == 1
        assert payload["history_deleted"] == 1
        remaining_ids = {row.id for row in store.all()}
        assert drop.id not in remaining_ids
        assert keep.id in remaining_ids

    asyncio.run(_scenario())


def test_memory_forget_by_query_enforces_min_length(tmp_path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(db_path=tmp_path / "memory.jsonl")
        tool = MemoryForgetTool(store)
        with pytest.raises(ValueError, match="query must be at least 3 characters"):
            await tool.run({"query": "ab"}, ToolContext(session_id="s1"))

    asyncio.run(_scenario())


def test_memory_analyze_base_stats_fields(tmp_path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(db_path=tmp_path / "memory.jsonl")
        store.add("today deadline for project alpha", source="seed:temporal")
        store.add("plain reference note", source="seed:plain")
        tool = MemoryAnalyzeTool(store)

        payload = json.loads(await tool.run({}, ToolContext(session_id="s1")))
        assert payload["status"] == "ok"
        assert payload["counts"]["history"] == 2
        assert payload["counts"]["total"] >= payload["counts"]["history"]
        assert set(payload["recent"].keys()) == {"last_24h", "last_7d", "last_30d"}
        assert "temporal_marked_count" in payload
        assert isinstance(payload["top_sources"], list)

    asyncio.run(_scenario())


def test_memory_analyze_query_returns_matches_with_refs(tmp_path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(db_path=tmp_path / "memory.jsonl")
        row = store.add("python memory match example", source="seed:test")
        tool = MemoryAnalyzeTool(store)

        payload = json.loads(await tool.run({"query": "python", "limit": 3}, ToolContext(session_id="s1")))
        assert payload["status"] == "ok"
        assert payload["query"] == "python"
        assert payload["matches"]
        assert payload["matches"][0]["ref"] == f"mem:{row.id[:8]}"

    asyncio.run(_scenario())
