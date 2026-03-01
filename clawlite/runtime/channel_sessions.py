from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import threading
import time
from typing import Any


@dataclass
class ChannelSession:
    instance_key: str
    channel: str
    session_id: str
    chat_id: str = ""
    thread_id: str = ""
    metadata: dict[str, Any] | None = None
    first_seen_at: float = 0.0
    last_seen_at: float = 0.0
    message_count: int = 0


class ChannelSessionManager:
    """Gerencia sessões por canal/instância para runtime do gateway."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_instance: dict[str, ChannelSession] = {}
        self._tasks_by_session: dict[str, set[asyncio.Task[Any]]] = {}

    def bind(
        self,
        *,
        instance_key: str,
        channel: str,
        session_id: str,
        chat_id: str = "",
        thread_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ChannelSession:
        now = time.time()
        sid = str(session_id or "").strip()
        if not sid:
            raise ValueError("session_id é obrigatório")
        key = str(instance_key or "").strip() or str(channel or "").strip().lower()
        ch = str(channel or "").strip().lower()
        with self._lock:
            current = self._by_instance.get(key)
            if current and current.session_id == sid:
                current.last_seen_at = now
                current.message_count += 1
                if metadata:
                    base = dict(current.metadata or {})
                    base.update(metadata)
                    current.metadata = base
                if chat_id:
                    current.chat_id = str(chat_id)
                if thread_id:
                    current.thread_id = str(thread_id)
                return current

            row = ChannelSession(
                instance_key=key,
                channel=ch,
                session_id=sid,
                chat_id=str(chat_id or ""),
                thread_id=str(thread_id or ""),
                metadata=(dict(metadata) if metadata else {}),
                first_seen_at=now,
                last_seen_at=now,
                message_count=1,
            )
            self._by_instance[key] = row
            return row

    def last_session_id(self, instance_key: str) -> str:
        key = str(instance_key or "").strip()
        if not key:
            return ""
        with self._lock:
            row = self._by_instance.get(key)
            return row.session_id if row else ""

    def get(self, instance_key: str) -> ChannelSession | None:
        key = str(instance_key or "").strip()
        if not key:
            return None
        with self._lock:
            row = self._by_instance.get(key)
            if row is None:
                return None
            return ChannelSession(**asdict(row))

    def list_by_channel(self, channel: str) -> list[ChannelSession]:
        ch = str(channel or "").strip().lower()
        with self._lock:
            rows = [ChannelSession(**asdict(row)) for row in self._by_instance.values() if row.channel == ch]
        rows.sort(key=lambda row: row.last_seen_at, reverse=True)
        return rows

    def drop_instance(self, instance_key: str) -> None:
        key = str(instance_key or "").strip()
        if not key:
            return
        with self._lock:
            self._by_instance.pop(key, None)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            rows = [asdict(row) for row in self._by_instance.values()]
        return {"instances": len(rows), "sessions": rows}

    def register_task(self, session_id: str, task: asyncio.Task[Any]) -> None:
        sid = str(session_id or "").strip()
        if not sid:
            return
        with self._lock:
            bucket = self._tasks_by_session.setdefault(sid, set())
            bucket.add(task)

    def unregister_task(self, session_id: str, task: asyncio.Task[Any]) -> None:
        sid = str(session_id or "").strip()
        if not sid:
            return
        with self._lock:
            bucket = self._tasks_by_session.get(sid)
            if not bucket:
                return
            bucket.discard(task)
            if not bucket:
                self._tasks_by_session.pop(sid, None)

    def active_task_count(self, session_id: str) -> int:
        sid = str(session_id or "").strip()
        if not sid:
            return 0
        with self._lock:
            bucket = self._tasks_by_session.get(sid, set())
            return sum(1 for task in bucket if not task.done())

    def cancel_session_tasks(self, session_id: str) -> int:
        sid = str(session_id or "").strip()
        if not sid:
            return 0
        with self._lock:
            bucket = list(self._tasks_by_session.get(sid, set()))

        cancelled = 0
        for task in bucket:
            if task.done():
                continue
            task.cancel()
            cancelled += 1
        return cancelled
