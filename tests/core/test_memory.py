from __future__ import annotations

import json
import sys
import types
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from clawlite.core.memory import MemoryStore


def test_memory_store_add_and_search(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    store.add("I like python and async systems", source="user")
    store.add("Weather in Sao Paulo is warm", source="user")

    found = store.search("python", limit=3)
    assert found
    assert "python" in found[0].text.lower()


def test_memory_home_derivation_uses_state_sibling_mapping_and_keeps_local_behavior(tmp_path: Path) -> None:
    state_history = tmp_path / ".clawlite" / "state" / "memory.jsonl"
    state_store = MemoryStore(history_path=state_history)
    assert state_store.memory_home == state_history.parent.parent / "memory"

    local_history = tmp_path / "session" / "memory.jsonl"
    local_store = MemoryStore(history_path=local_history)
    assert local_store.memory_home == local_history.parent / "memory"


def test_memory_semantic_add_writes_embedding_file_when_enabled(tmp_path: Path, monkeypatch) -> None:
    def _fake_embedding(self: MemoryStore, text: str) -> list[float] | None:
        assert text
        return [0.25, 0.75]

    monkeypatch.setattr(MemoryStore, "_generate_embedding", _fake_embedding)

    store = MemoryStore(tmp_path / "memory.jsonl", semantic_enabled=True)
    row = store.add("Semantic candidate memory", source="user")

    lines = [line for line in store.embeddings_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["id"] == row.id
    assert payload["embedding"] == [0.25, 0.75]
    assert payload["source"] == "user"
    assert payload["created_at"] == row.created_at


def test_memory_semantic_backfill_populates_missing_embeddings_without_duplicates(tmp_path: Path, monkeypatch) -> None:
    def _fake_embedding(self: MemoryStore, text: str) -> list[float] | None:
        lowered = text.lower()
        if "history" in lowered:
            return [1.0, 0.0]
        if "curated" in lowered:
            return [0.0, 1.0]
        return [0.5, 0.5]

    monkeypatch.setattr(MemoryStore, "_generate_embedding", _fake_embedding)

    store = MemoryStore(tmp_path / "memory.jsonl", semantic_enabled=True)
    store.history_path.write_text(
        json.dumps(
            {
                "id": "hist001",
                "text": "history semantic row",
                "source": "seed:history",
                "created_at": "2026-03-01T00:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    store.curated_path.write_text(
        json.dumps(
            {
                "version": 2,
                "facts": [
                    {
                        "id": "cur001",
                        "text": "curated semantic row",
                        "source": "curated:seed",
                        "created_at": "2026-03-01T00:00:01+00:00",
                        "last_seen_at": "2026-03-01T00:00:01+00:00",
                        "mentions": 1,
                        "session_count": 1,
                        "sessions": ["session:a"],
                        "importance": 1.0,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    first = store.backfill_embeddings(limit=10)
    second = store.backfill_embeddings(limit=10)

    lines = [line for line in store.embeddings_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [json.loads(line)["id"] for line in lines]
    assert first["created"] == 2
    assert first["failed"] == 0
    assert second["created"] == 0
    assert second["skipped_existing"] == 2
    assert sorted(ids) == ["cur001", "hist001"]


def test_memory_search_hybrid_semantic_and_bm25_ranks_by_combined_score(tmp_path: Path, monkeypatch) -> None:
    class _FakeBM25:
        def __init__(self, _corpus: object) -> None:
            pass

        def get_scores(self, _query_tokens: object) -> list[float]:
            return [0.2, 0.8]

    def _fake_embedding(self: MemoryStore, text: str) -> list[float] | None:
        lowered = text.lower()
        if "alpha" in lowered:
            return [1.0, 0.0]
        if "beta" in lowered:
            return [0.0, 1.0]
        if "which" in lowered:
            return [1.0, 0.0]
        return [0.0, 0.0]

    monkeypatch.setattr("clawlite.core.memory.BM25Okapi", _FakeBM25)
    monkeypatch.setattr(MemoryStore, "_generate_embedding", _fake_embedding)

    store = MemoryStore(tmp_path / "memory.jsonl", semantic_enabled=True)
    store.add("alpha project memory", source="user")
    store.add("beta project memory", source="user")

    found = store.search("which project should I pick", limit=2)
    assert found
    assert "alpha" in found[0].text.lower()


def test_memory_consolidate(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    row = store.consolidate([
        {"role": "user", "content": "remember my timezone"},
        {"role": "assistant", "content": "ok timezone set"},
    ])
    assert row is not None
    assert "timezone" in row.text


def test_memory_consolidate_skips_trivial_exchange(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    row = store.consolidate([
        {"role": "user", "content": "ok"},
        {"role": "assistant", "content": "done"},
    ])
    assert row is None
    assert store.all() == []


def test_memory_consolidate_deduplicates_by_source_checkpoint(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    messages = [
        {"role": "user", "content": "remember that my timezone is UTC-3"},
        {"role": "assistant", "content": "noted, timezone preference stored"},
    ]
    first = store.consolidate(messages, source="session:abc")
    second = store.consolidate(messages, source="session:abc")
    assert first is not None
    assert second is None
    assert len(store.all()) == 1


def test_memory_consolidate_updates_curated_layer(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    store.consolidate(
        [
            {"role": "user", "content": "remember that I prefer concise answers"},
            {"role": "assistant", "content": "noted preference: concise answers"},
        ],
        source="session:42",
    )
    curated_rows = store.curated()
    assert curated_rows
    assert any("concise" in row.text.lower() for row in curated_rows)
    found = store.search("preference concise", limit=3)
    assert found
    assert any(row.source.startswith("curated:") for row in found)


def test_memory_search_prefers_overlap_even_with_negative_bm25(tmp_path: Path, monkeypatch) -> None:
    class _FakeBM25:
        def __init__(self, _corpus: object) -> None:
            pass

        def get_scores(self, _query_tokens: object) -> list[float]:
            # Simulates BM25 score inversion in tiny corpora:
            # matching row gets negative score and non-matching row gets 0.
            return [-0.3, 0.0]

    monkeypatch.setattr("clawlite.core.memory.BM25Okapi", _FakeBM25)

    store = MemoryStore(tmp_path / "memory.jsonl")
    store.add("I like python and async systems", source="user")
    store.add("Weather in Sao Paulo is warm", source="user")

    found = store.search("python", limit=1)
    assert found
    assert "python" in found[0].text.lower()


def test_memory_add_is_concurrency_safe(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")

    def _writer(idx: int) -> None:
        store.add(f"remember preference {idx}", source="load")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_writer, range(60)))

    rows = store.all()
    assert len(rows) == 60
    assert len({row.id for row in rows}) == 60


def test_memory_consolidate_promotes_repeated_facts_across_sessions(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    messages = [
        {"role": "user", "content": "remember that I prefer concise answers in summaries"},
        {"role": "assistant", "content": "noted, concise summaries preference saved"},
    ]

    first = store.consolidate(messages, source="session:a")
    second = store.consolidate(messages, source="session:b")

    assert first is not None
    assert second is not None
    curated_payload = json.loads(store.curated_path.read_text(encoding="utf-8"))
    facts = curated_payload["facts"]
    assert facts
    concise_fact = next(item for item in facts if "concise" in item["text"].lower())
    assert int(concise_fact["mentions"]) >= 2
    assert int(concise_fact["session_count"]) >= 2
    assert len(concise_fact["sessions"]) >= 2


def test_memory_consolidate_global_signature_count_tracks_cross_session(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    messages = [
        {"role": "user", "content": "remember my timezone is UTC-3 and keep it"},
        {"role": "assistant", "content": "timezone UTC-3 saved"},
    ]

    store.consolidate(messages, source="session:alpha")
    store.consolidate(messages, source="session:beta")

    checkpoints_payload = json.loads(store.checkpoints_path.read_text(encoding="utf-8"))
    global_signatures = checkpoints_payload.get("global_signatures", {})
    assert global_signatures
    counts = [int(item.get("count", 0)) for item in global_signatures.values()]
    assert max(counts) >= 2


def test_memory_consolidate_reads_legacy_checkpoints_format(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    store.checkpoints_path.write_text(
        json.dumps({"session:legacy": "sig-1"}) + "\n",
        encoding="utf-8",
    )

    row = store.consolidate(
        [
            {"role": "user", "content": "remember that project deadline is monday morning"},
            {"role": "assistant", "content": "deadline captured"},
        ],
        source="session:new",
    )
    assert row is not None
    checkpoints_payload = json.loads(store.checkpoints_path.read_text(encoding="utf-8"))
    assert "source_signatures" in checkpoints_payload
    assert "global_signatures" in checkpoints_payload


def test_memory_history_prunes_when_store_exceeds_limit(tmp_path: Path, monkeypatch) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    monkeypatch.setattr(store, "_MAX_HISTORY_RECORDS", 5)

    for idx in range(12):
        store.add(f"remember preference {idx}", source="bulk")

    rows = store.all()
    assert len(rows) == 5
    assert rows[0].text.endswith("7")
    assert rows[-1].text.endswith("11")


def test_memory_curated_prunes_low_rank_facts_when_oversized(tmp_path: Path, monkeypatch) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    monkeypatch.setattr(store, "_MAX_CURATED_FACTS", 2)

    repeated = [
        {"role": "user", "content": "remember I always use python for backend tasks"},
        {"role": "assistant", "content": "noted backend python preference"},
    ]
    store.consolidate(repeated, source="session:1")
    store.consolidate(repeated, source="session:2")

    store.consolidate(
        [
            {"role": "user", "content": "remember that I enjoy mountain biking on weekends"},
            {"role": "assistant", "content": "weekend biking noted"},
        ],
        source="session:3",
    )
    store.consolidate(
        [
            {"role": "user", "content": "remember that my favorite snack is popcorn"},
            {"role": "assistant", "content": "popcorn preference noted"},
        ],
        source="session:4",
    )

    curated_payload = json.loads(store.curated_path.read_text(encoding="utf-8"))
    facts = curated_payload["facts"]
    assert len(facts) == 2
    assert any("python" in item["text"].lower() for item in facts)


def test_memory_search_is_deterministic_for_repeated_queries(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    store.consolidate(
        [
            {"role": "user", "content": "remember that project alpha deadline is friday"},
            {"role": "assistant", "content": "project alpha deadline captured"},
        ],
        source="session:a",
    )
    store.add("project alpha includes migration work", source="user")
    store.add("project beta has a different schedule", source="user")

    first = [item.id for item in store.search("project alpha deadline", limit=4)]
    second = [item.id for item in store.search("project alpha deadline", limit=4)]
    assert first == second


def test_memory_search_prefers_promoted_curated_fact(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    for source in ("session:a", "session:b", "session:c"):
        store.consolidate(
            [
                {"role": "user", "content": "remember that my timezone is UTC-3"},
                {"role": "assistant", "content": "timezone preference UTC-3 saved"},
            ],
            source=source,
        )
    store.add("Timezone conversions can use UTC offsets", source="note")

    found = store.search("timezone utc-3", limit=3)
    assert found
    assert found[0].source.startswith("curated:")
    assert "utc-3" in found[0].text.lower()


def test_memory_search_uses_recency_to_break_lexical_and_bm25_ties(tmp_path: Path, monkeypatch) -> None:
    class _FakeBM25:
        def __init__(self, _corpus: object) -> None:
            pass

        def get_scores(self, _query_tokens: object) -> list[float]:
            return [0.0, 0.0]

    monkeypatch.setattr("clawlite.core.memory.BM25Okapi", _FakeBM25)

    store = MemoryStore(tmp_path / "memory.jsonl")
    now = datetime.now(timezone.utc)
    older = now - timedelta(days=120)
    newer = now - timedelta(hours=2)
    rows = [
        {
            "id": "old-record",
            "text": "project alpha timeline review",
            "source": "session:old",
            "created_at": older.isoformat(),
        },
        {
            "id": "new-record",
            "text": "project alpha timeline review",
            "source": "session:new",
            "created_at": newer.isoformat(),
        },
    ]
    store.history_path.write_text("\n".join(json.dumps(item) for item in rows) + "\n", encoding="utf-8")

    found = store.search("project alpha timeline", limit=2)
    assert found
    assert found[0].id == "new-record"


def test_memory_search_temporal_intent_prefers_temporal_marker_on_tie(tmp_path: Path, monkeypatch) -> None:
    class _FakeBM25:
        def __init__(self, _corpus: object) -> None:
            pass

        def get_scores(self, _query_tokens: object) -> list[float]:
            return [0.0, 0.0]

    monkeypatch.setattr("clawlite.core.memory.BM25Okapi", _FakeBM25)

    store = MemoryStore(tmp_path / "memory.jsonl")
    stamp = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "id": "non-temporal",
            "text": "project alpha review notes",
            "source": "session:a",
            "created_at": stamp,
        },
        {
            "id": "temporal",
            "text": "project alpha review monday",
            "source": "session:b",
            "created_at": stamp,
        },
    ]
    store.history_path.write_text("\n".join(json.dumps(item) for item in rows) + "\n", encoding="utf-8")

    found = store.search("project alpha next week", limit=2)
    assert found
    assert found[0].id == "temporal"


def test_memory_history_read_tolerates_corrupt_lines_and_repairs_file(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    valid_a = {
        "id": "r1",
        "text": "remember alpha",
        "source": "session:a",
        "created_at": "2026-03-03T00:00:00+00:00",
    }
    valid_b = {
        "id": "r2",
        "text": "remember beta",
        "source": "session:b",
        "created_at": "2026-03-03T00:00:01+00:00",
    }
    store.history_path.write_text(
        "\n".join([json.dumps(valid_a), "{not-json", json.dumps(valid_b)]) + "\n",
        encoding="utf-8",
    )

    rows = store.all()

    assert [row.text for row in rows] == ["remember alpha", "remember beta"]
    repaired_lines = [line for line in store.history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(repaired_lines) == 2
    diag = store.diagnostics()
    assert diag["history_read_corrupt_lines"] == 1
    assert diag["history_repaired_files"] == 1


def test_memory_consolidate_diagnostics_track_writes_and_dedup_hits(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    messages = [
        {"role": "user", "content": "remember that I prefer concise output"},
        {"role": "assistant", "content": "noted concise output preference"},
    ]

    assert store.consolidate(messages, source="session:a") is not None
    assert store.consolidate(messages, source="session:a") is None
    assert store.consolidate(messages, source="session:b") is not None

    diag = store.diagnostics()
    assert diag["consolidate_writes"] == 2
    assert diag["consolidate_dedup_hits"] == 1


def test_memory_recover_session_context_uses_history_then_curated_fallback(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    store.add("session direct context", source="abc")
    store.curated_path.write_text(
        json.dumps(
            {
                "version": 2,
                "facts": [
                    {
                        "id": "f1",
                        "text": "curated fallback context",
                        "source": "curated:session:abc",
                        "created_at": "2026-03-03T00:00:02+00:00",
                        "last_seen_at": "2026-03-03T00:00:02+00:00",
                        "mentions": 1,
                        "session_count": 1,
                        "sessions": ["session:abc"],
                        "importance": 1.0,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    snippets = store.recover_session_context("abc", limit=4)

    assert snippets == ["session direct context", "curated fallback context"]
    diag = store.diagnostics()
    assert diag["session_recovery_attempts"] == 1
    assert diag["session_recovery_hits"] == 1


def test_memory_delete_by_prefixes_removes_from_history_and_curated(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    keep = store.add("keep history row", source="session:keep")
    drop_history = store.add("drop history row", source="session:drop")
    store.curated_path.write_text(
        json.dumps(
            {
                "version": 2,
                "facts": [
                    {
                        "id": "curdrop001",
                        "text": "drop curated row",
                        "source": "curated:session:drop",
                        "created_at": "2026-03-03T00:00:01+00:00",
                        "last_seen_at": "2026-03-03T00:00:01+00:00",
                        "mentions": 1,
                        "session_count": 1,
                        "sessions": ["session:drop"],
                        "importance": 1.0,
                    },
                    {
                        "id": "curkeep01",
                        "text": "keep curated row",
                        "source": "curated:session:keep",
                        "created_at": "2026-03-03T00:00:02+00:00",
                        "last_seen_at": "2026-03-03T00:00:02+00:00",
                        "mentions": 1,
                        "session_count": 1,
                        "sessions": ["session:keep"],
                        "importance": 1.0,
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    deleted = store.delete_by_prefixes([drop_history.id[:8], "curdrop"], limit=10)

    assert deleted["deleted_count"] == 2
    assert deleted["history_deleted"] == 1
    assert deleted["curated_deleted"] == 1
    history_ids = {row.id for row in store.all()}
    curated_ids = {row.id for row in store.curated()}
    assert keep.id in history_ids
    assert drop_history.id not in history_ids
    assert "curkeep01" in curated_ids
    assert "curdrop001" not in curated_ids


def test_memory_delete_by_prefixes_prunes_embedding_rows_for_deleted_ids(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl", semantic_enabled=True)
    keep = store.add("keep history row", source="session:keep")
    drop = store.add("drop history row", source="session:drop")
    store.embeddings_path.write_text(
        "\n".join(
            [
                json.dumps({"id": keep.id, "embedding": [1.0, 0.0], "created_at": keep.created_at, "source": keep.source}),
                json.dumps({"id": drop.id, "embedding": [0.0, 1.0], "created_at": drop.created_at, "source": drop.source}),
                json.dumps({"id": drop.id, "embedding": [0.1, 0.9], "created_at": drop.created_at, "source": drop.source}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    deleted = store.delete_by_prefixes([drop.id[:8]], limit=1)

    assert deleted["deleted_count"] == 1
    assert deleted["history_deleted"] == 1
    assert deleted["embeddings_deleted"] == 2
    lines = [line for line in store.embeddings_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    remaining_ids = [json.loads(line)["id"] for line in lines]
    assert remaining_ids == [keep.id]


def test_memory_delete_by_prefixes_is_limit_bounded_and_keeps_repair_behavior(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    old = {
        "id": "aaa11111drop",
        "text": "old row",
        "source": "seed",
        "created_at": "2026-03-01T00:00:00+00:00",
    }
    new = {
        "id": "bbb22222drop",
        "text": "new row",
        "source": "seed",
        "created_at": "2026-03-02T00:00:00+00:00",
    }
    store.history_path.write_text(
        "\n".join([json.dumps(old), "{invalid", json.dumps(new)]) + "\n",
        encoding="utf-8",
    )

    deleted = store.delete_by_prefixes(["bbb"], limit=1)

    assert deleted["deleted_count"] == 1
    assert deleted["history_deleted"] == 1
    lines = store.history_path.read_text(encoding="utf-8").splitlines()
    assert "{invalid" not in lines
    kept_payloads = [json.loads(line) for line in lines if line.startswith("{") and '"id"' in line]
    kept_ids = {item["id"] for item in kept_payloads}
    assert "aaa11111drop" in kept_ids
    assert "bbb22222drop" not in kept_ids


def test_memory_record_normalization_fills_defaults_for_legacy_rows(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    store.history_path.write_text(
        json.dumps(
            {
                "id": "legacy-1",
                "text": "legacy row",
                "source": "seed",
                "created_at": "2026-03-01T00:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    rows = store.all()
    assert len(rows) == 1
    row = rows[0]
    assert row.user_id == "default"
    assert row.layer == "item"
    assert row.modality == "text"
    assert row.updated_at == ""
    assert row.confidence == 1.0
    assert row.decay_rate == 0.0
    assert row.emotional_tone == "neutral"


def test_generate_embedding_fallback_order_tries_openai_after_gemini_failure(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []

    async def _fake_aembedding(*, model: str, input: list[str]):
        del input
        calls.append(model)
        if model == "gemini/text-embedding-004":
            raise RuntimeError("gemini down")
        return {"data": [{"embedding": [0.11, 0.22]}]}

    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(aembedding=_fake_aembedding))

    store = MemoryStore(tmp_path / "memory.jsonl", semantic_enabled=True)
    embedding = store._generate_embedding("fallback test")
    assert embedding == [0.11, 0.22]
    assert calls == ["gemini/text-embedding-004", "openai/text-embedding-3-small"]


def test_memory_async_memorize_supports_text_and_messages(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        learned = await store.memorize(text="remember this from async", source="session:async")
        assert learned["status"] == "ok"
        assert learned["mode"] == "add"

        consolidated = await store.memorize(
            messages=[
                {"role": "user", "content": "remember my timezone is UTC-3"},
                {"role": "assistant", "content": "noted timezone UTC-3"},
            ],
            source="session:async",
        )
        assert consolidated["status"] == "ok"
        assert consolidated["mode"] == "consolidate"

    asyncio.run(_scenario())


def test_memory_async_retrieve_rag_and_llm_fallback(tmp_path: Path, monkeypatch) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        store.add("project alpha deploys on friday", source="session:a")

        rag = await store.retrieve("project alpha", method="rag", limit=3)
        assert rag["method"] == "rag"
        assert rag["count"] >= 1
        assert rag["hits"]
        assert rag["metadata"]["fallback_to_rag"] is False

        async def _broken_completion(**kwargs):
            del kwargs
            raise RuntimeError("llm unavailable")

        monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(acompletion=_broken_completion))
        llm = await store.retrieve("project alpha", method="llm", limit=3)
        assert llm["method"] == "llm"
        assert llm["hits"]
        assert llm["metadata"]["fallback_to_rag"] is True

    asyncio.run(_scenario())


def test_memory_memorize_skips_when_privacy_pattern_matches(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        result = await store.memorize(text="meu token secreto e abc123", source="session:privacy")
        assert result["status"] == "skipped"
        assert result["record"] is None
        assert store.all() == []

    asyncio.run(_scenario())


def test_memory_profile_auto_update_from_preferences_timezone_and_topics(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        await store.memorize(text="prefiro respostas curtas e moro em Sao Paulo", source="session:profile")
        await store.memorize(text="gosto de viagens internacionais", source="session:profile")
        await store.memorize(text="planejando viagens longas em 2026", source="session:profile")

        profile = json.loads(store.profile_path.read_text(encoding="utf-8"))
        assert profile["response_length_preference"] == "curto"
        assert profile["timezone"] == "America/Sao_Paulo"
        assert "viagens" in profile["interests"]

    asyncio.run(_scenario())


def test_memory_emotional_tracking_flag_controls_add_tone_detection(tmp_path: Path) -> None:
    disabled_store = MemoryStore(tmp_path / "disabled.jsonl")
    disabled_row = disabled_store.add("estou triste e ansioso com o prazo", source="user")
    assert disabled_row.emotional_tone == "neutral"

    enabled_store = MemoryStore(tmp_path / "enabled.jsonl", emotional_tracking=True)
    enabled_row = enabled_store.add("estou triste e ansioso com o prazo", source="user")
    assert enabled_row.emotional_tone == "negative"


def test_memory_snapshot_rollback_and_diff(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    first = store.add("baseline memory", source="session:a")
    snap_a = store.snapshot("before")

    second = store.add("new memory after snapshot", source="session:b")
    snap_b = store.snapshot("after")

    delta = store.diff(snap_a, snap_b)
    assert delta["counts"]["added"] == 1
    assert second.id in delta["added"]

    store.rollback(snap_a)
    ids_after_rollback = {row.id for row in store.all()}
    assert first.id in ids_after_rollback
    assert second.id not in ids_after_rollback
