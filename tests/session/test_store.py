from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawlite.session.store import SessionStore


def test_session_store_persists_jsonl(tmp_path: Path) -> None:
    store = SessionStore(root=tmp_path / "sessions")
    store.append("telegram:1", "user", "oi")
    store.append("telegram:1", "assistant", "ola")
    rows = store.read("telegram:1", limit=10)
    assert rows[-1]["content"] == "ola"
    assert store.list_sessions() == ["telegram:1"]


def test_session_store_append_retries_once_on_transient_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = SessionStore(root=tmp_path / "sessions")
    attempts = {"count": 0}
    original_append_once = store._append_once

    def _flaky_append_once(path, payload):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise OSError("temporary disk error")
        original_append_once(path, payload)

    monkeypatch.setattr(store, "_append_once", _flaky_append_once)
    store.append("telegram:2", "user", "hello")

    rows = store.read("telegram:2", limit=10)
    assert rows == [{"role": "user", "content": "hello"}]

    diag = store.diagnostics()
    assert diag["append_attempts"] == 2
    assert diag["append_retries"] == 1
    assert diag["append_failures"] == 0
    assert diag["append_success"] == 1


def test_session_store_read_recovers_from_malformed_json_and_repairs_file(tmp_path: Path) -> None:
    store = SessionStore(root=tmp_path / "sessions")
    target = tmp_path / "sessions" / "telegram:3.jsonl"
    valid1 = {"session_id": "telegram:3", "role": "user", "content": "hello", "ts": "t1", "metadata": {}}
    valid2 = {"session_id": "telegram:3", "role": "assistant", "content": "world", "ts": "t2", "metadata": {}}
    target.write_text(
        "\n".join(
            [
                json.dumps(valid1),
                "{not-valid-json",
                json.dumps(valid2),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rows = store.read("telegram:3", limit=10)
    assert rows == [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "world"}]

    repaired_lines = target.read_text(encoding="utf-8").splitlines()
    assert len(repaired_lines) == 2
    assert all("not-valid-json" not in line for line in repaired_lines)

    diag = store.diagnostics()
    assert diag["read_corrupt_lines"] == 1
    assert diag["read_repaired_files"] == 1
