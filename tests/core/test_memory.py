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
    assert store.working_memory_path == store.memory_home / "working-memory.json"
    assert store.working_memory_path.exists()
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


def test_memory_search_user_scope_uses_semantic_ranking(tmp_path: Path, monkeypatch) -> None:
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
    store.add("alpha project memory", source="user", user_id="alice")
    store.add("beta project memory", source="user", user_id="alice")

    found = store.search("which project should I pick", user_id="alice", limit=2)
    assert found
    assert "alpha" in found[0].text.lower()


def test_memory_search_include_shared_uses_semantic_ranking(tmp_path: Path, monkeypatch) -> None:
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
    store.add("alpha project memory", source="user", user_id="alice", shared=True)
    store.add("beta project memory", source="user", user_id="alice")
    store.set_shared_opt_in("alice", True)

    found = store.search("which project should I pick", user_id="alice", include_shared=True, limit=2)
    assert found
    assert "alpha" in found[0].text.lower()


def test_memory_search_entity_match_breaks_temporal_ties(tmp_path: Path, monkeypatch) -> None:
    class _FakeBM25:
        def __init__(self, _corpus: object) -> None:
            pass

        def get_scores(self, _query_tokens: object) -> list[float]:
            return [0.0, 0.0]

    def _fake_tokens(text: str) -> list[str]:
        lowered = text.lower()
        if "release" in lowered or "window" in lowered:
            return ["release", "window"]
        return ["note"]

    monkeypatch.setattr("clawlite.core.memory.BM25Okapi", _FakeBM25)
    monkeypatch.setattr(MemoryStore, "_tokens", staticmethod(_fake_tokens))

    store = MemoryStore(tmp_path / "memory.jsonl")
    store.add("Release window confirmed for 2026-05-10", source="user")
    store.add("Release window confirmed for 2026-05-12", source="user")

    found = store.search("what is the release window for 2026-05-10", limit=2)
    assert found
    assert "2026-05-10" in found[0].text


def test_memory_add_reinforces_existing_hash_in_same_scope(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")

    first = store.add("Remember release window on 2026-05-10", source="session:a", memory_type="event")
    second = store.add("remember   release window on 2026-05-10", source="session:b", memory_type="event")

    rows = store.all()
    assert len(rows) == 1
    assert second.id == first.id
    assert second.updated_at
    assert int(second.metadata["reinforcement_count"]) == 2
    assert str(second.metadata["last_reinforced_at"])

    item_payload = json.loads((store.items_path / "context.json").read_text(encoding="utf-8"))
    assert len(item_payload["items"]) == 1
    assert item_payload["items"][0]["id"] == first.id
    assert int(item_payload["items"][0]["metadata"]["reinforcement_count"]) == 2


def test_memory_add_reinforcement_stays_local_to_each_user_scope(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")

    alice_first = store.add("remember deployment checklist", source="session:a", user_id="alice")
    alice_second = store.add("remember deployment checklist", source="session:b", user_id="alice")
    bob = store.add("remember deployment checklist", source="session:c", user_id="bob")

    assert alice_first.id == alice_second.id
    assert alice_first.id != bob.id

    alice_scope = store._scope_paths(user_id="alice", shared=False)
    bob_scope = store._scope_paths(user_id="bob", shared=False)
    alice_rows = store._read_history_records_from(alice_scope["history"])
    bob_rows = store._read_history_records_from(bob_scope["history"])
    assert len(alice_rows) == 1
    assert len(bob_rows) == 1
    assert int(alice_rows[0].metadata["reinforcement_count"]) == 2
    assert int(bob_rows[0].metadata["reinforcement_count"]) == 1

    global_rows = [row for row in store.all() if "deployment checklist" in row.text]
    assert len(global_rows) == 2
    by_id = {row.id: row for row in global_rows}
    assert int(by_id[alice_first.id].metadata["reinforcement_count"]) == 2
    assert int(by_id[bob.id].metadata["reinforcement_count"]) == 1


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


def test_memory_search_salience_prefers_reinforced_record_on_close_tie(tmp_path: Path, monkeypatch) -> None:
    class _FakeBM25:
        def __init__(self, _corpus: object) -> None:
            pass

        def get_scores(self, _query_tokens: object) -> list[float]:
            return [0.0, 0.0]

    monkeypatch.setattr("clawlite.core.memory.BM25Okapi", _FakeBM25)

    store = MemoryStore(tmp_path / "memory.jsonl")
    now_iso = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "id": "reinforced",
            "text": "project alpha rollout notes",
            "source": "session:a",
            "created_at": now_iso,
            "metadata": {
                "content_hash": "aaa111",
                "scope_key": "user:default",
                "reinforcement_count": 5,
                "last_reinforced_at": now_iso,
            },
        },
        {
            "id": "plain",
            "text": "project alpha deployment notes",
            "source": "session:b",
            "created_at": now_iso,
            "metadata": {
                "content_hash": "bbb222",
                "scope_key": "user:default",
                "reinforcement_count": 1,
                "last_reinforced_at": now_iso,
            },
        },
    ]
    store.history_path.write_text("\n".join(json.dumps(item) for item in rows) + "\n", encoding="utf-8")

    found = store.search("project alpha", limit=2)
    assert found
    assert found[0].id == "reinforced"


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


