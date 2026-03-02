from __future__ import annotations

from pathlib import Path

from clawlite.session.store import SessionStore


def test_session_store_persists_jsonl(tmp_path: Path) -> None:
    store = SessionStore(root=tmp_path / "sessions")
    store.append("telegram:1", "user", "oi")
    store.append("telegram:1", "assistant", "ola")
    rows = store.read("telegram:1", limit=10)
    assert rows[-1]["content"] == "ola"
    assert store.list_sessions() == ["telegram:1"]
