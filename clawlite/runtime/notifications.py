from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Iterator

from clawlite.runtime import multiagent

PRIORITY_RANK = {"low": 1, "normal": 2, "high": 3}


@dataclass
class NotificationRow:
    id: int
    channel: str
    chat_id: str
    thread_id: str
    label: str
    event: str
    priority: str
    priority_rank: int
    dedupe_key: str
    message: str
    metadata: str
    created_at: float


def _now() -> float:
    return time.time()


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    db_path = multiagent.current_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=3000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_notifications_db() -> None:
    multiagent.init_db()
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              channel TEXT NOT NULL DEFAULT '',
              chat_id TEXT NOT NULL DEFAULT '',
              thread_id TEXT NOT NULL DEFAULT '',
              label TEXT NOT NULL DEFAULT '',
              event TEXT NOT NULL,
              priority TEXT NOT NULL,
              priority_rank INTEGER NOT NULL,
              dedupe_key TEXT NOT NULL,
              message TEXT NOT NULL,
              metadata TEXT NOT NULL DEFAULT '{}',
              created_at REAL NOT NULL
            )
            """
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_notifications_dedupe_time ON notifications (dedupe_key, created_at DESC)"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_notifications_priority_time ON notifications (priority_rank DESC, created_at DESC)"
        )


def normalize_priority(priority: str) -> str:
    value = (priority or "").strip().lower()
    if value in PRIORITY_RANK:
        return value
    return "normal"


def infer_priority(event: str) -> str:
    value = (event or "").strip().lower()
    if any(token in value for token in ["failed", "error", "provider_failure"]):
        return "high"
    if any(token in value for token in ["fallback", "offline"]):
        return "normal"
    if any(token in value for token in ["ok", "success", "enqueued"]):
        return "low"
    return "normal"


def _default_dedupe_key(
    event: str,
    message: str,
    channel: str,
    chat_id: str,
    thread_id: str,
    label: str,
) -> str:
    raw = "|".join([event.strip().lower(), channel, chat_id, thread_id, label, message.strip().lower()])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_notification(
    *,
    event: str,
    message: str,
    priority: str | None = None,
    dedupe_key: str | None = None,
    dedupe_window_seconds: int = 300,
    channel: str = "",
    chat_id: str = "",
    thread_id: str = "",
    label: str = "",
    metadata: dict[str, Any] | None = None,
) -> tuple[bool, int | None]:
    init_notifications_db()
    chosen_priority = normalize_priority(priority or infer_priority(event))
    rank = PRIORITY_RANK[chosen_priority]
    key = (dedupe_key or _default_dedupe_key(event, message, channel, chat_id, thread_id, label)).strip()
    meta_json = json.dumps(metadata or {}, ensure_ascii=False)
    now_ts = _now()
    cutoff = now_ts - max(int(dedupe_window_seconds), 0)

    with _conn() as c:
        dup = c.execute(
            "SELECT id FROM notifications WHERE dedupe_key=? AND created_at >= ? ORDER BY id DESC LIMIT 1",
            (key, cutoff),
        ).fetchone()
        if dup:
            return False, None

        c.execute(
            """
            INSERT INTO notifications
            (channel, chat_id, thread_id, label, event, priority, priority_rank, dedupe_key, message, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                channel,
                chat_id,
                thread_id,
                label,
                event,
                chosen_priority,
                rank,
                key,
                message,
                meta_json,
                now_ts,
            ),
        )
        row = c.execute("SELECT last_insert_rowid() AS id").fetchone()
    return True, int(row["id"])


def list_notifications(limit: int = 20, min_priority: str = "low") -> list[NotificationRow]:
    init_notifications_db()
    threshold = PRIORITY_RANK[normalize_priority(min_priority)]
    with _conn() as c:
        rows = c.execute(
            """
            SELECT * FROM notifications
            WHERE priority_rank >= ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (threshold, int(limit)),
        ).fetchall()
    return [NotificationRow(**dict(row)) for row in rows]


def format_notifications_table(rows: list[NotificationRow]) -> str:
    if not rows:
        return "(sem notificações)"
    lines = ["id | prioridade | evento | canal/chat/thread/label | mensagem"]
    for row in rows:
        context = f"{row.channel or '-'}:{row.chat_id or '-'}:{row.thread_id or '-'}:{row.label or '-'}"
        lines.append(f"{row.id} | {row.priority} | {row.event} | {context} | {row.message}")
    return "\n".join(lines)
