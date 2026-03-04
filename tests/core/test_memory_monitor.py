from __future__ import annotations

import asyncio
import json
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
