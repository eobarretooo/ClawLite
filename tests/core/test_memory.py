from __future__ import annotations

import json
import base64
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


def test_memory_scaffolds_hierarchical_home_directories_and_new_default_paths(tmp_path: Path) -> None:
    store = MemoryStore(history_path=tmp_path / ".clawlite" / "state" / "memory.jsonl")

    assert (store.memory_home / "resources").exists()
    assert (store.memory_home / "items").exists()
    assert (store.memory_home / "categories").exists()
    assert (store.memory_home / "embeddings").exists()
    assert (store.memory_home / "emotional").exists()
    assert (store.memory_home / "versions").exists()
    assert (store.memory_home / "users").exists()
    assert (store.memory_home / "shared").exists()
    assert store.profile_path == store.memory_home / "emotional" / "profile.json"
    assert store.privacy_path == store.memory_home / "privacy.json"
    assert store.embeddings_path == store.memory_home / "embeddings" / "embeddings.jsonl"


def test_memory_migrates_legacy_profile_to_emotional_profile_path(tmp_path: Path) -> None:
    history_path = tmp_path / ".clawlite" / "state" / "memory.jsonl"
    memory_home = tmp_path / ".clawlite" / "memory"
    memory_home.mkdir(parents=True, exist_ok=True)
    legacy_profile = memory_home / "profile.json"
    legacy_profile.write_text(json.dumps({"timezone": "America/Sao_Paulo"}) + "\n", encoding="utf-8")

    store = MemoryStore(history_path=history_path)
    profile = json.loads(store.profile_path.read_text(encoding="utf-8"))
    assert profile["timezone"] == "America/Sao_Paulo"


