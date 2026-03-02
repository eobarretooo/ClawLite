from __future__ import annotations

from pathlib import Path

from clawlite.core.memory import MemoryStore


def test_memory_store_add_and_search(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    store.add("I like python and async systems", source="user")
    store.add("Weather in Sao Paulo is warm", source="user")

    found = store.search("python", limit=3)
    assert found
    assert "python" in found[0].text.lower()


def test_memory_consolidate(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    row = store.consolidate([
        {"role": "user", "content": "remember my timezone"},
        {"role": "assistant", "content": "ok timezone set"},
    ])
    assert row is not None
    assert "timezone" in row.text


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
