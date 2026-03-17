from __future__ import annotations

import json
import os
import time
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
    target = store._path("telegram:3")
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


def test_session_store_compacts_to_keep_last_n_messages(tmp_path: Path) -> None:
    store = SessionStore(root=tmp_path / "sessions", max_messages_per_session=3)
    for idx in range(6):
        store.append("telegram:4", "user", f"m{idx}")

    rows = store.read("telegram:4", limit=10)
    assert [row["content"] for row in rows] == ["m3", "m4", "m5"]


def test_session_store_compaction_preserves_order_and_latest_messages(tmp_path: Path) -> None:
    store = SessionStore(root=tmp_path / "sessions", max_messages_per_session=4)
    payloads = [
        ("user", "first"),
        ("assistant", "second"),
        ("user", "third"),
        ("assistant", "fourth"),
        ("user", "fifth"),
        ("assistant", "sixth"),
    ]
    for role, content in payloads:
        store.append("telegram:5", role, content)

    rows = store.read("telegram:5", limit=10)
    assert [(row["role"], row["content"]) for row in rows] == payloads[-4:]


def test_session_store_compaction_updates_diagnostics_counters(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = SessionStore(root=tmp_path / "sessions", max_messages_per_session=2)
    store.append("telegram:6", "user", "one")
    store.append("telegram:6", "user", "two")
    store.append("telegram:6", "user", "three")

    diag = store.diagnostics()
    assert diag["compaction_runs"] == 3
    assert diag["compaction_trimmed_lines"] == 1
    assert diag["compaction_failures"] == 0

    target = store._path("telegram:6")

    original_read_text = Path.read_text

    def _boom(self: Path, *args, **kwargs) -> str:
        if self == target:
            raise OSError("compaction exploded")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _boom)
    store.append("telegram:6", "user", "four")
    diag_after = store.diagnostics()
    assert diag_after["append_success"] == 4
    assert diag_after["compaction_failures"] == 1
    assert target.exists()


def test_session_store_batches_compaction_for_larger_limits(tmp_path: Path) -> None:
    store = SessionStore(root=tmp_path / "sessions", max_messages_per_session=100)
    for idx in range(130):
        store.append("telegram:7", "user", f"m{idx}")

    diag = store.diagnostics()
    assert diag["append_success"] == 130
    assert diag["compaction_runs"] < 130
    assert diag["compaction_runs"] <= 5
    assert diag["compaction_trimmed_lines"] >= 10

    rows = store.read("telegram:7", limit=200)
    assert len(rows) == 100
    assert rows[0]["content"] == "m30"
    assert rows[-1]["content"] == "m129"


def test_session_store_prune_expired_deletes_stale_session_files(tmp_path: Path) -> None:
    store = SessionStore(root=tmp_path / "sessions", session_retention_ttl_s=60)
    store.append("telegram:stale", "user", "old")
    store.append("telegram:fresh", "user", "new")

    stale_path = store._path("telegram:stale")
    fresh_path = store._path("telegram:fresh")
    now = time.time()
    os.utime(stale_path, (now - 3600, now - 3600))

    deleted = store.prune_expired(now=now)

    assert deleted == 1
    assert stale_path.exists() is False
    assert fresh_path.exists() is True
    diag = store.diagnostics()
    assert diag["ttl_prune_runs"] == 1
    assert diag["ttl_prune_deleted_sessions"] == 1


def test_session_store_prune_expired_is_noop_when_ttl_disabled(tmp_path: Path) -> None:
    store = SessionStore(root=tmp_path / "sessions", session_retention_ttl_s=None)
    store.append("telegram:1", "user", "hello")

    deleted = store.prune_expired(now=time.time())

    assert deleted == 0
    assert store.list_sessions() == ["telegram:1"]
    diag = store.diagnostics()
    assert diag["ttl_prune_runs"] == 0
