from __future__ import annotations

import json
import importlib
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any
from typing import Protocol
from urllib.parse import urlparse


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

    def search_text(
        self,
        query: str,
        layer: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Full-text BM25 search. Returns list of {record_id, score} dicts."""
        ...


@dataclass(slots=True)
class SQLiteMemoryBackend:
    db_path: str = ""
    _db_file: Path | None = field(init=False, default=None)
    _lock: threading.Lock = field(init=False)
    _status: dict[str, Any] = field(init=False)

    def __post_init__(self) -> None:
        self._db_file = Path(self.db_path).expanduser() if str(self.db_path or "").strip() else None
        self._lock = threading.Lock()
        self._status = {
            "driver_name": "sqlite3",
            "connection_ok": False,
            "vector_extension": False,
            "vector_version": "",
            "supported": True,
            "last_error": "",
        }

    @property
    def name(self) -> str:
        return "sqlite"

    def is_supported(self) -> bool:
        return True

    def diagnostics(self) -> dict[str, Any]:
        return dict(self._status)

    @contextmanager
    def _connect(self):
        if self._db_file is None:
            raise RuntimeError("sqlite backend not initialized")
        conn = sqlite3.connect(str(self._db_file))
        try:
            yield conn
        finally:
            conn.close()

    def initialize(self, memory_home: str | Path) -> None:
        with self._lock:
            if self._db_file is None:
                self._db_file = Path(memory_home).expanduser() / "memory-index.sqlite3"
            self._db_file.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
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
                # FTS5 virtual table for fast full-text search (BM25 native).
                # Uses a standalone (non-content) table so FTS5 manages its own
                # copy of the indexed text; triggers keep it in sync.
                conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS layer_records_fts
                    USING fts5(
                        record_id UNINDEXED,
                        content,
                        tokenize='unicode61 remove_diacritics 2'
                    )
                """)
                # Keep FTS index in sync via triggers
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS layer_records_fts_insert
                    AFTER INSERT ON layer_records BEGIN
                        INSERT INTO layer_records_fts(rowid, record_id, content)
                        VALUES (new.rowid, new.record_id, new.payload);
                    END
                """)
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS layer_records_fts_update
                    AFTER UPDATE ON layer_records BEGIN
                        UPDATE layer_records_fts SET content = new.payload
                        WHERE record_id = new.record_id;
                    END
                """)
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS layer_records_fts_delete
                    AFTER DELETE ON layer_records BEGIN
                        DELETE FROM layer_records_fts WHERE record_id = old.record_id;
                    END
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS resources (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        kind TEXT NOT NULL DEFAULT 'project',
                        description TEXT NOT NULL DEFAULT '',
                        tags TEXT NOT NULL DEFAULT '[]',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS record_resources (
                        record_id TEXT NOT NULL,
                        resource_id TEXT NOT NULL,
                        PRIMARY KEY (record_id, resource_id)
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_record_resources_rid ON record_resources (resource_id)")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS memory_ttl (
                        record_id TEXT PRIMARY KEY,
                        expires_at TEXT NOT NULL
                    )
                """)
                conn.commit()
                self._status.update(connection_ok=True, supported=True, last_error="")

    # ------------------------------------------------------------------
    # Resource CRUD
    # ------------------------------------------------------------------

    def upsert_resource(self, resource: dict[str, Any]) -> None:
        if self._db_file is None:
            return
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """INSERT INTO resources (id, name, kind, description, tags, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET
                           name=excluded.name, kind=excluded.kind,
                           description=excluded.description, tags=excluded.tags,
                           updated_at=excluded.updated_at""",
                    (
                        resource["id"], resource["name"], resource.get("kind", "project"),
                        resource.get("description", ""), resource.get("tags", "[]"),
                        resource.get("created_at", ""), resource.get("updated_at", ""),
                    ),
                )
                conn.commit()

    def fetch_resource(self, resource_id: str) -> dict[str, Any] | None:
        if self._db_file is None:
            return None
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT id, name, kind, description, tags, created_at, updated_at FROM resources WHERE id=?",
                    (resource_id,),
                ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "name": row[1], "kind": row[2], "description": row[3],
                "tags": row[4], "created_at": row[5], "updated_at": row[6]}

    def fetch_all_resources(self) -> list[dict[str, Any]]:
        if self._db_file is None:
            return []
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT id, name, kind, description, tags, created_at, updated_at FROM resources ORDER BY created_at DESC"
                ).fetchall()
        return [{"id": r[0], "name": r[1], "kind": r[2], "description": r[3],
                 "tags": r[4], "created_at": r[5], "updated_at": r[6]} for r in rows]

    def delete_resource(self, resource_id: str) -> None:
        if self._db_file is None:
            return
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM resources WHERE id=?", (resource_id,))
                conn.execute("DELETE FROM record_resources WHERE resource_id=?", (resource_id,))
                conn.commit()

    def link_record_resource(self, record_id: str, resource_id: str) -> None:
        if self._db_file is None:
            return
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO record_resources (record_id, resource_id) VALUES (?, ?)",
                    (record_id, resource_id),
                )
                conn.commit()

    def fetch_records_by_resource(self, resource_id: str) -> list[str]:
        if self._db_file is None:
            return []
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT record_id FROM record_resources WHERE resource_id=? ORDER BY rowid ASC",
                    (resource_id,),
                ).fetchall()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    # TTL CRUD
    # ------------------------------------------------------------------

    def set_ttl(self, record_id: str, expires_at: str) -> None:
        if self._db_file is None:
            return
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO memory_ttl (record_id, expires_at) VALUES (?, ?)",
                    (record_id, expires_at),
                )
                conn.commit()

    def get_ttl(self, record_id: str) -> dict[str, str] | None:
        if self._db_file is None:
            return None
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT record_id, expires_at FROM memory_ttl WHERE record_id=?", (record_id,)
                ).fetchone()
        return {"record_id": row[0], "expires_at": row[1]} if row else None

    def fetch_expired_record_ids(self) -> list[str]:
        if self._db_file is None:
            return []
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT record_id FROM memory_ttl WHERE expires_at <= ?", (now,)
                ).fetchall()
        return [r[0] for r in rows]

    def delete_ttl_entries(self, record_ids: list[str]) -> None:
        if not record_ids or self._db_file is None:
            return
        placeholders = ", ".join("?" for _ in record_ids)
        with self._lock:
            with self._connect() as conn:
                conn.execute(f"DELETE FROM memory_ttl WHERE record_id IN ({placeholders})", record_ids)
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
            with self._connect() as conn:
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
            with self._connect() as conn:
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
            with self._connect() as conn:
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
        normalized = _normalize_embedding(embedding)
        if not clean_id or normalized is None:
            return
        if self._db_file is None:
            return
        with self._lock:
            with self._connect() as conn:
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
            with self._connect() as conn:
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
            with self._connect() as conn:
                rows = conn.execute(query, params).fetchall()

        out: dict[str, list[float]] = {}
        for row_id, row_embedding in rows:
            clean_id = str(row_id or "").strip()
            if not clean_id:
                continue
            parsed = _normalize_embedding(row_embedding)
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
        normalized_query = _normalize_embedding(query_embedding)
        if normalized_query is None:
            return []
        bounded_limit = max(1, int(limit or 1))
        embeddings = self.fetch_embeddings(record_ids=record_ids, limit=max(bounded_limit, 5000))
        if not embeddings:
            return []

        scored: list[dict[str, Any]] = []
        for row_id, vector in embeddings.items():
            score = _cosine_similarity(normalized_query, vector)
            scored.append({"record_id": row_id, "score": float(score)})
        scored.sort(key=lambda item: (float(item.get("score", 0.0)), str(item.get("record_id", ""))), reverse=True)
        return scored[:bounded_limit]

    def search_text(
        self,
        query: str,
        layer: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """BM25 full-text search via SQLite FTS5.

        Returns list of {record_id, score} sorted best-match first.
        Score is the raw FTS5 rank (negative; closer to 0 = better).
        """
        query = str(query or "").strip()
        if not query or self._db_file is None:
            return []
        limit = max(1, min(int(limit or 10), 200))
        # Convert plain multi-word queries to AND boolean so each token is matched
        # independently (FTS5 treats bare phrases as exact adjacency matches).
        import re as _re
        if not any(op in query for op in ("AND", "OR", "NOT", '"', "*", "NEAR")):
            tokens = _re.findall(r'\w+', query)
            query = " AND ".join(tokens) if tokens else query
        with self._lock:
            with self._connect() as conn:
                try:
                    if layer:
                        rows = conn.execute(
                            """
                            SELECT f.record_id, rank AS score
                            FROM layer_records_fts f
                            JOIN layer_records r ON r.record_id = f.record_id
                            WHERE layer_records_fts MATCH ? AND r.layer = ?
                            ORDER BY rank
                            LIMIT ?
                            """,
                            (query, str(layer), limit),
                        ).fetchall()
                    else:
                        rows = conn.execute(
                            """
                            SELECT record_id, rank AS score
                            FROM layer_records_fts
                            WHERE layer_records_fts MATCH ?
                            ORDER BY rank
                            LIMIT ?
                            """,
                            (query, limit),
                        ).fetchall()
                    return [{"record_id": r[0], "score": float(r[1])} for r in rows]
                except Exception:
                    return []


@dataclass(slots=True)
class SQLiteVecMemoryBackend(SQLiteMemoryBackend):
    @property
    def name(self) -> str:
        return "sqlite-vec"

    def is_supported(self) -> bool:
        self._status.update(supported=True)
        return True

    def _load_sqlite_vec(self, conn: sqlite3.Connection) -> tuple[bool, str, str]:
        try:
            sqlite_vec = importlib.import_module("sqlite_vec")
        except Exception:
            return False, "", "sqlite_vec package not installed; falling back to sqlite cosine search"

        load_fn = getattr(sqlite_vec, "load", None)
        if not callable(load_fn):
            return False, "", "sqlite_vec.load() is unavailable; falling back to sqlite cosine search"

        try:
            conn.enable_load_extension(True)
        except Exception:
            pass
        try:
            load_fn(conn)
            row = conn.execute("select vec_version()").fetchone()
            version = str(row[0] or "").strip() if isinstance(row, (list, tuple)) and row else ""
            return True, version, ""
        except Exception as exc:
            return False, "", str(exc)
        finally:
            try:
                conn.enable_load_extension(False)
            except Exception:
                pass

    def initialize(self, memory_home: str | Path) -> None:
        SQLiteMemoryBackend.initialize(self, memory_home)
        if self._db_file is None:
            return
        with self._lock:
            with self._connect() as conn:
                enabled, version, error = self._load_sqlite_vec(conn)
                self._status.update(
                    connection_ok=True,
                    vector_extension=enabled,
                    vector_version=version,
                    supported=True,
                    last_error=error,
                )

    def query_similar_embeddings(
        self,
        query_embedding: list[float],
        record_ids: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        normalized_query = _normalize_embedding(query_embedding)
        if normalized_query is None or self._db_file is None:
            return []
        bounded_limit = max(1, int(limit or 1))
        clean_ids = [str(item).strip() for item in (record_ids or []) if str(item).strip()]
        placeholders = ", ".join("?" for _ in clean_ids)
        where_clause = f"WHERE record_id IN ({placeholders})" if clean_ids else ""
        query_literal = json.dumps(normalized_query, ensure_ascii=True, separators=(",", ":"))
        params: list[Any] = [query_literal, *clean_ids, bounded_limit]
        try:
            with self._lock:
                with self._connect() as conn:
                    enabled, version, error = self._load_sqlite_vec(conn)
                    self._status.update(
                        connection_ok=True,
                        vector_extension=enabled,
                        vector_version=version,
                        supported=True,
                        last_error=error,
                    )
                    if not enabled:
                        raise RuntimeError(error or "sqlite_vec unavailable")
                    rows = conn.execute(
                        f"""
                        SELECT record_id, distance
                        FROM (
                            SELECT
                                record_id,
                                vec_distance_cosine(vec_f32(embedding), vec_f32(?)) AS distance
                            FROM embeddings
                            {where_clause}
                        )
                        ORDER BY distance ASC, record_id DESC
                        LIMIT ?
                        """,
                        params,
                    ).fetchall()
        except Exception as exc:
            self._status["last_error"] = str(exc)
            return SQLiteMemoryBackend.query_similar_embeddings(
                self,
                normalized_query,
                record_ids=record_ids,
                limit=bounded_limit,
            )

        return [
            {
                "record_id": str(row_id or ""),
                "score": float(1.0 - float(distance or 0.0)),
            }
            for row_id, distance in rows
            if str(row_id or "").strip()
        ]


@dataclass(slots=True)
class PgvectorMemoryBackend:
    pgvector_url: str = ""
    _lock: threading.Lock = field(init=False)
    _status: dict[str, Any] = field(init=False)

    def __post_init__(self) -> None:
        self._lock = threading.RLock()
        self._status = self._default_status()

    @property
    def name(self) -> str:
        return "pgvector"

    @staticmethod
    def _default_status() -> dict[str, Any]:
        return {
            "url_valid": False,
            "driver_name": "",
            "driver_available": False,
            "connection_ok": False,
            "vector_extension": False,
            "vector_version": "",
            "sql_similarity_available": False,
            "supported": False,
            "last_error": "",
        }

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def support_error(self) -> str:
        if not bool(self.diagnostics().get("supported", False)):
            self.is_supported()
        return str(self.diagnostics().get("last_error", "") or "")

    def _set_status(self, **updates: Any) -> None:
        with self._lock:
            self._status.update(updates)

    def is_supported(self) -> bool:
        status = self._default_status()
        status["url_valid"] = self._is_valid_pg_url()
        if not status["url_valid"]:
            status["last_error"] = "pgvector_url must use postgres:// or postgresql:// with a hostname"
            self._set_status(**status)
            return False

        driver_name, driver_module = self._detect_driver()
        status["driver_name"] = str(driver_name or "")
        status["driver_available"] = bool(driver_name is not None and driver_module is not None)
        if driver_name is None or driver_module is None:
            status["last_error"] = "pgvector backend requires psycopg or psycopg2"
            self._set_status(**status)
            return False

        conn = None
        try:
            conn = driver_module.connect(str(self.pgvector_url or ""))
            status["connection_ok"] = True
            status["vector_version"] = self._probe_vector_extension(conn)
            status["vector_extension"] = bool(status["vector_version"])
            status["sql_similarity_available"] = bool(status["vector_extension"])
            status["supported"] = bool(status["connection_ok"] and status["vector_extension"])
            status["last_error"] = ""
            return bool(status["supported"])
        except Exception as exc:
            status["last_error"] = str(exc)
            return False
        finally:
            self._set_status(**status)
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

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

    @staticmethod
    def _row_first_value(row: Any) -> str:
        if isinstance(row, (list, tuple)) and row:
            return str(row[0] or "")
        if row is None:
            return ""
        return str(row or "")

    def _probe_vector_extension(self, conn: Any) -> str:
        cursor = None
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            version = self._row_first_value(cursor.fetchone()).strip()
            if version:
                return version

            try:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                conn.commit()
            except Exception as exc:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise RuntimeError("pgvector extension 'vector' is unavailable") from exc

            cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            version = self._row_first_value(cursor.fetchone()).strip()
            if not version:
                raise RuntimeError("pgvector extension 'vector' is unavailable")
            return version
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass

    def _ensure_embeddings_vector_column(self, cursor: Any) -> None:
        cursor.execute(
            """
            SELECT udt_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'embeddings'
              AND column_name = 'embedding'
            """
        )
        udt_name = self._row_first_value(cursor.fetchone()).strip().lower()
        if udt_name == "vector":
            return
        cursor.execute(
            """
            ALTER TABLE embeddings
            ALTER COLUMN embedding TYPE vector
            USING embedding::vector
            """
        )

    def _open_connection(self) -> Any | None:
        if not self._is_valid_pg_url():
            self._set_status(
                url_valid=False,
                connection_ok=False,
                sql_similarity_available=False,
                supported=False,
                last_error="pgvector_url must use postgres:// or postgresql:// with a hostname",
            )
            return None
        driver_name, driver_module = self._detect_driver()
        if driver_name is None or driver_module is None:
            self._set_status(
                url_valid=True,
                driver_name=str(driver_name or ""),
                driver_available=False,
                connection_ok=False,
                sql_similarity_available=False,
                supported=False,
                last_error="pgvector backend requires psycopg or psycopg2",
            )
            return None
        try:
            conn = driver_module.connect(str(self.pgvector_url or ""))
            self._set_status(
                url_valid=True,
                driver_name=str(driver_name or ""),
                driver_available=True,
                connection_ok=True,
                last_error="",
            )
            return conn
        except Exception as exc:
            self._set_status(
                url_valid=True,
                driver_name=str(driver_name or ""),
                driver_available=True,
                connection_ok=False,
                sql_similarity_available=False,
                supported=False,
                last_error=str(exc),
            )
            return None

    def initialize(self, memory_home: str | Path) -> None:
        del memory_home
        if not self.is_supported():
            return
        conn = self._open_connection()
        if conn is None:
            details = self.diagnostics()
            raise RuntimeError(str(details.get("last_error", "") or "pgvector connection unavailable"))
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
                        embedding vector NOT NULL,
                        created_at TEXT NOT NULL,
                        source TEXT NOT NULL
                    )
                    """
                )
                self._ensure_embeddings_vector_column(cursor)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_layer_records_layer ON layer_records(layer)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_layer_records_category ON layer_records(category)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_layer_records_updated_at ON layer_records(updated_at)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_created_at ON embeddings(created_at)")
                conn.commit()
                self._set_status(sql_similarity_available=True, supported=True, last_error="")
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
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
        normalized = _normalize_embedding(embedding)
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
                    VALUES (%s, %s::vector, %s, %s)
                    ON CONFLICT(record_id) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        created_at = EXCLUDED.created_at,
                        source = EXCLUDED.source
                    """,
                    (
                        clean_id,
                        self._to_vector_literal(normalized),
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
        query = "SELECT record_id, embedding::text FROM embeddings"
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
            parsed = _normalize_embedding(row_embedding)
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
        normalized_query = _normalize_embedding(query_embedding)
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
                        "SELECT record_id, (1 - (embedding <=> %s::vector)) AS score "
                        "FROM embeddings"
                    )

                    clean_ids = [str(item).strip() for item in (record_ids or []) if str(item).strip()]
                    if clean_ids:
                        placeholders = ", ".join("%s" for _ in clean_ids)
                        query += f" WHERE record_id IN ({placeholders})"
                        params.extend(clean_ids)

                    query += " ORDER BY embedding <=> %s::vector ASC, record_id DESC LIMIT %s"
                    params.append(vector_literal)
                    params.append(bounded_limit)

                    cursor = conn.cursor()
                    cursor.execute(query, tuple(params))
                    rows = cursor.fetchall()
                    self._set_status(sql_similarity_available=True, last_error="")

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
                except Exception as exc:
                    self._set_status(sql_similarity_available=False, last_error=str(exc))
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
            scored.append({"record_id": row_id, "score": _cosine_similarity(normalized_query, vector)})
        scored.sort(key=lambda item: (float(item.get("score", 0.0)), str(item.get("record_id", ""))), reverse=True)
        return scored[:bounded_limit]

    def search_text(self, query: str, layer: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        """Full-text search via PostgreSQL plainto_tsquery on payload->>'text'.

        Returns list of {record_id, score} sorted best-match first (score in [0,1]).
        Falls back gracefully to [] when the connection is unavailable.
        """
        query = str(query or "").strip()
        if not query:
            return []
        limit = max(1, min(int(limit or 10), 200))

        conn = self._open_connection()
        if conn is None:
            return []

        with self._lock:
            cursor = None
            try:
                cursor = conn.cursor()
                text_col = "COALESCE(payload::json->>'text', '')"
                tsv = f"to_tsvector('english', {text_col})"
                tsq = "plainto_tsquery('english', %s)"
                if layer:
                    cursor.execute(
                        f"""
                        SELECT record_id,
                               ts_rank({tsv}, {tsq}) AS score
                        FROM layer_records
                        WHERE layer = %s
                          AND {tsv} @@ {tsq}
                        ORDER BY score DESC
                        LIMIT %s
                        """,
                        (query, str(layer), query, limit),
                    )
                else:
                    cursor.execute(
                        f"""
                        SELECT record_id,
                               ts_rank({tsv}, {tsq}) AS score
                        FROM layer_records
                        WHERE {tsv} @@ {tsq}
                        ORDER BY score DESC
                        LIMIT %s
                        """,
                        (query, query, limit),
                    )
                rows = cursor.fetchall()
                return [{"record_id": str(r[0] or ""), "score": float(r[1])} for r in rows]
            except Exception as exc:
                self._set_status(last_error=str(exc))
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


def resolve_memory_backend(backend_name: str, pgvector_url: str = "") -> MemoryBackend:
    normalized = str(backend_name or "sqlite").strip().lower()
    if normalized in {"sqlite-vec", "sqlite_vec"}:
        return SQLiteVecMemoryBackend()
    if normalized == "pgvector":
        return PgvectorMemoryBackend(pgvector_url=str(pgvector_url or ""))
    return SQLiteMemoryBackend()
