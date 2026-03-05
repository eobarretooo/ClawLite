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


def test_memory_learn_persists_reasoning_layer_and_confidence(tmp_path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(db_path=tmp_path / "memory.jsonl")
        tool = MemoryLearnTool(store)

        payload = json.loads(
            await tool.run(
                {"text": "Persistent decision memory", "reasoning_layer": "decision", "confidence": 0.82},
                ToolContext(session_id="telegram:42"),
            )
        )
        assert payload["status"] == "ok"
        assert payload["reasoning_layer"] == "decision"
        assert payload["confidence"] == 0.82

        rows = store.all()
        assert len(rows) == 1
        assert rows[0].reasoning_layer == "decision"
        assert rows[0].confidence == 0.82

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
        assert isinstance(payload["categories"], dict)
        assert payload["categories"]["context"] >= 2

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


def test_memory_analyze_includes_semantic_coverage_metadata(tmp_path, monkeypatch) -> None:
    async def _scenario() -> None:
        def _fake_embedding(self: MemoryStore, text: str) -> list[float] | None:
            return [0.3, 0.7] if text else None

        monkeypatch.setattr(MemoryStore, "_generate_embedding", _fake_embedding)

        store = MemoryStore(db_path=tmp_path / "memory.jsonl", semantic_enabled=True)
        store.add("semantic coverage row", source="seed:test")
        tool = MemoryAnalyzeTool(store)

        payload = json.loads(await tool.run({}, ToolContext(session_id="s1")))
        assert payload["status"] == "ok"
        assert "semantic" in payload
        assert payload["semantic"]["enabled"] is True
        assert payload["semantic"]["total_records"] >= 1
        assert payload["semantic"]["embedded_records"] >= 1
        assert payload["semantic"]["missing_records"] == 0
        assert payload["semantic"]["coverage_ratio"] == 1.0
        assert payload["semantic"]["coverage_percent"] == 100.0

    asyncio.run(_scenario())


def test_memory_recall_prefers_async_retrieve_and_preserves_response_shape() -> None:
    class _AsyncMemory:
        def __init__(self) -> None:
            self.retrieve_calls: list[tuple[str, int, str]] = []

        async def retrieve(self, query: str, *, limit: int = 5, method: str = "rag") -> dict[str, object]:
            self.retrieve_calls.append((query, limit, method))
            return {
                "status": "ok",
                "hits": [
                    {
                        "id": "abc12345def",
                        "text": "async hit",
                        "source": "seed",
                        "created_at": "2026-03-04T00:00:00+00:00",
                    }
                ],
            }

        def search(self, query: str, *, limit: int = 5):
            raise AssertionError(f"search fallback should not run for query={query} limit={limit}")

    async def _scenario() -> None:
        memory = _AsyncMemory()
        tool = MemoryRecallTool(memory)  # type: ignore[arg-type]
        payload = json.loads(await tool.run({"query": "async", "limit": 4}, ToolContext(session_id="s1")))
        assert payload["status"] == "ok"
        assert payload["query"] == "async"
        assert payload["count"] == 1
        assert payload["results"][0]["ref"] == "mem:abc12345"
        assert payload["results"][0]["text"] == "async hit"
        assert payload["results"][0]["id"] == "abc12345def"
        assert memory.retrieve_calls == [("async", 4, "rag")]

    asyncio.run(_scenario())


def test_memory_learn_prefers_async_memorize_and_preserves_response_shape() -> None:
    class _AsyncMemory:
        def __init__(self) -> None:
            self.memorize_calls: list[tuple[str, str]] = []

        async def memorize(self, *, text: str | None = None, source: str = "session", messages=None) -> dict[str, object]:
            del messages
            self.memorize_calls.append((str(text), source))
            return {
                "status": "ok",
                "record": {
                    "id": "learn12345678",
                    "text": str(text),
                    "source": source,
                    "created_at": "2026-03-04T00:00:00+00:00",
                    "category": "context",
                },
            }

        def add(self, text: str, *, source: str = "user"):
            raise AssertionError(f"add fallback should not run for text={text} source={source}")

    async def _scenario() -> None:
        memory = _AsyncMemory()
        tool = MemoryLearnTool(memory)  # type: ignore[arg-type]
        payload = json.loads(await tool.run({"text": "saved async"}, ToolContext(session_id="cli:99")))
        assert payload["status"] == "ok"
        assert payload["ref"] == "mem:learn123"
        assert payload["id"] == "learn12345678"
        assert payload["source"] == "memory_learn:cli:99"
        assert payload["created_at"] == "2026-03-04T00:00:00+00:00"
        assert payload["chars"] == len("saved async")
        assert memory.memorize_calls == [("saved async", "memory_learn:cli:99")]

    asyncio.run(_scenario())


def test_memory_learn_does_not_bypass_privacy_skip_with_add_fallback() -> None:
    class _AsyncMemory:
        async def memorize(self, *, text: str | None = None, source: str = "session", messages=None) -> dict[str, object]:
            del text, source, messages
            return {"status": "skipped", "record": None}

        def add(self, text: str, *, source: str = "user"):
            raise AssertionError(f"privacy skip must not call add fallback text={text} source={source}")

    async def _scenario() -> None:
        memory = _AsyncMemory()
        tool = MemoryLearnTool(memory)  # type: ignore[arg-type]
        payload = json.loads(await tool.run({"text": "secret payload"}, ToolContext(session_id="cli:privacy")))
        assert payload["status"] == "skipped"
        assert payload["id"] == ""
        assert payload["ref"] == ""

    asyncio.run(_scenario())


def test_memory_recall_passes_user_context_when_retrieve_supports_kwargs() -> None:
    class _AsyncMemory:
        def __init__(self) -> None:
            self.retrieve_calls: list[dict[str, object]] = []

        async def retrieve(
            self,
            query: str,
            *,
            limit: int = 5,
            method: str = "rag",
            user_id: str = "",
            include_shared: bool = False,
        ) -> dict[str, object]:
            self.retrieve_calls.append(
                {
                    "query": query,
                    "limit": limit,
                    "method": method,
                    "user_id": user_id,
                    "include_shared": include_shared,
                }
            )
            return {"status": "ok", "hits": []}

        def search(self, query: str, *, limit: int = 5):
            del query, limit
            return []

    async def _scenario() -> None:
        memory = _AsyncMemory()
        tool = MemoryRecallTool(memory)  # type: ignore[arg-type]
        payload = json.loads(await tool.run({"query": "timezone"}, ToolContext(session_id="telegram:42", user_id="42")))
        assert payload["status"] == "ok"
        assert memory.retrieve_calls == [
            {
                "query": "timezone",
                "limit": 6,
                "method": "rag",
                "user_id": "42",
                "include_shared": True,
            }
        ]

    asyncio.run(_scenario())


def test_memory_recall_forwards_reasoning_filters_and_returns_metadata() -> None:
    class _AsyncMemory:
        def __init__(self) -> None:
            self.retrieve_calls: list[dict[str, object]] = []

        async def retrieve(
            self,
            query: str,
            *,
            limit: int = 5,
            method: str = "rag",
            user_id: str = "",
            include_shared: bool = False,
            reasoning_layers=None,
            min_confidence: float | None = None,
        ) -> dict[str, object]:
            self.retrieve_calls.append(
                {
                    "query": query,
                    "limit": limit,
                    "method": method,
                    "user_id": user_id,
                    "include_shared": include_shared,
                    "reasoning_layers": list(reasoning_layers or []),
                    "min_confidence": min_confidence,
                }
            )
            return {
                "status": "ok",
                "hits": [
                    {
                        "id": "rr99887766",
                        "text": "reasoning-aware hit",
                        "source": "seed",
                        "created_at": "2026-03-04T00:00:00+00:00",
                        "reasoning_layer": "hypothesis",
                        "confidence": 0.66,
                    }
                ],
            }

        def search(self, query: str, *, limit: int = 5):
            raise AssertionError(f"search fallback should not run for query={query} limit={limit}")

    async def _scenario() -> None:
        memory = _AsyncMemory()
        tool = MemoryRecallTool(memory)  # type: ignore[arg-type]
        payload = json.loads(
            await tool.run(
                {
                    "query": "status",
                    "reasoning_layers": ["hypothesis", "decision"],
                    "min_confidence": 0.6,
                    "include_metadata": True,
                },
                ToolContext(session_id="s1", user_id="u-1"),
            )
        )
        assert payload["status"] == "ok"
        assert payload["count"] == 1
        assert payload["results"][0]["reasoning_layer"] == "hypothesis"
        assert payload["results"][0]["confidence"] == 0.66
        assert memory.retrieve_calls == [
            {
                "query": "status",
                "limit": 6,
                "method": "rag",
                "user_id": "u-1",
                "include_shared": True,
                "reasoning_layers": ["hypothesis", "decision"],
                "min_confidence": 0.6,
            }
        ]

    asyncio.run(_scenario())


def test_memory_learn_passes_user_context_when_memorize_supports_kwargs() -> None:
    class _AsyncMemory:
        def __init__(self) -> None:
            self.memorize_calls: list[dict[str, object]] = []

        async def memorize(
            self,
            *,
            text: str | None = None,
            source: str = "session",
            messages=None,
            user_id: str = "",
            shared: bool = True,
        ) -> dict[str, object]:
            del messages
            self.memorize_calls.append(
                {
                    "text": text,
                    "source": source,
                    "user_id": user_id,
                    "shared": shared,
                }
            )
            return {
                "status": "ok",
                "record": {
                    "id": "ctx99887766",
                    "text": str(text),
                    "source": source,
                    "created_at": "2026-03-04T00:00:00+00:00",
                    "category": "context",
                },
            }

    async def _scenario() -> None:
        memory = _AsyncMemory()
        tool = MemoryLearnTool(memory)  # type: ignore[arg-type]
        payload = json.loads(await tool.run({"text": "save this"}, ToolContext(session_id="cli:7", user_id="u-7")))
        assert payload["status"] == "ok"
        assert memory.memorize_calls == [
            {
                "text": "save this",
                "source": "memory_learn:cli:7",
                "user_id": "u-7",
                "shared": False,
            }
        ]

    asyncio.run(_scenario())


def test_memory_analyze_includes_reasoning_layers_and_confidence_blocks(tmp_path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(db_path=tmp_path / "memory.jsonl")
        store.add("fact row", source="seed:fact", reasoning_layer="fact", confidence=0.95)
        store.add("hypothesis row", source="seed:hyp", reasoning_layer="hypothesis", confidence=0.45)
        tool = MemoryAnalyzeTool(store)

        payload = json.loads(await tool.run({}, ToolContext(session_id="s1")))
        assert payload["status"] == "ok"
        assert "reasoning_layers" in payload
        assert payload["reasoning_layers"]["fact"] >= 1
        assert payload["reasoning_layers"]["hypothesis"] >= 1
        assert "confidence" in payload
        assert payload["confidence"]["count"] >= 2
        assert "buckets" in payload["confidence"]

    asyncio.run(_scenario())
