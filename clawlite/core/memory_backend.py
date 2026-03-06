from __future__ import annotations

import json
import importlib
import sqlite3
import threading
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any
from typing import Protocol
from urllib.parse import urlparse


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

    def upsert_embedding(self, record_id: str, embedding: list[float], created_at: str, source: str) -> None:
        ...

    def delete_embeddings(self, record_ids: list[str] | set[str]) -> int:
        ...

    def fetch_embeddings(self, record_ids: list[str] | None = None, limit: int = 5000) -> dict[str, list[float]]:
        ...

    def query_similar_embeddings(
        self,
        query_embedding: list[float],
        record_ids: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
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

    @staticmethod
    def _normalize_embedding(raw: Any) -> list[float] | None:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                return None
        if not isinstance(raw, list) or not raw:
            return None
        out: list[float] = []
        for item in raw:
            try:
                out.append(float(item))
            except Exception:
                return None
        return out if out else None

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = 0.0
        left_norm = 0.0
        right_norm = 0.0
        for idx in range(len(left)):
            lval = float(left[idx])
            rval = float(right[idx])
            dot += lval * rval
            left_norm += lval * lval
            right_norm += rval * rval
        if left_norm <= 0.0 or right_norm <= 0.0:
            return 0.0
        return float(dot / ((left_norm * right_norm) ** 0.5))

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
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS embeddings (
                        record_id TEXT PRIMARY KEY,
                        embedding TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        source TEXT NOT NULL
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_layer_records_layer ON layer_records(layer)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_layer_records_category ON layer_records(category)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_layer_records_updated_at ON layer_records(updated_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_created_at ON embeddings(created_at)")
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

    def upsert_embedding(self, record_id: str, embedding: list[float], created_at: str, source: str) -> None:
        clean_id = str(record_id or "").strip()
        normalized = self._normalize_embedding(embedding)
        if not clean_id or normalized is None:
            return
        if self._db_file is None:
            return
        with self._lock:
            with sqlite3.connect(str(self._db_file)) as conn:
                conn.execute(
                    """
                    INSERT INTO embeddings (record_id, embedding, created_at, source)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(record_id) DO UPDATE SET
                        embedding = excluded.embedding,
                        created_at = excluded.created_at,
                        source = excluded.source
                    """,
                    (
                        clean_id,
                        json.dumps(normalized, ensure_ascii=False),
                        str(created_at or ""),
                        str(source or ""),
                    ),
                )
                conn.commit()

    def delete_embeddings(self, record_ids: list[str] | set[str]) -> int:
        ids = [str(item).strip() for item in record_ids if str(item).strip()]
        if not ids:
            return 0
        if self._db_file is None:
            return 0
        placeholders = ", ".join("?" for _ in ids)
        with self._lock:
            with sqlite3.connect(str(self._db_file)) as conn:
                cursor = conn.execute(f"DELETE FROM embeddings WHERE record_id IN ({placeholders})", ids)
                conn.commit()
                return int(cursor.rowcount or 0)

    def fetch_embeddings(self, record_ids: list[str] | None = None, limit: int = 5000) -> dict[str, list[float]]:
        bounded_limit = max(1, int(limit or 1))
        if self._db_file is None:
            return {}

        params: list[Any] = []
        query = "SELECT record_id, embedding FROM embeddings"
        clean_ids = [str(item).strip() for item in (record_ids or []) if str(item).strip()]
        if clean_ids:
            placeholders = ", ".join("?" for _ in clean_ids)
            query += f" WHERE record_id IN ({placeholders})"
            params.extend(clean_ids)
        query += " ORDER BY created_at DESC, record_id DESC LIMIT ?"
        params.append(bounded_limit)

        with self._lock:
            with sqlite3.connect(str(self._db_file)) as conn:
                rows = conn.execute(query, params).fetchall()

        out: dict[str, list[float]] = {}
        for row_id, row_embedding in rows:
            clean_id = str(row_id or "").strip()
            if not clean_id:
                continue
            parsed = self._normalize_embedding(row_embedding)
            if parsed is None:
                continue
            out[clean_id] = parsed
        return out

    def query_similar_embeddings(
        self,
        query_embedding: list[float],
        record_ids: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        normalized_query = self._normalize_embedding(query_embedding)
        if normalized_query is None:
            return []
        bounded_limit = max(1, int(limit or 1))
        embeddings = self.fetch_embeddings(record_ids=record_ids, limit=max(bounded_limit, 5000))
        if not embeddings:
            return []

        scored: list[dict[str, Any]] = []
        for row_id, vector in embeddings.items():
            score = self._cosine_similarity(normalized_query, vector)
            scored.append({"record_id": row_id, "score": float(score)})
        scored.sort(key=lambda item: (float(item.get("score", 0.0)), str(item.get("record_id", ""))), reverse=True)
        return scored[:bounded_limit]


@dataclass(slots=True)
class PgvectorMemoryBackend:
    pgvector_url: str = ""
    _lock: threading.Lock = field(init=False)

    def __post_init__(self) -> None:
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "pgvector"

    def is_supported(self) -> bool:
        if not self._is_valid_pg_url():
            return False
        return self._detect_driver()[0] is not None

    @staticmethod
    def _normalize_embedding(raw: Any) -> list[float] | None:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                return None
        if not isinstance(raw, list) or not raw:
            return None
        out: list[float] = []
        for item in raw:
            try:
                out.append(float(item))
            except Exception:
                return None
        return out if out else None

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = 0.0
        left_norm = 0.0
        right_norm = 0.0
        for idx in range(len(left)):
            lval = float(left[idx])
            rval = float(right[idx])
            dot += lval * rval
            left_norm += lval * lval
            right_norm += rval * rval
        if left_norm <= 0.0 or right_norm <= 0.0:
            return 0.0
        return float(dot / ((left_norm * right_norm) ** 0.5))

    @staticmethod
    def _to_vector_literal(embedding: list[float]) -> str:
        return json.dumps([float(item) for item in embedding], ensure_ascii=True, separators=(",", ":"))

    def _is_valid_pg_url(self) -> bool:
        raw_url = str(self.pgvector_url or "").strip()
        if not raw_url:
            return False
        try:
            parsed = urlparse(raw_url)
        except Exception:
            return False
        if parsed.scheme not in {"postgres", "postgresql"}:
            return False
        return bool(parsed.hostname)

    def _detect_driver(self) -> tuple[str | None, Any | None]:
        for module_name in ("psycopg", "psycopg2"):
            try:
                module = importlib.import_module(module_name)
                return module_name, module
            except Exception:
                continue
        return None, None

    def _open_connection(self) -> Any | None:
        if not self._is_valid_pg_url():
            return None
        driver_name, driver_module = self._detect_driver()
        if driver_name is None or driver_module is None:
            return None
        try:
            return driver_module.connect(str(self.pgvector_url or ""))
        except Exception:
            return None

    def initialize(self, memory_home: str | Path) -> None:
        del memory_home
        conn = self._open_connection()
        if conn is None:
            return
        with self._lock:
            cursor = None
            try:
                cursor = conn.cursor()
                cursor.execute(
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
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS embeddings (
                        record_id TEXT PRIMARY KEY,
                        embedding TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        source TEXT NOT NULL
                    )
                    """
                )
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_layer_records_layer ON layer_records(layer)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_layer_records_category ON layer_records(category)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_layer_records_updated_at ON layer_records(updated_at)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_created_at ON embeddings(created_at)")
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
            finally:
                if cursor is not None:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                try:
                    conn.close()
                except Exception:
                    pass

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
        conn = self._open_connection()
        if conn is None:
            return
        with self._lock:
            cursor = None
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO layer_records (layer, record_id, category, payload, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT(layer, record_id) DO UPDATE SET
                        category = EXCLUDED.category,
                        payload = EXCLUDED.payload,
                        updated_at = EXCLUDED.updated_at
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
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
            finally:
                if cursor is not None:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                try:
                    conn.close()
                except Exception:
                    pass

    def delete_layer_records(self, record_ids: list[str] | set[str]) -> int:
        ids = [str(item).strip() for item in record_ids if str(item).strip()]
        if not ids:
            return 0

        conn = self._open_connection()
        if conn is None:
            return 0

        placeholders = ", ".join("%s" for _ in ids)
        with self._lock:
            cursor = None
            try:
                cursor = conn.cursor()
                cursor.execute(f"DELETE FROM layer_records WHERE record_id IN ({placeholders})", tuple(ids))
                deleted = int(getattr(cursor, "rowcount", 0) or 0)
                conn.commit()
                return deleted
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                return 0
            finally:
                if cursor is not None:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                try:
                    conn.close()
                except Exception:
                    pass

    def fetch_layer_records(self, *, layer: str, category: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        bounded_limit = max(1, int(limit or 1))
        query = (
            "SELECT layer, record_id, category, payload, created_at, updated_at "
            "FROM layer_records WHERE layer = %s"
        )
        params: list[Any] = [str(layer or "item")]
        if category is not None:
            query += " AND category = %s"
            params.append(str(category or "context"))
        query += " ORDER BY updated_at DESC, record_id DESC LIMIT %s"
        params.append(bounded_limit)

        conn = self._open_connection()
        if conn is None:
            return []

        with self._lock:
            cursor = None
            try:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()
            except Exception:
                return []
            finally:
                if cursor is not None:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                try:
                    conn.close()
                except Exception:
                    pass

        out: list[dict[str, Any]] = []
        for row_layer, row_id, row_category, row_payload, created_at, updated_at in rows:
            payload: dict[str, Any] = {}
            if isinstance(row_payload, dict):
                payload = row_payload
            else:
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

    def upsert_embedding(self, record_id: str, embedding: list[float], created_at: str, source: str) -> None:
        clean_id = str(record_id or "").strip()
        normalized = self._normalize_embedding(embedding)
        if not clean_id or normalized is None:
            return
        conn = self._open_connection()
        if conn is None:
            return
        with self._lock:
            cursor = None
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO embeddings (record_id, embedding, created_at, source)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT(record_id) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        created_at = EXCLUDED.created_at,
                        source = EXCLUDED.source
                    """,
                    (
                        clean_id,
                        json.dumps(normalized, ensure_ascii=False),
                        str(created_at or ""),
                        str(source or ""),
                    ),
                )
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
            finally:
                if cursor is not None:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                try:
                    conn.close()
                except Exception:
                    pass

    def delete_embeddings(self, record_ids: list[str] | set[str]) -> int:
        ids = [str(item).strip() for item in record_ids if str(item).strip()]
        if not ids:
            return 0
        conn = self._open_connection()
        if conn is None:
            return 0

        placeholders = ", ".join("%s" for _ in ids)
        with self._lock:
            cursor = None
            try:
                cursor = conn.cursor()
                cursor.execute(f"DELETE FROM embeddings WHERE record_id IN ({placeholders})", tuple(ids))
                deleted = int(getattr(cursor, "rowcount", 0) or 0)
                conn.commit()
                return deleted
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                return 0
            finally:
                if cursor is not None:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                try:
                    conn.close()
                except Exception:
                    pass

    def fetch_embeddings(self, record_ids: list[str] | None = None, limit: int = 5000) -> dict[str, list[float]]:
        bounded_limit = max(1, int(limit or 1))
        conn = self._open_connection()
        if conn is None:
            return {}

        clean_ids = [str(item).strip() for item in (record_ids or []) if str(item).strip()]
        query = "SELECT record_id, embedding FROM embeddings"
        params: list[Any] = []
        if clean_ids:
            placeholders = ", ".join("%s" for _ in clean_ids)
            query += f" WHERE record_id IN ({placeholders})"
            params.extend(clean_ids)
        query += " ORDER BY created_at DESC, record_id DESC LIMIT %s"
        params.append(bounded_limit)

        with self._lock:
            cursor = None
            try:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()
            except Exception:
                return {}
            finally:
                if cursor is not None:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                try:
                    conn.close()
                except Exception:
                    pass

        out: dict[str, list[float]] = {}
        for row_id, row_embedding in rows:
            clean_id = str(row_id or "").strip()
            if not clean_id:
                continue
            parsed = self._normalize_embedding(row_embedding)
            if parsed is None:
                continue
            out[clean_id] = parsed
        return out

    def query_similar_embeddings(
        self,
        query_embedding: list[float],
        record_ids: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        normalized_query = self._normalize_embedding(query_embedding)
        if normalized_query is None:
            return []
        bounded_limit = max(1, int(limit or 1))

        sql_hits: list[dict[str, Any]] | None = None
        conn = self._open_connection()
        if conn is not None:
            with self._lock:
                cursor = None
                try:
                    vector_literal = self._to_vector_literal(normalized_query)
                    params: list[Any] = [vector_literal]
                    query = (
                        "SELECT record_id, (1 - (embedding::vector <=> %s::vector)) AS score "
                        "FROM embeddings"
                    )

                    clean_ids = [str(item).strip() for item in (record_ids or []) if str(item).strip()]
                    if clean_ids:
                        placeholders = ", ".join("%s" for _ in clean_ids)
                        query += f" WHERE record_id IN ({placeholders})"
                        params.extend(clean_ids)

                    query += " ORDER BY embedding::vector <=> %s::vector ASC, record_id DESC LIMIT %s"
                    params.append(vector_literal)
                    params.append(bounded_limit)

                    cursor = conn.cursor()
                    cursor.execute(query, tuple(params))
                    rows = cursor.fetchall()

                    sql_hits = []
                    for row in rows:
                        row_id = str(row[0] or "").strip() if len(row) >= 1 else ""
                        if not row_id:
                            continue
                        try:
                            score = float(row[1]) if len(row) >= 2 else 0.0
                        except Exception:
                            score = 0.0
                        sql_hits.append({"record_id": row_id, "score": score})
                except Exception:
                    sql_hits = None
                finally:
                    if cursor is not None:
                        try:
                            cursor.close()
                        except Exception:
                            pass
                    try:
                        conn.close()
                    except Exception:
                        pass

        if sql_hits is not None:
            return sql_hits[:bounded_limit]

        embeddings = self.fetch_embeddings(record_ids=record_ids, limit=max(bounded_limit, 5000))
        if not embeddings:
            return []
        scored: list[dict[str, Any]] = []
        for row_id, vector in embeddings.items():
            scored.append({"record_id": row_id, "score": self._cosine_similarity(normalized_query, vector)})
        scored.sort(key=lambda item: (float(item.get("score", 0.0)), str(item.get("record_id", ""))), reverse=True)
        return scored[:bounded_limit]


def resolve_memory_backend(backend_name: str, pgvector_url: str = "") -> MemoryBackend:
    normalized = str(backend_name or "sqlite").strip().lower()
    if normalized == "pgvector":
        return PgvectorMemoryBackend(pgvector_url=str(pgvector_url or ""))
    return SQLiteMemoryBackend()
