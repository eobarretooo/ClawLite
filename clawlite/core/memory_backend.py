from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any
from typing import Protocol


class MemoryBackend(Protocol):
    """Memory backend contract used by MemoryStore persistence layers."""

    @property
    def name(self) -> str:
        ...

    def is_supported(self) -> bool:
        ...

    def initialize(self, memory_home: str | Path) -> None:
        ...

    def upsert_layer_record(
        self,
        *,
        layer: str,
        record_id: str,
        payload: dict[str, Any],
        category: str,
        created_at: str,
        updated_at: str,
    ) -> None:
        ...

    def delete_layer_records(self, record_ids: list[str] | set[str]) -> int:
        ...

    def fetch_layer_records(self, *, layer: str, category: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        ...


@dataclass(slots=True)
class SQLiteMemoryBackend:
    db_path: str = ""
    _db_file: Path | None = field(init=False, default=None)
    _lock: threading.Lock = field(init=False)

    def __post_init__(self) -> None:
        self._db_file = Path(self.db_path).expanduser() if str(self.db_path or "").strip() else None
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "sqlite"

    def is_supported(self) -> bool:
        return True

    def initialize(self, memory_home: str | Path) -> None:
        with self._lock:
            if self._db_file is None:
                self._db_file = Path(memory_home).expanduser() / "memory-index.sqlite3"
            self._db_file.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(self._db_file)) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS layer_records (
                        layer TEXT NOT NULL,
                        record_id TEXT NOT NULL,
                        category TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (layer, record_id)
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_layer_records_layer ON layer_records(layer)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_layer_records_category ON layer_records(category)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_layer_records_updated_at ON layer_records(updated_at)")
                conn.commit()

    def upsert_layer_record(
        self,
        *,
        layer: str,
        record_id: str,
        payload: dict[str, Any],
        category: str,
        created_at: str,
        updated_at: str,
    ) -> None:
        if not str(record_id or "").strip():
            return
        if self._db_file is None:
            return
        with self._lock:
            with sqlite3.connect(str(self._db_file)) as conn:
                conn.execute(
                    """
                    INSERT INTO layer_records (layer, record_id, category, payload, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(layer, record_id) DO UPDATE SET
                        category = excluded.category,
                        payload = excluded.payload,
                        updated_at = excluded.updated_at
                    """,
                    (
                        str(layer or "item"),
                        str(record_id),
                        str(category or "context"),
                        json.dumps(payload or {}, ensure_ascii=False),
                        str(created_at or ""),
                        str(updated_at or ""),
                    ),
                )
                conn.commit()

    def delete_layer_records(self, record_ids: list[str] | set[str]) -> int:
        ids = [str(item).strip() for item in record_ids if str(item).strip()]
        if not ids:
            return 0
        if self._db_file is None:
            return 0
        placeholders = ", ".join("?" for _ in ids)
        with self._lock:
            with sqlite3.connect(str(self._db_file)) as conn:
                cursor = conn.execute(f"DELETE FROM layer_records WHERE record_id IN ({placeholders})", ids)
                conn.commit()
                return int(cursor.rowcount or 0)

    def fetch_layer_records(self, *, layer: str, category: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        bounded_limit = max(1, int(limit or 1))
        query = (
            "SELECT layer, record_id, category, payload, created_at, updated_at "
            "FROM layer_records WHERE layer = ?"
        )
        params: list[Any] = [str(layer or "item")]
        if category is not None:
            query += " AND category = ?"
            params.append(str(category or "context"))
        query += " ORDER BY updated_at DESC, record_id DESC LIMIT ?"
        params.append(bounded_limit)

        if self._db_file is None:
            return []

        with self._lock:
            with sqlite3.connect(str(self._db_file)) as conn:
                rows = conn.execute(query, params).fetchall()

        out: list[dict[str, Any]] = []
        for row_layer, row_id, row_category, row_payload, created_at, updated_at in rows:
            payload: dict[str, Any] = {}
            try:
                parsed = json.loads(str(row_payload or "{}"))
                if isinstance(parsed, dict):
                    payload = parsed
            except Exception:
                payload = {}
            out.append(
                {
                    "layer": str(row_layer or ""),
                    "record_id": str(row_id or ""),
                    "category": str(row_category or ""),
                    "payload": payload,
                    "created_at": str(created_at or ""),
                    "updated_at": str(updated_at or ""),
                }
            )
        return out


@dataclass(slots=True)
class PgvectorMemoryBackend:
    pgvector_url: str = ""

    @property
    def name(self) -> str:
        return "pgvector"

    def is_supported(self) -> bool:
        url = str(self.pgvector_url or "").strip().lower()
        if not url:
            return False
        return url.startswith("postgres://") or url.startswith("postgresql://")

    def initialize(self, memory_home: str | Path) -> None:
        del memory_home
        return

    def upsert_layer_record(
        self,
        *,
        layer: str,
        record_id: str,
        payload: dict[str, Any],
        category: str,
        created_at: str,
        updated_at: str,
    ) -> None:
        del layer, record_id, payload, category, created_at, updated_at
        return

    def delete_layer_records(self, record_ids: list[str] | set[str]) -> int:
        del record_ids
        return 0

    def fetch_layer_records(self, *, layer: str, category: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        del layer, category, limit
        return []


def resolve_memory_backend(backend_name: str, pgvector_url: str = "") -> MemoryBackend:
    normalized = str(backend_name or "sqlite").strip().lower()
    if normalized == "pgvector":
        return PgvectorMemoryBackend(pgvector_url=str(pgvector_url or ""))
    return SQLiteMemoryBackend()