def test_memory_migrates_legacy_state_embeddings_when_new_path_missing(tmp_path: Path) -> None:
    history_path = tmp_path / ".clawlite" / "state" / "memory.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_embeddings = history_path.parent / "embeddings.jsonl"
    legacy_embeddings.write_text(
        json.dumps({"id": "e1", "embedding": [0.1, 0.9], "created_at": "2026-03-01T00:00:00+00:00", "source": "seed"})
        + "\n",
        encoding="utf-8",
    )

    store = MemoryStore(history_path=history_path)
    lines = [line for line in store.embeddings_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["id"] == "e1"


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


def test_memory_add_flushes_and_fsyncs_append_paths(tmp_path: Path, monkeypatch) -> None:
    fsync_calls: list[int] = []
    real_fsync = __import__("os").fsync

    def _spy_fsync(fd: int) -> None:
        fsync_calls.append(fd)
        real_fsync(fd)

    monkeypatch.setattr("clawlite.core.memory.os.fsync", _spy_fsync)

    store = MemoryStore(tmp_path / "memory.jsonl")
    baseline_calls = len(fsync_calls)
    store.add("remember fsync durability path", source="session:fsync")

    assert len(fsync_calls) > baseline_calls


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


def test_memory_diagnostics_expose_backend_health_defaults(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")

    diag = store.diagnostics()
    assert diag["backend_name"] == "sqlite"
    assert diag["backend_supported"] is True
    assert diag["backend_initialized"] is True
    assert diag["backend_init_error"] == ""


def test_memory_diagnostics_preserve_backend_init_failure_details(tmp_path: Path, monkeypatch) -> None:
    class _FailingBackend:
        name = "failing"

        def is_supported(self) -> bool:
            return True

        def initialize(self, memory_home):
            del memory_home
            raise RuntimeError("backend init exploded")

    monkeypatch.setattr("clawlite.core.memory.resolve_memory_backend", lambda **kwargs: _FailingBackend())

    store = MemoryStore(tmp_path / "memory.jsonl")
    diag = store.diagnostics()
    assert diag["backend_name"] == "failing"
    assert diag["backend_supported"] is True
    assert diag["backend_initialized"] is False
    assert diag["backend_init_error"] == "backend init exploded"
    assert diag["last_error"] == "backend init exploded"

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


def test_memory_async_memorize_ingests_text_file_path_with_default_modality(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        note = tmp_path / "notes.md"
        note.write_text("Project alpha launch notes\nDeadline: 2026-05-10", encoding="utf-8")

        result = await store.memorize(file_path=str(note), source="session:file")
        assert result["status"] == "ok"
        assert result["mode"] == "add"
        assert "Project alpha launch notes" in str(result["record"]["text"])
        assert result["record"]["modality"] == "text"

    asyncio.run(_scenario())


def test_memory_async_memorize_ingests_url_audio_fallback_text_and_modality(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")

        result = await store.memorize(
            url="https://example.com/audio/meeting-42",
            modality="audio",
            metadata={"transcript": "Call with Ana about travel plans and deadlines."},
            source="session:audio",
        )

        assert result["status"] == "ok"
        assert result["mode"] == "add"
        text = str(result["record"]["text"]).lower()
        assert "https://example.com/audio/meeting-42" in text
        assert "travel plans" in text
        assert result["record"]["modality"] == "audio"

    asyncio.run(_scenario())


def test_memory_async_memorize_ingests_url_html_extracts_text_without_network(tmp_path: Path, monkeypatch) -> None:
    class _Headers:
        @staticmethod
        def get_content_type() -> str:
            return "text/html"

        @staticmethod
        def get_content_charset() -> str:
            return "utf-8"

    class _Response:
        headers = _Headers()

        @staticmethod
        def read(_max_bytes: int = -1) -> bytes:
            return b"<html><body><h1>Alpha</h1><p>Launch timeline updated.</p></body></html>"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return None

    def _fake_urlopen(request, timeout: float = 0.0):
        del request, timeout
        return _Response()

    monkeypatch.setattr("clawlite.core.memory.urllib.request.urlopen", _fake_urlopen)

    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        result = await store.memorize(url="https://example.com/news", modality="text", source="session:url")
        assert result["status"] == "ok"
        text = str(result["record"]["text"]).lower()
        assert "alpha" in text
        assert "launch timeline updated" in text

    asyncio.run(_scenario())


def test_memory_async_memorize_non_text_modality_fallback_keeps_reference_and_modality(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        image_path = tmp_path / "diagram.png"
        result = await store.memorize(file_path=str(image_path), modality="image", source="session:image")

        assert result["status"] == "ok"
        assert result["record"]["modality"] == "image"
        text = str(result["record"]["text"]).lower()
        assert "ingested image file reference" in text
        assert "diagram.png" in text

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


def test_memory_async_retrieve_llm_returns_next_step_query_from_json(tmp_path: Path, monkeypatch) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        store.add("project alpha deploys on friday", source="session:a")

        async def _json_completion(**kwargs):
            del kwargs
            payload = {
                "answer": "Project alpha deploys on Friday.",
                "next_step_query": "Do we have a rollback plan for project alpha?",
            }
            return {"choices": [{"message": {"content": json.dumps(payload)}}]}

        monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(acompletion=_json_completion))
        llm = await store.retrieve("project alpha", method="llm", limit=3)

        assert llm["method"] == "llm"
        assert llm["metadata"]["fallback_to_rag"] is False
        assert llm["answer"] == "Project alpha deploys on Friday."
        assert llm["next_step_query"] == "Do we have a rollback plan for project alpha?"

    asyncio.run(_scenario())


def test_memory_memorize_skips_when_privacy_pattern_matches(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        result = await store.memorize(text="meu token secreto e abc123", source="session:privacy")
        assert result["status"] == "skipped"
        assert result["record"] is None
        assert store.all() == []

    asyncio.run(_scenario())


def test_memory_privacy_skip_writes_audit_entry(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        store.privacy_path.write_text(
            json.dumps(
                {
                    "never_memorize_patterns": ["secret-token"],
                    "ephemeral_categories": ["context"],
                    "ephemeral_ttl_days": 7,
                    "encrypted_categories": [],
                    "audit_log": True,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        result = await store.memorize(text="contains secret-token", source="session:audit")
        assert result["status"] == "skipped"

        lines = [line for line in store.privacy_audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert lines
        payload = json.loads(lines[-1])
        assert payload["action"] == "memorize_skipped"
        assert payload["source"] == "session:audit"
        assert payload["reason"].startswith("pattern:")
        assert store.diagnostics()["privacy_audit_writes"] >= 1

    asyncio.run(_scenario())


def test_memory_ephemeral_ttl_cleanup_deletes_expired_rows(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        now = datetime.now(timezone.utc)
        old_stamp = (now - timedelta(days=3)).isoformat()
        fresh_stamp = (now - timedelta(hours=2)).isoformat()
        store.history_path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "id": "ttl-old",
                            "text": "stale context",
                            "source": "session:old",
                            "created_at": old_stamp,
                            "category": "context",
                        }
                    ),
                    json.dumps(
                        {
                            "id": "ttl-new",
                            "text": "fresh context",
                            "source": "session:new",
                            "created_at": fresh_stamp,
                            "category": "context",
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        store._append_embedding(record_id="ttl-old", embedding=[0.1, 0.9], created_at=old_stamp, source="session:old")
        store._append_embedding(record_id="ttl-new", embedding=[0.9, 0.1], created_at=fresh_stamp, source="session:new")
        store.privacy_path.write_text(
            json.dumps(
                {
                    "never_memorize_patterns": [],
                    "ephemeral_categories": ["context"],
                    "ephemeral_ttl_days": 1,
                    "encrypted_categories": [],
                    "audit_log": True,
                }
            )
            + "\n",
            encoding="utf-8",
        )

        await store.memorize(text="trigger cleanup", source="session:ttl")

        remaining_ids = {row.id for row in store.all()}
        assert "ttl-old" not in remaining_ids
        assert "ttl-new" in remaining_ids
        embedding_ids = {json.loads(line)["id"] for line in store.embeddings_path.read_text(encoding="utf-8").splitlines() if line.strip()}
        assert "ttl-old" not in embedding_ids
        assert store.diagnostics()["privacy_ttl_deleted"] >= 1

    asyncio.run(_scenario())


def test_memory_encrypted_category_roundtrip_preserves_plain_reads(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl", memory_auto_categorize=False)
    store.privacy_path.write_text(
        json.dumps(
            {
                "never_memorize_patterns": [],
                "ephemeral_categories": ["context"],
                "ephemeral_ttl_days": 7,
                "encrypted_categories": ["context"],
                "audit_log": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    row = store.add("sensitive context text", source="session:enc")
    assert row.text == "sensitive context text"
    raw_lines = [line for line in store.history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert raw_lines
    stored = json.loads(raw_lines[0])
    assert stored["text"].startswith("enc:v2:")
    assert store.privacy_key_path.exists()

    read_back = store.all()
    assert read_back[0].text == "sensitive context text"
    assert store.search("sensitive", limit=1)[0].text == "sensitive context text"


def test_memory_decrypt_supports_legacy_enc_v1_rows(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    legacy_text = base64.urlsafe_b64encode("legacy encrypted text".encode("utf-8")).decode("ascii")
    store.history_path.write_text(
        json.dumps(
            {
                "id": "legacy-v1",
                "text": f"enc:v1:{legacy_text}",
                "source": "session:legacy",
                "created_at": "2026-03-01T00:00:00+00:00",
                "category": "context",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    rows = store.all()
    assert len(rows) == 1
    assert rows[0].text == "legacy encrypted text"


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
    assert enabled_row.emotional_tone == "sad"


def test_memory_detect_emotional_tone_scores_frustrated_phrase() -> None:
    tone = MemoryStore._detect_emotional_tone("Não funciona, erro de novo isso")
    assert tone == "frustrated"


def test_memory_detect_emotional_tone_scores_excited_phrase() -> None:
    tone = MemoryStore._detect_emotional_tone("Incrível!! Funcionou, consegui perfeito")
    assert tone == "excited"


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


def test_memory_memorize_add_persists_resource_item_and_category_layers(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl", memory_auto_categorize=False)
        result = await store.memorize(text="remember this layered memory", source="session:layers")

        assert result["status"] == "ok"
        record_id = str(result["record"]["id"])
        category = str(result["record"]["category"])

        resource_files = list(store.resources_path.glob("conv_*.jsonl"))
        assert resource_files
        resource_rows: list[dict[str, object]] = []
        for path in resource_files:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    resource_rows.append(json.loads(line))
        assert any(str(row.get("id")) == record_id for row in resource_rows)

        item_payload = json.loads(store._item_file_path(category).read_text(encoding="utf-8"))
        assert any(str(item.get("id", "")) == record_id for item in item_payload.get("items", []))

        category_md = store._category_file_path(category).read_text(encoding="utf-8")
        assert "Total items" in category_md
        assert record_id in category_md

    asyncio.run(_scenario())


def test_memory_memorize_consolidate_persists_joined_resource_and_category_summary(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        result = await store.memorize(
            messages=[
                {"role": "user", "content": "remember my timezone is UTC-3"},
                {"role": "assistant", "content": "noted timezone UTC-3 preference"},
            ],
            source="session:consolidate-layers",
        )

        assert result["status"] == "ok"
        record_id = str(result["record"]["id"])
        resource_files = list(store.resources_path.glob("conv_*.jsonl"))
        rows: list[dict[str, object]] = []
        for path in resource_files:
            rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        persisted = next(row for row in rows if str(row.get("id")) == record_id)
        assert "user:" in str(persisted.get("text", ""))
        assert "assistant:" in str(persisted.get("text", ""))

        category = str(result["record"]["category"])
        category_md = store._category_file_path(category).read_text(encoding="utf-8")
        assert "Top Sources" in category_md
        assert "Recent Items" in category_md

    asyncio.run(_scenario())


def test_memory_delete_by_prefixes_prunes_layer_files_and_backend_index(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    keep = store.add("keep layer row", source="session:keep")
    drop = store.add("drop layer row", source="session:drop")

    deleted = store.delete_by_prefixes([drop.id[:8]], limit=1)

    assert deleted["deleted_count"] == 1
    assert int(deleted["backend_deleted"]) >= 1
    keep_item_payload = json.loads(store._item_file_path(keep.category).read_text(encoding="utf-8"))
    item_ids = {str(row.get("id", "")) for row in keep_item_payload.get("items", []) if isinstance(row, dict)}
    assert keep.id in item_ids
    assert drop.id not in item_ids

    backend_rows = store.backend.fetch_layer_records(layer="item", limit=10)
    backend_ids = {str(row.get("record_id", "")) for row in backend_rows}
    assert drop.id not in backend_ids


def test_memory_user_scoped_memorize_and_retrieve_isolated_by_default(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        await store.memorize(text="alpha-only memory", source="session:a", user_id="user-a")
        await store.memorize(text="beta-only memory", source="session:b", user_id="user-b")

        a_hits = await store.retrieve("memory", user_id="user-a", limit=5)
        b_hits = await store.retrieve("memory", user_id="user-b", limit=5)

        assert any("alpha-only" in str(item["text"]).lower() for item in a_hits["hits"])
        assert all("beta-only" not in str(item["text"]).lower() for item in a_hits["hits"])
        assert any("beta-only" in str(item["text"]).lower() for item in b_hits["hits"])
        assert all("alpha-only" not in str(item["text"]).lower() for item in b_hits["hits"])

    asyncio.run(_scenario())


def test_memory_shared_opt_in_controls_include_shared_results(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        await store.memorize(text="shared handbook", source="session:shared", shared=True)
        await store.memorize(text="private alpha note", source="session:a", user_id="user-a")

        without_optin = await store.retrieve("shared", user_id="user-a", include_shared=True, limit=5)
        assert all("shared handbook" not in str(item["text"]).lower() for item in without_optin["hits"])

        store.set_shared_opt_in("user-a", True)
        with_optin = await store.retrieve("shared", user_id="user-a", include_shared=True, limit=5)
        assert any("shared handbook" in str(item["text"]).lower() for item in with_optin["hits"])

    asyncio.run(_scenario())


def test_memory_branch_create_list_checkout_basics(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    snap = store.snapshot("seed")
    created = store.branch("feature-x", from_version=snap, checkout=False)
    listed = store.branches()
    checked = store.checkout_branch("feature-x")

    assert created["name"] == "feature-x"
    assert created["head"] == snap
    assert "feature-x" in listed["branches"]
    assert checked["current"] == "feature-x"


def test_memory_merge_creates_snapshot_and_updates_target_head(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    store.add("main baseline", source="session:main")
    main_snap = store.snapshot("main-base")
    store.branch("feature", from_version=main_snap, checkout=True)
    store.add("feature line", source="session:feature")
    feature_snap = store.snapshot("feature-work")
    store.checkout_branch("main")

    merged = store.merge("feature", "main")
    listed = store.branches()

    assert merged["source_head"] == feature_snap
    assert merged["target_head_before"] == main_snap
    assert merged["target_head_after"] == merged["version"]
    assert listed["branches"]["main"]["head"] == merged["version"]


def test_memory_quality_state_update_persists_report_with_drift_and_recommendations(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")

    first = store.update_quality_state(
        retrieval_metrics={"attempts": 10, "hits": 8, "rewrites": 1},
        turn_stability_metrics={"successes": 9, "errors": 1},
        semantic_metrics={"enabled": True, "coverage_ratio": 0.75},
        sampled_at="2026-03-05T10:00:00+00:00",
    )
    second = store.update_quality_state(
        retrieval_metrics={"attempts": 10, "hits": 4, "rewrites": 2},
        turn_stability_metrics={"successes": 6, "errors": 4},
        semantic_metrics={"enabled": True, "coverage_ratio": 0.45},
        sampled_at="2026-03-05T11:00:00+00:00",
    )

    assert first["score"] >= second["score"]
    snapshot = store.quality_state_snapshot()
    assert snapshot["version"] == 1
    assert snapshot["updated_at"] == "2026-03-05T11:00:00+00:00"
    assert snapshot["current"]["score"] == second["score"]
    assert snapshot["current"]["drift"]["assessment"] in {"stable", "degrading", "improving", "baseline"}
    assert isinstance(snapshot["current"]["recommendations"], list)
    assert snapshot["current"]["recommendations"]
    assert len(snapshot["history"]) == 2
    assert store.quality_state_path.exists()


def test_memory_quality_state_snapshot_normalizes_tuning_defaults_and_legacy_shapes(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    store.quality_state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "updated_at": "2026-03-05T12:00:00+00:00",
                "baseline": {},
                "current": {},
                "history": [],
                "tuning": {
                    "degrading_streak": -7,
                    "last_action": None,
                    "recent_actions": [{"action": f"a{idx}"} for idx in range(30)],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    snapshot = store.quality_state_snapshot()
    tuning = snapshot["tuning"]
    assert tuning["degrading_streak"] == 0
    assert tuning["last_action"] == ""
    assert tuning["last_action_at"] == ""
    assert tuning["last_action_status"] == ""
    assert tuning["last_reason"] == ""
    assert tuning["next_run_at"] == ""
    assert tuning["last_run_at"] == ""
    assert tuning["last_error"] == ""
    assert len(tuning["recent_actions"]) == store._MAX_QUALITY_TUNING_RECENT_ACTIONS
    assert tuning["recent_actions"][-1]["action"] == "a29"


def test_memory_update_quality_tuning_state_persists_without_history_growth_and_supports_update_patch(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    store.update_quality_state(
        retrieval_metrics={"attempts": 10, "hits": 8, "rewrites": 1},
        turn_stability_metrics={"successes": 9, "errors": 1},
        semantic_metrics={"enabled": True, "coverage_ratio": 0.75},
        sampled_at="2026-03-05T10:00:00+00:00",
    )
    before = store.quality_state_snapshot()

    tuning = store.update_quality_tuning_state(
        {
            "degrading_streak": 2,
            "last_action": "diagnostics_snapshot",
            "last_action_status": "ok",
            "last_action_at": "2026-03-05T10:01:00+00:00",
            "last_reason": "quality_drift",
            "next_run_at": "2026-03-05T10:31:00+00:00",
            "recent_actions": [{"action": "diagnostics_snapshot", "status": "ok", "at": "2026-03-05T10:01:00+00:00"}],
        }
    )
    after = store.quality_state_snapshot()

    assert len(after["history"]) == len(before["history"])
    assert tuning["degrading_streak"] == 2
    assert after["tuning"]["last_action"] == "diagnostics_snapshot"
    assert after["tuning"]["last_action_status"] == "ok"
    assert after["tuning"]["last_reason"] == "quality_drift"

    store.update_quality_state(
        retrieval_metrics={"attempts": 10, "hits": 7, "rewrites": 2},
        turn_stability_metrics={"successes": 9, "errors": 1},
        semantic_metrics={"enabled": True, "coverage_ratio": 0.72},
        sampled_at="2026-03-05T10:30:00+00:00",
        tuning_patch={"last_action_status": "report_only", "last_error": ""},
    )
    snapshot = store.quality_state_snapshot()
    assert len(snapshot["history"]) == len(before["history"]) + 1
    assert snapshot["tuning"]["last_action_status"] == "report_only"


def test_memory_quality_tuning_recent_actions_is_bounded(tmp_path: Path, monkeypatch) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    monkeypatch.setattr(store, "_MAX_QUALITY_TUNING_RECENT_ACTIONS", 3)

    store.update_quality_tuning_state({"recent_actions": [{"action": "a1"}, {"action": "a2"}]})
    store.update_quality_tuning_state({"recent_actions": [{"action": "a3"}, {"action": "a4"}]})

    actions = store.quality_state_snapshot()["tuning"]["recent_actions"]
    assert [row["action"] for row in actions] == ["a2", "a3", "a4"]


def test_memory_quality_state_history_is_bounded(tmp_path: Path, monkeypatch) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    monkeypatch.setattr(store, "_MAX_QUALITY_HISTORY", 3)

    for idx in range(5):
        store.update_quality_state(
            retrieval_metrics={"attempts": 5, "hits": max(0, 5 - idx), "rewrites": idx},
            turn_stability_metrics={"successes": 5, "errors": idx},
            semantic_metrics={"enabled": False, "coverage_ratio": 0.0},
            sampled_at=f"2026-03-05T10:0{idx}:00+00:00",
        )

    snapshot = store.quality_state_snapshot()
    assert len(snapshot["history"]) == 3
    sampled = [row["sampled_at"] for row in snapshot["history"]]
    assert sampled == [
        "2026-03-05T10:02:00+00:00",
        "2026-03-05T10:03:00+00:00",
        "2026-03-05T10:04:00+00:00",
    ]


def test_memory_integration_policy_defaults_to_normal_on_empty_quality_state(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")

    policy = store.integration_policy("agent")

    assert policy["mode"] == "normal"
    assert policy["reason"] == "quality_state_uninitialized"
    assert policy["allow_memory_write"] is True
    assert policy["allow_skill_exec"] is True
    assert policy["allow_subagent_spawn"] is True
    assert policy["recommended_search_limit"] == 8
    assert policy["quality"]["has_report"] is False


def test_memory_integration_policy_uses_quality_state_for_degraded_and_severe_modes(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    store.quality_state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "updated_at": "2026-03-05T12:00:00+00:00",
                "baseline": {},
                "current": {
                    "score": 62,
                    "drift": {"assessment": "stable"},
                },
                "history": [],
                "tuning": {"degrading_streak": 2, "last_error": ""},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    degraded = store.integration_policy("agent")
    delegated = store.integration_policy("subagent")

    assert degraded["mode"] == "degraded"
    assert degraded["allow_memory_write"] is True
    assert degraded["allow_skill_exec"] is False
    assert degraded["allow_subagent_spawn"] is False
    assert degraded["recommended_search_limit"] == 4
    assert delegated["recommended_search_limit"] == 3
    assert delegated["allow_subagent_spawn"] is False

    store.quality_state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "updated_at": "2026-03-05T12:30:00+00:00",
                "baseline": {},
                "current": {
                    "score": 38,
                    "drift": {"assessment": "degrading"},
                },
                "history": [],
                "tuning": {"degrading_streak": 4, "last_error": ""},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    severe = store.integration_policy("agent")

    assert severe["mode"] == "severe"
    assert severe["allow_memory_write"] is False
    assert severe["allow_skill_exec"] is False
    assert severe["allow_subagent_spawn"] is False
    assert severe["recommended_search_limit"] == 2


def test_memory_integration_hint_is_empty_for_normal_and_present_for_risk_modes(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")

    assert store.integration_hint("agent") == ""

    store.quality_state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "updated_at": "2026-03-05T12:05:00+00:00",
                "baseline": {},
                "current": {
                    "score": 68,
                    "drift": {"assessment": "degrading"},
                },
                "history": [],
                "tuning": {"degrading_streak": 1, "last_error": ""},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    degraded_hint = store.integration_hint("agent")
    assert degraded_hint

    store.quality_state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "updated_at": "2026-03-05T12:06:00+00:00",
                "baseline": {},
                "current": {
                    "score": 80,
                    "drift": {"assessment": "stable"},
                },
                "history": [],
                "tuning": {"degrading_streak": 0, "last_error": "loop timeout"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    severe_hint = store.integration_hint("agent")
    assert severe_hint
    assert "severe" in severe_hint.lower()


def test_memory_integration_policies_snapshot_returns_expected_shape(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")

    snapshot = store.integration_policies_snapshot(session_id="sess-123")

    assert snapshot["session_id"] == "sess-123"
    assert snapshot["mode"] == "normal"
    assert isinstance(snapshot["quality"], dict)
    policies = snapshot["policies"]
    assert set(policies.keys()) == {"system", "agent", "subagent", "tool"}
    for actor, payload in policies.items():
        assert payload["actor"] == actor
        assert "allow_memory_write" in payload
        assert "allow_skill_exec" in payload
        assert "allow_subagent_spawn" in payload
        assert "recommended_search_limit" in payload
