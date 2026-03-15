from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from clawlite.bus.events import InboundEvent, OutboundEvent

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bus_inbound (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    correlation_id TEXT NOT NULL,
    channel     TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    text        TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    acked_at    TEXT
);

CREATE TABLE IF NOT EXISTS bus_outbound (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    correlation_id TEXT NOT NULL,
    channel     TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    target      TEXT NOT NULL,
    text        TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}',
    attempt     INTEGER NOT NULL DEFAULT 1,
    max_attempts INTEGER NOT NULL DEFAULT 1,
    retryable   INTEGER NOT NULL DEFAULT 1,
    dead_lettered INTEGER NOT NULL DEFAULT 0,
    dead_letter_reason TEXT NOT NULL DEFAULT '',
    last_error  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    acked_at    TEXT
);
"""


class BusJournal:
    """Optional SQLite persistence layer for the message bus.

    When enabled, every published event is appended to the journal.
    On startup, unacked events (without ``acked_at``) are replayed.
    On successful consumption the event is acked (``acked_at`` filled in).

    Journal write failures are logged and swallowed — the bus continues
    in degraded (no-persistence) mode rather than crashing.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        logger.info("BusJournal: opened %s", self._path)

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    # ------------------------------------------------------------------
    # Inbound
    # ------------------------------------------------------------------

    def append_inbound(self, event: InboundEvent) -> int | None:
        if self._conn is None:
            return None
        try:
            cur = self._conn.execute(
                """INSERT INTO bus_inbound
                   (correlation_id, channel, session_id, user_id, text,
                    metadata, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    event.correlation_id,
                    event.channel,
                    event.session_id,
                    event.user_id,
                    event.text,
                    json.dumps(event.metadata),
                    event.created_at,
                ),
            )
            self._conn.commit()
            return cur.lastrowid
        except Exception as exc:
            logger.error("BusJournal.append_inbound failed: %s", exc)
            return None

    def ack_inbound(self, row_id: int) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(
                "UPDATE bus_inbound SET acked_at=? WHERE id=?",
                (_utc_now(), row_id),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("BusJournal.ack_inbound failed: %s", exc)

    def unacked_inbound(self) -> list[tuple[int, InboundEvent]]:
        if self._conn is None:
            return []
        try:
            rows = self._conn.execute(
                "SELECT * FROM bus_inbound WHERE acked_at IS NULL ORDER BY id ASC"
            ).fetchall()
            return [(row["id"], _row_to_inbound(row)) for row in rows]
        except Exception as exc:
            logger.error("BusJournal.unacked_inbound failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    def append_outbound(self, event: OutboundEvent) -> int | None:
        if self._conn is None:
            return None
        try:
            cur = self._conn.execute(
                """INSERT INTO bus_outbound
                   (correlation_id, channel, session_id, target, text,
                    metadata, attempt, max_attempts, retryable,
                    dead_lettered, dead_letter_reason, last_error, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event.correlation_id,
                    event.channel,
                    event.session_id,
                    event.target,
                    event.text,
                    json.dumps(event.metadata),
                    event.attempt,
                    event.max_attempts,
                    int(event.retryable),
                    int(event.dead_lettered),
                    event.dead_letter_reason,
                    event.last_error,
                    event.created_at,
                ),
            )
            self._conn.commit()
            return cur.lastrowid
        except Exception as exc:
            logger.error("BusJournal.append_outbound failed: %s", exc)
            return None

    def ack_outbound(self, row_id: int) -> None:
        if self._conn is None:
            return
        try:
            self._conn.execute(
                "UPDATE bus_outbound SET acked_at=? WHERE id=?",
                (_utc_now(), row_id),
            )
            self._conn.commit()
        except Exception as exc:
            logger.error("BusJournal.ack_outbound failed: %s", exc)

    def unacked_outbound(self) -> list[tuple[int, OutboundEvent]]:
        if self._conn is None:
            return []
        try:
            rows = self._conn.execute(
                "SELECT * FROM bus_outbound WHERE acked_at IS NULL ORDER BY id ASC"
            ).fetchall()
            return [(row["id"], _row_to_outbound(row)) for row in rows]
        except Exception as exc:
            logger.error("BusJournal.unacked_outbound failed: %s", exc)
            return []


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_inbound(row: sqlite3.Row) -> InboundEvent:
    metadata: dict[str, Any] = {}
    try:
        metadata = json.loads(row["metadata"] or "{}")
    except Exception:
        pass
    return InboundEvent(
        channel=row["channel"],
        session_id=row["session_id"],
        user_id=row["user_id"],
        text=row["text"],
        metadata=metadata,
        created_at=row["created_at"],
        correlation_id=row["correlation_id"],
    )


def _row_to_outbound(row: sqlite3.Row) -> OutboundEvent:
    metadata: dict[str, Any] = {}
    try:
        metadata = json.loads(row["metadata"] or "{}")
    except Exception:
        pass
    return OutboundEvent(
        channel=row["channel"],
        session_id=row["session_id"],
        target=row["target"],
        text=row["text"],
        metadata=metadata,
        attempt=int(row["attempt"] or 1),
        max_attempts=int(row["max_attempts"] or 1),
        retryable=bool(row["retryable"]),
        dead_lettered=bool(row["dead_lettered"]),
        dead_letter_reason=str(row["dead_letter_reason"] or ""),
        last_error=str(row["last_error"] or ""),
        created_at=row["created_at"],
        correlation_id=row["correlation_id"],
    )