def test_memory_working_set_persists_and_shares_parent_subagent_family(tmp_path: Path) -> None:
    history_path = tmp_path / "memory.jsonl"
    store = MemoryStore(history_path)
    store.remember_working_set("cli:owner", role="user", content="parent session says deploy on friday", user_id="42")
    store.remember_working_set(
        "cli:owner:subagent",
        role="assistant",
        content="subagent found the release checklist",
        user_id="42",
        metadata={"channel": "telegram"},
    )

    reloaded = MemoryStore(history_path)
    parent_rows = reloaded.get_working_set("cli:owner", limit=8)
    child_rows = reloaded.get_working_set("cli:owner:subagent", limit=8)

    assert [row["content"] for row in parent_rows] == [
        "subagent found the release checklist",
        "parent session says deploy on friday",
    ]
    assert [row["session_id"] for row in parent_rows] == ["cli:owner:subagent", "cli:owner"]
    assert [row["content"] for row in child_rows] == [
        "subagent found the release checklist",
        "parent session says deploy on friday",
    ]
    assert all(row["share_group"] == "cli:owner" for row in parent_rows)
    assert child_rows[0]["metadata"]["channel"] == "telegram"


def test_memory_working_set_keeps_siblings_isolated_until_family_share_is_enabled(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    store.remember_working_set("cli:owner", role="assistant", content="parent context", user_id="42")
    store.remember_working_set("cli:owner:subagent-a", role="assistant", content="subagent a findings", user_id="42")
    store.remember_working_set("cli:owner:subagent-b", role="assistant", content="subagent b findings", user_id="42")

    initial = store.get_working_set("cli:owner:subagent-a", limit=8)
    assert [row["content"] for row in initial] == ["subagent a findings", "parent context"]

    store.set_working_memory_share_scope("cli:owner:subagent-a", "family")
    store.set_working_memory_share_scope("cli:owner:subagent-b", "family")

    updated = store.get_working_set("cli:owner:subagent-a", limit=8)
    assert [row["content"] for row in updated] == [
        "subagent b findings",
        "subagent a findings",
        "parent context",
    ]


def test_memory_recover_session_context_prefers_working_set_before_history_and_curated(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    store.remember_working_set("abc", role="assistant", content="working memory summary")
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

    assert snippets == ["working memory summary", "session direct context", "curated fallback context"]


def test_memory_working_set_auto_promotes_episode_snapshots_in_batches(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    session_id = "cli:owner"
    messages = [
        ("user", "Remember the important deployment summary for Friday at 14:00 UTC and keep it in memory."),
        ("assistant", "Deployment is scheduled for Friday at 14:00 UTC with one blocker still open."),
        ("user", "Remember the release checklist status and the security blocker for this project."),
        ("assistant", "Checklist has five pending items and the blocker is still waiting on review."),
    ]
    for role, content in messages:
        store.remember_working_set(session_id, role=role, content=content, user_id="42")

    first_batch = [row for row in store.all() if row.source == f"working-session:{session_id}"]
    assert len(first_batch) == 1
    first = first_batch[0]
    assert first.memory_type == "event"
    assert first.user_id == "42"
    assert first.metadata["working_memory_promoted"] is True
    assert first.metadata["working_memory_session_id"] == session_id
    assert first.metadata["working_memory_message_count"] == 4
    assert first.metadata["skip_profile_sync"] is True

    store.remember_working_set(session_id, role="user", content="Did the important blocker change for this deployment project?", user_id="42")
    store.remember_working_set(session_id, role="assistant", content="Not yet, it is still waiting on the security review outcome.", user_id="42")
    mid_batch = [row for row in store.all() if row.source == f"working-session:{session_id}"]
    assert len(mid_batch) == 1

    store.remember_working_set(session_id, role="user", content="Remember the mitigation path and the exact next deployment steps.", user_id="42")
    store.remember_working_set(session_id, role="assistant", content="Mitigation is to clear review, rerun tests, and deploy after approval.", user_id="42")
    final_batch = [row for row in store.all() if row.source == f"working-session:{session_id}"]
    assert len(final_batch) == 2

    diag = store.diagnostics()
    assert diag["working_memory_promotions"] == 2


def test_memory_search_prioritizes_same_session_working_episode(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    store.add("release checklist blocker still waiting", source="session:generic", user_id="42")
    store.add(
        "release checklist blocker still waiting on security review",
        source="working-session:cli:owner",
        user_id="42",
        memory_type="event",
        metadata={
            "working_memory_promoted": True,
            "working_memory_session_id": "cli:owner",
            "working_memory_share_group": "cli:owner",
            "working_memory_share_scope": "family",
            "skip_profile_sync": True,
        },
    )

    found = store.search("release checklist blocker", user_id="42", session_id="cli:owner", limit=2)

    assert found
    assert found[0].source == "working-session:cli:owner"


def test_memory_search_hides_parent_only_sibling_episodes_but_allows_family_scope(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    base_metadata = {
        "working_memory_promoted": True,
        "working_memory_parent_session_id": "cli:owner",
        "working_memory_share_group": "cli:owner",
        "skip_profile_sync": True,
    }
    store.add(
        "release checklist blocker for subagent a",
        source="working-session:cli:owner:subagent-a",
        user_id="42",
        memory_type="event",
        metadata={
            **base_metadata,
            "working_memory_session_id": "cli:owner:subagent-a",
            "working_memory_share_scope": "parent",
        },
    )
    store.add(
        "release checklist blocker for subagent b",
        source="working-session:cli:owner:subagent-b",
        user_id="42",
        memory_type="event",
        metadata={
            **base_metadata,
            "working_memory_session_id": "cli:owner:subagent-b",
            "working_memory_share_scope": "parent",
        },
    )

    initial = store.search("release checklist blocker", user_id="42", session_id="cli:owner:subagent-a", limit=5)
    initial_sources = {row.source for row in initial}
    assert "working-session:cli:owner:subagent-a" in initial_sources
    assert "working-session:cli:owner:subagent-b" not in initial_sources

    store.add(
        "release checklist blocker for subagent b with family sharing",
        source="working-session:cli:owner:subagent-b",
        user_id="42",
        memory_type="event",
        metadata={
            **base_metadata,
            "working_memory_session_id": "cli:owner:subagent-b",
            "working_memory_share_scope": "family",
        },
    )

    updated = store.search("release checklist blocker", user_id="42", session_id="cli:owner:subagent-a", limit=5)
    assert any(
        str(row.metadata.get("working_memory_session_id", "") or "") == "cli:owner:subagent-b"
        and str(row.metadata.get("working_memory_share_scope", "") or "") == "family"
        for row in updated
    )


def test_memory_retrieve_surfaces_visible_episode_digest_by_session_relationship(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        shared = {
            "working_memory_promoted": True,
            "working_memory_parent_session_id": "cli:owner",
            "working_memory_share_group": "cli:owner",
            "skip_profile_sync": True,
        }
        store.add(
            "release checklist blocker for parent coordinator",
            source="working-session:cli:owner",
            user_id="42",
            memory_type="event",
            metadata={
                **shared,
                "working_memory_session_id": "cli:owner",
                "working_memory_share_scope": "family",
            },
        )
        store.add(
            "release checklist blocker for current subagent",
            source="working-session:cli:owner:subagent-a",
            user_id="42",
            memory_type="event",
            metadata={
                **shared,
                "working_memory_session_id": "cli:owner:subagent-a",
                "working_memory_share_scope": "parent",
            },
        )
        store.add(
            "release checklist blocker for sibling helper",
            source="working-session:cli:owner:subagent-b",
            user_id="42",
            memory_type="event",
            metadata={
                **shared,
                "working_memory_session_id": "cli:owner:subagent-b",
                "working_memory_share_scope": "family",
            },
        )
        store.add(
            "release checklist blocker for hidden sibling",
            source="working-session:cli:owner:subagent-c",
            user_id="42",
            memory_type="event",
            metadata={
                **shared,
                "working_memory_session_id": "cli:owner:subagent-c",
                "working_memory_share_scope": "parent",
            },
        )

        retrieved = await store.retrieve(
            "release checklist blocker",
            method="rag",
            user_id="42",
            session_id="cli:owner:subagent-a",
            limit=4,
        )

        digest = retrieved["episodic_digest"]
        assert digest is not None
        assert retrieved["metadata"]["episodic_digest"] == digest
        sessions = {row["session_id"]: row["label"] for row in digest["sessions"]}
        assert sessions["cli:owner:subagent-a"] == "current"
        assert sessions["cli:owner"] == "parent"
        assert sessions["cli:owner:subagent-b"] == "sibling"
        assert "cli:owner:subagent-c" not in sessions
        assert "current:cli:owner:subagent-a" in digest["summary"]
        assert "parent:cli:owner" in digest["summary"]
        assert "sibling:cli:owner:subagent-b" in digest["summary"]

    asyncio.run(_scenario())


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


def test_memory_list_recent_candidates_uses_backend_bounded_scan_without_history_full_read(tmp_path: Path, monkeypatch) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")

    def _fake_fetch_layer_records(self, *, layer: str, category=None, limit: int = 200):
        del self
        del category
        assert layer == "item"
        assert limit == 33
        return [
            {
                "payload": {
                    "id": "abc12345feed6789",
                    "text": "backend candidate",
                    "source": "seed:drop",
                    "created_at": "2026-03-06T00:00:00+00:00",
                    "category": "context",
                }
            }
        ]

    def _blocked_locked_file(*args, **kwargs):
        del args, kwargs
        raise AssertionError("history lock/read should not run when backend scan already satisfies limit")

    monkeypatch.setattr(type(store.backend), "fetch_layer_records", _fake_fetch_layer_records)
    monkeypatch.setattr(store, "_locked_file", _blocked_locked_file)

    rows = store.list_recent_candidates(source="seed:drop", ref_prefix="mem:abc12345", limit=1, max_scan=33)
    assert len(rows) == 1
    assert rows[0].id == "abc12345feed6789"
    assert rows[0].source == "seed:drop"


def test_memory_list_recent_candidates_falls_back_to_bounded_recent_history_scan(tmp_path: Path, monkeypatch) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    old = store.add("old row", source="seed")
    mid = store.add("mid row", source="seed")
    new = store.add("new row", source="seed")

    def _empty_fetch_layer_records(self, **kwargs):
        del self, kwargs
        return []

    monkeypatch.setattr(type(store.backend), "fetch_layer_records", _empty_fetch_layer_records)

    rows = store.list_recent_candidates(source="seed", limit=2, max_scan=2)
    assert len(rows) == 2
    ids = [row.id for row in rows]
    assert new.id in ids
    assert mid.id in ids
    assert old.id not in ids


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
    assert row.reasoning_layer == "fact"
    assert row.modality == "text"
    assert row.updated_at == ""
    assert row.confidence == 1.0
    assert row.decay_rate == 0.0
    assert row.emotional_tone == "neutral"
    assert row.memory_type == "knowledge"
    assert row.happened_at == ""
    assert row.metadata == {}


def test_memory_reasoning_layer_and_confidence_roundtrip_on_write_and_read(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    created = store.add(
        "Decision: use blue-green deploy",
        source="session:decision",
        reasoning_layer="decision",
        confidence=0.42,
        memory_type="skill",
        happened_at="2026-03-10T00:00:00+00:00",
        metadata={"origin": "manual", "tags": ["deploy", "release"]},
    )

    assert created.reasoning_layer == "decision"
    assert created.confidence == 0.42
    assert created.memory_type == "skill"
    assert created.happened_at == "2026-03-10T00:00:00+00:00"
    assert created.metadata["origin"] == "manual"
    read_back = store.all()
    assert len(read_back) == 1
    assert read_back[0].reasoning_layer == "decision"
    assert read_back[0].confidence == 0.42
    assert read_back[0].memory_type == "skill"
    assert read_back[0].happened_at == "2026-03-10T00:00:00+00:00"
    assert read_back[0].metadata["origin"] == "manual"

    raw_line = next(line for line in store.history_path.read_text(encoding="utf-8").splitlines() if line.strip())
    payload = json.loads(raw_line)
    assert payload["reasoning_layer"] == "decision"
    assert payload["confidence"] == 0.42
    assert payload["memory_type"] == "skill"
    assert payload["happened_at"] == "2026-03-10T00:00:00+00:00"
    assert payload["metadata"]["origin"] == "manual"


def test_memory_infers_event_type_happened_at_and_structured_metadata(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    row = store.add(
        "Product launch meeting scheduled for 2026-05-10 09:30 with ops@example.com",
        source="session:event",
    )

    assert row.memory_type == "event"
    assert row.happened_at == "2026-05-10T09:30:00+00:00"
    assert row.metadata["source_session"] == "session:event"
    assert row.metadata["content_hash"]
    assert row.metadata["entities"]["dates"] == ["2026-05-10"]
    assert row.metadata["entities"]["emails"] == ["ops@example.com"]

    retrieved = asyncio.run(store.retrieve("launch meeting", method="rag", limit=1))
    assert retrieved["hits"]
    assert retrieved["hits"][0]["memory_type"] == "event"
    assert retrieved["hits"][0]["happened_at"] == "2026-05-10T09:30:00+00:00"


def test_memory_default_decay_rate_varies_by_memory_type(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    profile = store.add("I prefer concise answers", source="session:profile", memory_type="profile")
    knowledge = store.add("Project alpha documentation reference", source="session:knowledge", memory_type="knowledge")
    future_event = store.add(
        "Launch deadline on 2026-05-10",
        source="session:event",
        memory_type="event",
        happened_at="2026-05-10T00:00:00+00:00",
    )

    assert profile.decay_rate < knowledge.decay_rate
    assert future_event.decay_rate < knowledge.decay_rate
    assert future_event.decay_rate <= 0.06


def test_memory_consolidate_infers_profile_type_for_preferences(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    row = store.consolidate(
        [
            {"role": "user", "content": "remember that I prefer concise answers"},
            {"role": "assistant", "content": "noted preference stored"},
        ],
        source="session:profile",
    )

    assert row is not None
    assert row.memory_type == "profile"
    curated_rows = store.curated()
    assert curated_rows
    assert any(item.memory_type == "profile" for item in curated_rows)


def test_memory_search_and_retrieve_support_reasoning_layer_and_min_confidence_filters(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        await store.memorize(text="project alpha baseline facts", source="session:a", reasoning_layer="fact", confidence=0.95)
        await store.memorize(
            text="project alpha might slip by one day",
            source="session:b",
            reasoning_layer="hypothesis",
            confidence=0.55,
        )
        await store.memorize(
            text="project alpha decision: keep friday release",
            source="session:c",
            reasoning_layer="decision",
            confidence=0.88,
        )

        hypothesis_only = store.search("project alpha", limit=5, reasoning_layers=["hypothesis"])
        assert hypothesis_only
        assert all(row.reasoning_layer == "hypothesis" for row in hypothesis_only)

        high_confidence = store.search("project alpha", limit=5, min_confidence=0.9)
        assert high_confidence
        assert all(float(row.confidence) >= 0.9 for row in high_confidence)

        retrieved = await store.retrieve(
            "project alpha",
            method="rag",
            limit=5,
            reasoning_layers=["decision"],
            min_confidence=0.8,
        )
        assert retrieved["hits"]
        assert all(hit["reasoning_layer"] == "decision" for hit in retrieved["hits"])
        assert all(float(hit["confidence"]) >= 0.8 for hit in retrieved["hits"])

    asyncio.run(_scenario())


def test_memory_search_decay_penalty_demotes_stale_high_decay_record_on_tie(tmp_path: Path, monkeypatch) -> None:
    class _FakeBM25:
        def __init__(self, _corpus: object) -> None:
            pass

        def get_scores(self, _query_tokens: object) -> list[float]:
            return [0.0, 0.0]

    monkeypatch.setattr("clawlite.core.memory.BM25Okapi", _FakeBM25)

    store = MemoryStore(tmp_path / "memory.jsonl")
    old_stamp = (datetime.now(timezone.utc) - timedelta(days=140)).isoformat()
    rows = [
        {
            "id": "high-decay",
            "text": "project alpha notes",
            "source": "session:a",
            "created_at": old_stamp,
            "decay_rate": 0.22,
            "metadata": {"content_hash": "decay-a", "scope_key": "user:default"},
        },
        {
            "id": "low-decay",
            "text": "project alpha notes",
            "source": "session:b",
            "created_at": old_stamp,
            "decay_rate": 0.01,
            "metadata": {"content_hash": "decay-b", "scope_key": "user:default"},
        },
    ]
    store.history_path.write_text("\n".join(json.dumps(item) for item in rows) + "\n", encoding="utf-8")

    found = store.search("project alpha", limit=2)
    assert found
    assert found[0].id == "low-decay"


def test_memory_analysis_stats_include_reasoning_layer_distribution_and_confidence_summary(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    store.add("fact row", source="session:a", reasoning_layer="fact", confidence=0.95)
    store.add("hypothesis row", source="session:b", reasoning_layer="hypothesis", confidence=0.55)
    store.add("decision row", source="session:c", reasoning_layer="decision", confidence=0.82)

    stats = store.analysis_stats()

    assert "reasoning_layers" in stats
    assert stats["reasoning_layers"]["fact"] >= 1
    assert stats["reasoning_layers"]["hypothesis"] >= 1
    assert stats["reasoning_layers"]["decision"] >= 1
    assert "confidence" in stats
    assert stats["confidence"]["count"] >= 3
    assert stats["confidence"]["maximum"] >= stats["confidence"]["minimum"]
    buckets = stats["confidence"]["buckets"]
    assert sum(int(value) for value in buckets.values()) >= 3


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
        assert "progressive" in rag["metadata"]
        assert rag["metadata"]["progressive"]["stages"][0]["stage"] == "category"

        async def _broken_completion(**kwargs):
            del kwargs
            raise RuntimeError("llm unavailable")

        monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(acompletion=_broken_completion))
        llm = await store.retrieve("project alpha", method="llm", limit=3)
        assert llm["method"] == "llm"
        assert llm["hits"]
        assert llm["metadata"]["fallback_to_rag"] is True

    asyncio.run(_scenario())


def test_memory_retrieve_progressive_surfaces_category_stage_metadata(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl", memory_auto_categorize=True)
        store.add("product launch deadline scheduled for 2026-05-10", source="session:event")
        store.add("prefiro respostas curtas para resumos", source="session:pref")

        retrieved = await store.retrieve("deadline 2026-05-10", method="rag", limit=2)

        assert retrieved["rewritten_query"]
        assert retrieved["category_hits"]
        assert retrieved["category_hits"][0]["category"] == "events"
        progressive = retrieved["metadata"]["progressive"]
        assert progressive["selected_categories"][0] == "events"
        assert progressive["item_sufficiency"]["sufficient"] is True
        assert [stage["stage"] for stage in progressive["stages"][:2]] == ["category", "item"]

    asyncio.run(_scenario())


def test_memory_retrieve_progressive_loads_resource_hits_for_partial_item_coverage(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        store.add(
            "release checklist",
            raw_resource_text="release checklist rollback owner Alice and deployment channel ops",
            source="session:resource",
        )

        retrieved = await store.retrieve("release checklist alice", method="rag", limit=3)

        assert retrieved["hits"]
        assert retrieved["resource_hits"]
        assert "alice" in str(retrieved["resource_hits"][0]["text"]).lower()
        progressive = retrieved["metadata"]["progressive"]
        assert progressive["item_sufficiency"]["sufficient"] is False
        assert progressive["resource_sufficiency"]["sufficient"] is True

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


def test_memory_ephemeral_ttl_cleanup_prunes_user_and_shared_scopes(tmp_path: Path, monkeypatch) -> None:
    def _rewrite_record_created_at(path: Path, record_id: str, created_at: str) -> None:
        lines: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw:
                continue
            payload = json.loads(raw)
            if payload.get("id") == record_id:
                payload["created_at"] = created_at
            lines.append(json.dumps(payload, ensure_ascii=False))
        path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")

    async def _scenario() -> None:
        monkeypatch.setattr(MemoryStore, "_generate_embedding", lambda self, text: [float(len(text)), 1.0])
        store = MemoryStore(tmp_path / "memory.jsonl", semantic_enabled=True)
        old_stamp = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()

        user_row = store.add("old scoped user context", source="session:user", user_id="user-a")
        shared_row = store.add("old shared team context", source="session:shared", shared=True)
        fresh_row = store.add("fresh scoped user context", source="session:user", user_id="user-a")

        user_scope = store._scope_paths(user_id="user-a", shared=False)
        shared_scope = store._scope_paths(shared=True)

        _rewrite_record_created_at(store.history_path, user_row.id, old_stamp)
        _rewrite_record_created_at(store.history_path, shared_row.id, old_stamp)
        _rewrite_record_created_at(user_scope["history"], user_row.id, old_stamp)
        _rewrite_record_created_at(shared_scope["history"], shared_row.id, old_stamp)

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
        store.set_shared_opt_in("user-a", True)

        await store.memorize(text="trigger scoped cleanup", source="session:ttl", user_id="user-a")

        global_ids = {row.id for row in store.all()}
        user_scope_ids = {row.id for row in store._read_history_records_from(user_scope["history"])}
        shared_scope_ids = {row.id for row in store._read_history_records_from(shared_scope["history"])}
        assert user_row.id not in global_ids
        assert shared_row.id not in global_ids
        assert user_row.id not in user_scope_ids
        assert shared_row.id not in shared_scope_ids
        assert fresh_row.id in user_scope_ids

        user_hits = await store.retrieve("old scoped user", user_id="user-a", limit=5)
        shared_hits = await store.retrieve("old shared team", user_id="user-a", include_shared=True, limit=5)
        assert all(str(item["id"]) != user_row.id for item in user_hits["hits"])
        assert all(str(item["id"]) != shared_row.id for item in shared_hits["hits"])

        user_item_payload = json.loads((user_scope["items"] / "context.json").read_text(encoding="utf-8"))
        shared_item_payload = json.loads((shared_scope["items"] / "context.json").read_text(encoding="utf-8"))
        user_item_ids = {str(item.get("id", "")) for item in user_item_payload.get("items", []) if isinstance(item, dict)}
        shared_item_ids = {str(item.get("id", "")) for item in shared_item_payload.get("items", []) if isinstance(item, dict)}
        assert user_row.id not in user_item_ids
        assert shared_row.id not in shared_item_ids
        assert fresh_row.id in user_item_ids

        embedding_ids = {json.loads(line)["id"] for line in store.embeddings_path.read_text(encoding="utf-8").splitlines() if line.strip()}
        assert user_row.id not in embedding_ids
        assert shared_row.id not in embedding_ids
        assert fresh_row.id in embedding_ids
        assert store.diagnostics()["privacy_ttl_deleted"] >= 2

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


def test_memory_profile_prompt_hint_is_empty_for_default_profile(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    assert store.profile_prompt_hint() == ""


def test_memory_profile_prompt_hint_summarizes_learned_preferences(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        await store.memorize(text="prefiro respostas curtas e moro em Sao Paulo", source="session:profile")
        await store.memorize(text="gosto de viagens internacionais", source="session:profile")
        await store.memorize(text="planejando viagens longas em 2026", source="session:profile")

        hint = store.profile_prompt_hint()
        assert "[User Profile]" in hint
        assert "Preferred response length: curto" in hint
        assert "Timezone: America/Sao_Paulo" in hint
        assert "Recurring interests: viagens" in hint

    asyncio.run(_scenario())


def test_memory_profile_tracks_upcoming_events_from_event_memory(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    store.add(
        "Product launch deadline",
        source="session:event",
        memory_type="event",
        happened_at="2026-05-10T09:30:00+00:00",
    )

    profile = json.loads(store.profile_path.read_text(encoding="utf-8"))
    upcoming = profile["upcoming_events"]
    assert upcoming
    assert upcoming[0]["title"] == "Product launch deadline"
    assert upcoming[0]["happened_at"] == "2026-05-10T09:30:00+00:00"

    hint = store.profile_prompt_hint()
    assert "Upcoming events:" in hint
    assert "2026-05-10 Product launch deadline" in hint


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


def test_memory_quality_state_reasoning_layers_report_structure_and_recommendations(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")

    report = store.update_quality_state(
        retrieval_metrics={"attempts": 10, "hits": 8, "rewrites": 1},
        turn_stability_metrics={"successes": 9, "errors": 1},
        semantic_metrics={"enabled": True, "coverage_ratio": 0.75},
        reasoning_layer_metrics={
            "reasoning_layers": {"facts": 8, "hypothesis": 1, "decision": 0, "outcomes": 1},
            "confidence": {"avg": 0.42, "min": 0.2, "max": 0.7},
            "totalRecords": 10,
        },
        sampled_at="2026-03-05T12:00:00+00:00",
    )

    reasoning = report["reasoning_layers"]
    assert reasoning["total_records"] == 10
    assert set(reasoning["distribution"].keys()) == {"fact", "hypothesis", "decision", "outcome"}
    assert reasoning["distribution"]["fact"]["count"] == 8
    assert reasoning["distribution"]["decision"]["count"] == 0
    assert reasoning["distribution"]["fact"]["ratio"] == 0.8
    assert reasoning["weakest_layer"] == "decision"
    assert reasoning["weakest_ratio"] == 0.0
    assert 0.0 <= reasoning["balance_score"] <= 1.0
    assert reasoning["confidence"] == {"average": 0.42, "minimum": 0.2, "maximum": 0.7}

    recommendations = report["recommendations"]
    assert any("decision" in item.lower() for item in recommendations)
    assert any("confidence" in item.lower() for item in recommendations)


def test_memory_quality_state_legacy_call_without_reasoning_metrics_keeps_score_and_defaults(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")

    report = store.update_quality_state(
        retrieval_metrics={"attempts": 10, "hits": 8, "rewrites": 1},
        turn_stability_metrics={"successes": 9, "errors": 1},
        semantic_metrics={"enabled": True, "coverage_ratio": 0.75},
        sampled_at="2026-03-05T12:30:00+00:00",
    )

    assert report["score"] == 82
    reasoning = report["reasoning_layers"]
    assert reasoning == {
        "total_records": 0,
        "distribution": {
            "fact": {"count": 0, "ratio": 0.0},
            "hypothesis": {"count": 0, "ratio": 0.0},
            "decision": {"count": 0, "ratio": 0.0},
            "outcome": {"count": 0, "ratio": 0.0},
        },
        "balance_score": 0.0,
        "weakest_layer": "fact",
        "weakest_ratio": 0.0,
        "confidence": {"average": 0.0, "minimum": 0.0, "maximum": 0.0},
    }


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
