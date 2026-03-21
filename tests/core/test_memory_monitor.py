from __future__ import annotations

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from clawlite.core.memory import MemoryStore
from clawlite.core.memory_monitor import MemoryMonitor


def _seed_history(store: MemoryStore, rows: list[dict[str, str]]) -> None:
    store.history_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_memory_monitor_scan_triggers_required_coverage(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        now = datetime.now(timezone.utc)
        upcoming = (now + timedelta(days=3)).date().isoformat()
        stale = (now - timedelta(days=3)).isoformat()
        recent = (now - timedelta(hours=8)).isoformat()

        rows = [
            {
                "id": "evt1",
                "text": f"birthday da Ana em {upcoming}",
                "source": "session:telegram:ana_chat",
                "created_at": recent,
            },
            {
                "id": "task1",
                "text": "todo: revisar proposta pendente",
                "source": "session:cli:tasks",
                "created_at": stale,
            },
            {
                "id": "r1",
                "text": "python migration checklist",
                "source": "session:topic",
                "created_at": recent,
            },
            {
                "id": "r2",
                "text": "python migration docs",
                "source": "session:topic",
                "created_at": recent,
            },
            {
                "id": "r3",
                "text": "python migration tests",
                "source": "session:topic",
                "created_at": recent,
            },
            {
                "id": "r4",
                "text": "python migration rollout",
                "source": "session:topic",
                "created_at": recent,
            },
            {
                "id": "b1",
                "text": "birthday da Maria 01-15",
                "source": "session:birthday",
                "created_at": recent,
            },
            {
                "id": "b2",
                "text": "aniversario do Joao 01-15",
                "source": "session:birthday",
                "created_at": recent,
            },
        ]
        _seed_history(store, rows)

        monitor = MemoryMonitor(store)
        suggestions = await monitor.scan()
        triggers = {item.trigger for item in suggestions}

        assert "upcoming_event" in triggers
        assert "pending_task" in triggers
        assert "pattern" in triggers
        assert all(isinstance(item.priority, float) for item in suggestions)
        assert all(0.0 <= item.priority <= 1.0 for item in suggestions)

        upcoming_items = [item for item in suggestions if item.trigger == "upcoming_event"]
        assert upcoming_items
        assert upcoming_items[0].channel == "telegram"
        assert upcoming_items[0].target == "ana_chat"
        assert "day(s)" in upcoming_items[0].text

    asyncio.run(_scenario())


def test_memory_monitor_pending_persistence_and_mark_delivered(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        now = datetime.now(timezone.utc)
        rows = [
            {
                "id": "evt2",
                "text": f"travel para Recife em {(now + timedelta(days=2)).date().isoformat()}",
                "source": "session:event",
                "created_at": now.isoformat(),
            }
        ]
        _seed_history(store, rows)
        monitor = MemoryMonitor(store)

        pending = await monitor.scan()
        assert pending
        first_id = pending[0].suggestion_id
        assert monitor.mark_delivered(first_id) is True

        remaining_ids = {item.suggestion_id for item in monitor.pending()}
        assert first_id not in remaining_ids

        payload = json.loads(monitor.suggestions_path.read_text(encoding="utf-8"))
        delivered = [row for row in payload if row.get("id") == first_id]
        assert delivered
        assert delivered[0]["status"] == "delivered"

    asyncio.run(_scenario())


def test_memory_monitor_scan_sync_persists_pending_without_asyncio_threads(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    now = datetime.now(timezone.utc)
    _seed_history(
        store,
        [
            {
                "id": "evt-sync",
                "text": f"travel para Recife em {(now + timedelta(days=2)).date().isoformat()}",
                "source": "session:event",
                "created_at": now.isoformat(),
            }
        ],
    )

    monitor = MemoryMonitor(store)
    pending = monitor.scan_sync()

    assert pending
    payload = json.loads(monitor.suggestions_path.read_text(encoding="utf-8"))
    assert payload
    assert payload[0]["status"] == "pending"


def test_memory_monitor_dedupe_and_cooldown_controls(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        now = datetime.now(timezone.utc)
        event_date = (now + timedelta(days=2)).date().isoformat()
        _seed_history(
            store,
            [
                {
                    "id": "evt-cooldown",
                    "text": f"birthday da Ana em {event_date}",
                    "source": "session:telegram:ana_chat",
                    "created_at": now.isoformat(),
                }
            ],
        )
        monitor = MemoryMonitor(store, cooldown_seconds=3600)

        first = await monitor.scan()
        second = await monitor.scan()
        assert first
        assert second
        assert len(first) == 1
        assert len(second) == 1

        suggestion = first[0]
        assert monitor.should_deliver(suggestion, min_priority=0.7) is True
        assert monitor.mark_delivered(suggestion) is True
        assert monitor.should_deliver(suggestion, min_priority=0.7) is False

        metrics = monitor.telemetry()
        assert metrics["scans"] == 2
        assert metrics["deduped"] >= 1
        assert metrics["cooldown_skipped"] >= 1
        assert metrics["sent"] >= 1

    asyncio.run(_scenario())


def test_memory_monitor_writes_pending_atomically(tmp_path: Path, monkeypatch) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    monitor = MemoryMonitor(store)

    replace_calls: list[tuple[str, str]] = []
    real_replace = __import__("os").replace

    def _spy_replace(src: str | Path, dst: str | Path) -> None:
        replace_calls.append((str(src), str(dst)))
        real_replace(src, dst)

    monkeypatch.setattr("clawlite.core.memory_monitor.os.replace", _spy_replace)

    monitor._write_pending_payload(
        [
            {
                "id": "a1",
                "semantic_key": "k1",
                "text": "pending",
                "priority": 0.8,
                "trigger": "pattern",
                "channel": "cli",
                "target": "default",
                "status": "pending",
            }
        ]
    )

    assert replace_calls
    payload = json.loads(monitor.suggestions_path.read_text(encoding="utf-8"))
    assert payload[0]["id"] == "a1"


def test_memory_monitor_mark_delivered_read_modify_write_is_lock_safe(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.jsonl")
    monitor = MemoryMonitor(store)
    monitor._write_pending_payload(
        [
            {
                "id": "race-1",
                "semantic_key": "race-semantic",
                "text": "pending race",
                "priority": 0.8,
                "trigger": "pattern",
                "channel": "cli",
                "target": "default",
                "status": "pending",
            }
        ]
    )

    def _mark() -> bool:
        return monitor.mark_delivered("race-1")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: _mark(), range(16)))

    assert any(results)
    payload = json.loads(monitor.suggestions_path.read_text(encoding="utf-8"))
    assert len(payload) == 1
    assert payload[0]["status"] == "delivered"


def test_memory_monitor_scan_offloads_persist_and_pending_to_threads(tmp_path: Path, monkeypatch) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        now = datetime.now(timezone.utc)
        _seed_history(
            store,
            [
                {
                    "id": "evt-thread",
                    "text": f"birthday da Ana em {(now + timedelta(days=2)).date().isoformat()}",
                    "source": "session:telegram:ana_chat",
                    "created_at": now.isoformat(),
                }
            ],
        )
        monitor = MemoryMonitor(store)

        observed: dict[str, int] = {}
        loop_thread = threading.get_ident()
        original_persist = monitor._persist_pending
        original_deliverable = monitor.deliverable

        def _persist_probe(suggestions):
            observed["persist"] = threading.get_ident()
            return original_persist(suggestions)

        def _deliverable_probe():
            observed["deliverable"] = threading.get_ident()
            return original_deliverable()

        monkeypatch.setattr(monitor, "_persist_pending", _persist_probe)
        monkeypatch.setattr(monitor, "deliverable", _deliverable_probe)

        suggestions = await monitor.scan()

        assert suggestions
        assert observed["persist"] != loop_thread
        assert observed["deliverable"] != loop_thread

    asyncio.run(_scenario())


def test_memory_monitor_replays_failed_suggestions_after_backoff(tmp_path: Path) -> None:
    async def _scenario() -> None:
        store = MemoryStore(tmp_path / "memory.jsonl")
        monitor = MemoryMonitor(store, retry_backoff_seconds=0.0, max_retry_attempts=3)
        monitor._write_pending_payload(
            [
                {
                    "id": "retry-1",
                    "semantic_key": "retry-semantic",
                    "text": "Pending task with no updates for 3 day(s): revisar rollout",
                    "priority": 0.8,
                    "trigger": "pending_task",
                    "channel": "telegram",
                    "target": "chat42",
                    "status": "pending",
                    "metadata": {"record_id": "task-1"},
                }
            ]
        )

        assert monitor.mark_failed("retry-1", error="telegram unavailable") is True

        pending = monitor.pending()
        assert pending == []

        deliverable = monitor.deliverable()
        assert len(deliverable) == 1
        assert deliverable[0].metadata["_delivery_status"] == "failed"
        assert deliverable[0].metadata["_failure_count"] == 1

        replayed = await monitor.scan()
        assert len(replayed) == 1
        assert replayed[0].suggestion_id == deliverable[0].suggestion_id

    asyncio.run(_scenario())
