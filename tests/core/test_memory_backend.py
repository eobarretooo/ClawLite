from __future__ import annotations

import importlib
from contextlib import contextmanager
from pathlib import Path

import clawlite.core.memory_backend as memory_backend_module
from clawlite.core.memory_backend import resolve_memory_backend


def test_sqlite_memory_backend_roundtrip(tmp_path: Path) -> None:
    backend = resolve_memory_backend("sqlite")
    backend.initialize(tmp_path)

    backend.upsert_layer_record(
        layer="item",
        record_id="rec-1",
        payload={"text": "hello"},
        category="context",
        created_at="2026-03-01T00:00:00+00:00",
        updated_at="2026-03-01T00:00:00+00:00",
    )
    backend.upsert_layer_record(
        layer="resource",
        record_id="rec-2",
        payload={"text": "raw"},
        category="context",
        created_at="2026-03-01T00:00:01+00:00",
        updated_at="2026-03-01T00:00:01+00:00",
    )

    rows = backend.fetch_layer_records(layer="item", limit=10)
    assert len(rows) == 1
    assert rows[0]["record_id"] == "rec-1"
    assert rows[0]["payload"]["text"] == "hello"

    deleted = backend.delete_layer_records({"rec-1"})
    assert deleted >= 1
    assert backend.fetch_layer_records(layer="item", limit=10) == []


def test_sqlite_embedding_roundtrip(tmp_path: Path) -> None:
    backend = resolve_memory_backend("sqlite")
    backend.initialize(tmp_path)

    backend.upsert_embedding(
        "emb-1",
        [0.1, 0.9],
        "2026-03-01T00:00:00+00:00",
        "user",
    )
    backend.upsert_embedding(
        "emb-2",
        [0.8, 0.2],
        "2026-03-01T00:00:01+00:00",
        "seed",
    )

    fetched_all = backend.fetch_embeddings(limit=10)
    assert fetched_all["emb-1"] == [0.1, 0.9]
    assert fetched_all["emb-2"] == [0.8, 0.2]

    fetched_filtered = backend.fetch_embeddings(record_ids=["emb-2"], limit=10)
    assert fetched_filtered == {"emb-2": [0.8, 0.2]}

    deleted = backend.delete_embeddings(["emb-1"])
    assert deleted >= 1
    remaining = backend.fetch_embeddings(limit=10)
    assert "emb-1" not in remaining
    assert remaining["emb-2"] == [0.8, 0.2]


def test_sqlite_query_similar_embeddings_returns_best_match(tmp_path: Path) -> None:
    backend = resolve_memory_backend("sqlite")
    backend.initialize(tmp_path)

    backend.upsert_embedding("alpha", [1.0, 0.0], "2026-03-01T00:00:00+00:00", "seed")
    backend.upsert_embedding("beta", [0.0, 1.0], "2026-03-01T00:00:00+00:00", "seed")
    backend.upsert_embedding("gamma", [0.5, 0.5], "2026-03-01T00:00:00+00:00", "seed")

    hits = backend.query_similar_embeddings([0.9, 0.1], limit=2)
    assert hits
    assert hits[0]["record_id"] == "alpha"
    assert float(hits[0]["score"]) > float(hits[1]["score"])


def test_sqlite_vec_backend_falls_back_to_sqlite_when_extension_unavailable(tmp_path: Path, monkeypatch) -> None:
    backend = resolve_memory_backend("sqlite-vec")
    monkeypatch.setattr(
        type(backend),
        "_load_sqlite_vec",
        lambda self, conn: (False, "", "sqlite_vec package not installed; falling back to sqlite cosine search"),
    )
    backend.initialize(tmp_path)

    backend.upsert_embedding("alpha", [1.0, 0.0], "2026-03-01T00:00:00+00:00", "seed")
    backend.upsert_embedding("beta", [0.0, 1.0], "2026-03-01T00:00:00+00:00", "seed")

    hits = backend.query_similar_embeddings([0.9, 0.1], limit=1)
    details = backend.diagnostics()

    assert hits == [{"record_id": "alpha", "score": hits[0]["score"]}]
    assert details["vector_extension"] is False
    assert "sqlite_vec" in str(details["last_error"])


def test_sqlite_vec_backend_uses_sql_distance_when_extension_available(tmp_path: Path, monkeypatch) -> None:
    backend = resolve_memory_backend("sqlite-vec")
    backend.initialize(tmp_path)
    monkeypatch.setattr(type(backend), "_load_sqlite_vec", lambda self, conn: (True, "0.1.6", ""))

    class FakeResult:
        def fetchall(self):
            return [("alpha", 0.01), ("beta", 0.20)]

    class FakeConnection:
        def __init__(self) -> None:
            self.queries: list[tuple[str, tuple[object, ...]]] = []

        def execute(self, query: str, params: tuple[object, ...] | list[object] = ()):
            self.queries.append((query, tuple(params)))
            return FakeResult()

    fake_conn = FakeConnection()

    @contextmanager
    def _fake_connect(self):
        yield fake_conn

    monkeypatch.setattr(type(backend), "_connect", _fake_connect)

    hits = backend.query_similar_embeddings([1.0, 0.0], record_ids=["alpha", "beta"], limit=2)
    details = backend.diagnostics()

    assert hits[0]["record_id"] == "alpha"
    assert hits[1]["record_id"] == "beta"
    assert "vec_distance_cosine" in fake_conn.queries[0][0]
    assert fake_conn.queries[0][1][0] == "[1.0,0.0]"
    assert details["vector_extension"] is True
    assert details["vector_version"] == "0.1.6"


def test_pgvector_backend_remains_graceful_when_unsupported(tmp_path: Path) -> None:
    backend = resolve_memory_backend("pgvector", pgvector_url="")
    assert backend.is_supported() is False

    backend.initialize(tmp_path)
    backend.upsert_layer_record(
        layer="item",
        record_id="rec-1",
        payload={"text": "ignored"},
        category="context",
        created_at="",
        updated_at="",
    )
    backend.upsert_embedding("rec-1", [1.0, 0.0], "", "ignored")
    assert backend.fetch_layer_records(layer="item", limit=5) == []
    assert backend.fetch_embeddings(limit=5) == {}
    assert backend.query_similar_embeddings([1.0, 0.0], limit=5) == []
    assert backend.delete_layer_records(["rec-1"]) == 0
    assert backend.delete_embeddings(["rec-1"]) == 0


def test_pgvector_support_detection_requires_valid_url_and_driver(monkeypatch) -> None:
    backend_with_invalid_url = resolve_memory_backend("pgvector", pgvector_url="not-a-postgres-url")
    assert backend_with_invalid_url.is_supported() is False

    attempted_imports: list[str] = []
    real_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None):
        if name in {"psycopg", "psycopg2"}:
            attempted_imports.append(name)
            raise ImportError(f"{name} missing")
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    backend_missing_drivers = resolve_memory_backend(
        "pgvector",
        pgvector_url="postgresql://user:pass@localhost:5432/clawlite",
    )
    assert backend_missing_drivers.is_supported() is False
    assert attempted_imports == ["psycopg", "psycopg2"]


def test_pgvector_support_detection_requires_connection_and_vector_extension(monkeypatch) -> None:
    backend = resolve_memory_backend(
        "pgvector",
        pgvector_url="postgresql://user:pass@localhost:5432/clawlite",
    )

    class FakeCursor:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def execute(self, query: str) -> None:
            self.queries.append(query)

        def fetchone(self):
            return ("0.8.1",)

        def close(self) -> None:
            return None

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_instance = FakeCursor()
            self.closed = False

        def cursor(self) -> FakeCursor:
            return self.cursor_instance

        def close(self) -> None:
            self.closed = True

    class FakeDriver:
        @staticmethod
        def connect(url: str) -> FakeConnection:
            assert url == "postgresql://user:pass@localhost:5432/clawlite"
            return FakeConnection()

    monkeypatch.setattr(type(backend), "_detect_driver", lambda self: ("psycopg", FakeDriver))

    assert backend.is_supported() is True
    details = backend.diagnostics()
    assert details["driver_name"] == "psycopg"
    assert details["connection_ok"] is True
    assert details["vector_extension"] is True
    assert details["vector_version"] == "0.8.1"
    assert details["supported"] is True
    assert details["last_error"] == ""


def test_pgvector_support_detection_reports_missing_vector_extension(monkeypatch) -> None:
    backend = resolve_memory_backend(
        "pgvector",
        pgvector_url="postgresql://user:pass@localhost:5432/clawlite",
    )

    class FakeCursor:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def execute(self, query: str) -> None:
            self.queries.append(query)
            if query.startswith("CREATE EXTENSION"):
                raise RuntimeError("permission denied")

        def fetchone(self):
            return None

        def close(self) -> None:
            return None

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_instance = FakeCursor()
            self.closed = False
            self.rollback_calls = 0

        def cursor(self) -> FakeCursor:
            return self.cursor_instance

        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            self.rollback_calls += 1

        def close(self) -> None:
            self.closed = True

    class FakeDriver:
        @staticmethod
        def connect(url: str) -> FakeConnection:
            assert url == "postgresql://user:pass@localhost:5432/clawlite"
            return FakeConnection()

    monkeypatch.setattr(type(backend), "_detect_driver", lambda self: ("psycopg", FakeDriver))

    assert backend.is_supported() is False
    details = backend.diagnostics()
    assert details["connection_ok"] is True
    assert details["vector_extension"] is False
    assert details["supported"] is False
    assert "pgvector extension 'vector' is unavailable" in str(details["last_error"])


def test_pgvector_query_similar_embeddings_uses_sql_path(monkeypatch) -> None:
    backend = resolve_memory_backend(
        "pgvector",
        pgvector_url="postgresql://user:pass@localhost:5432/clawlite",
    )

    class FakeCursor:
        def __init__(self) -> None:
            self.executed_query: str = ""
            self.executed_params: tuple[object, ...] = ()

        def execute(self, query: str, params: tuple[object, ...]) -> None:
            self.executed_query = query
            self.executed_params = params

        def fetchall(self):
            return [("alpha", 0.95), ("beta", 0.80)]

        def close(self) -> None:
            return None

    class FakeConnection:
        def __init__(self) -> None:
            self._cursor = FakeCursor()
            self.closed = False

        def cursor(self) -> FakeCursor:
            return self._cursor

        def close(self) -> None:
            self.closed = True

    fake_conn = FakeConnection()
    monkeypatch.setattr(type(backend), "_open_connection", lambda self: fake_conn)

    def fail_if_fallback_called(*args, **kwargs):
        del args, kwargs
        raise AssertionError("python fallback should not be used when SQL path succeeds")

    monkeypatch.setattr(type(backend), "fetch_embeddings", lambda self, record_ids=None, limit=5000: fail_if_fallback_called())

    hits = backend.query_similar_embeddings([1.0, 0.0], record_ids=["alpha", "beta"], limit=1)

    assert hits == [{"record_id": "alpha", "score": 0.95}]
    assert "embedding <=> %s::vector" in fake_conn._cursor.executed_query
    assert "record_id IN (%s, %s)" in fake_conn._cursor.executed_query
    assert fake_conn._cursor.executed_params[-1] == 1
    assert fake_conn.closed is True


def test_pgvector_query_similar_embeddings_falls_back_when_sql_fails(monkeypatch) -> None:
    backend = resolve_memory_backend(
        "pgvector",
        pgvector_url="postgresql://user:pass@localhost:5432/clawlite",
    )

    class BrokenCursor:
        def execute(self, query: str, params: tuple[object, ...]) -> None:
            del query, params
            raise RuntimeError("sql path unavailable")

        def close(self) -> None:
            return None

    class BrokenConnection:
        def cursor(self) -> BrokenCursor:
            return BrokenCursor()

        def close(self) -> None:
            return None

    monkeypatch.setattr(type(backend), "_open_connection", lambda self: BrokenConnection())
    monkeypatch.setattr(
        type(backend),
        "fetch_embeddings",
        lambda self, record_ids=None, limit=5000: {
            "alpha": [1.0, 0.0],
            "beta": [0.0, 1.0],
        },
    )

    hits = backend.query_similar_embeddings([0.9, 0.1], record_ids=["alpha", "beta"], limit=2)

    assert [item["record_id"] for item in hits] == ["alpha", "beta"]
    assert float(hits[0]["score"]) > float(hits[1]["score"])


def test_pgvector_initialize_migrates_embedding_column_to_vector(monkeypatch, tmp_path: Path) -> None:
    backend = resolve_memory_backend(
        "pgvector",
        pgvector_url="postgresql://user:pass@localhost:5432/clawlite",
    )
    connections: list[FakeConnection] = []

    class FakeCursor:
        def __init__(self) -> None:
            self.queries: list[str] = []
            self.last_query: str = ""

        def execute(self, query: str) -> None:
            self.last_query = query
            self.queries.append(query)

        def fetchone(self):
            if "SELECT extversion FROM pg_extension" in self.last_query:
                return ("0.8.1",)
            if "SELECT udt_name" in self.last_query:
                return ("text",)
            return None

        def fetchall(self):
            return []

        def close(self) -> None:
            return None

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_instance = FakeCursor()
            self.commit_calls = 0
            self.rollback_calls = 0
            self.closed = False

        def cursor(self) -> FakeCursor:
            return self.cursor_instance

        def commit(self) -> None:
            self.commit_calls += 1

        def rollback(self) -> None:
            self.rollback_calls += 1

        def close(self) -> None:
            self.closed = True

    class FakeDriver:
        @staticmethod
        def connect(url: str) -> FakeConnection:
            assert url == "postgresql://user:pass@localhost:5432/clawlite"
            conn = FakeConnection()
            connections.append(conn)
            return conn

    monkeypatch.setattr(type(backend), "_detect_driver", lambda self: ("psycopg", FakeDriver))

    backend.initialize(tmp_path)

    assert len(connections) == 2
    init_queries = connections[-1].cursor_instance.queries
    assert any("embedding vector NOT NULL" in query for query in init_queries)
    assert any("ALTER TABLE embeddings" in query for query in init_queries)
    assert any("USING hnsw" in query for query in init_queries)
    assert connections[-1].commit_calls >= 1


def test_pgvector_initialize_keeps_backend_working_when_ann_index_creation_fails(monkeypatch, tmp_path: Path) -> None:
    backend = resolve_memory_backend(
        "pgvector",
        pgvector_url="postgresql://user:pass@localhost:5432/clawlite",
    )

    class FakeCursor:
        def __init__(self) -> None:
            self.last_query = ""

        def execute(self, query: str) -> None:
            self.last_query = query
            if "USING hnsw" in query or "USING ivfflat" in query:
                raise RuntimeError("mixed vector dimensions")

        def fetchone(self):
            if "SELECT extversion FROM pg_extension" in self.last_query:
                return ("0.8.1",)
            if "SELECT udt_name" in self.last_query:
                return ("vector",)
            return None

        def fetchall(self):
            return []

        def close(self) -> None:
            return None

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_instance = FakeCursor()
            self.commit_calls = 0
            self.rollback_calls = 0

        def cursor(self) -> FakeCursor:
            return self.cursor_instance

        def commit(self) -> None:
            self.commit_calls += 1

        def rollback(self) -> None:
            self.rollback_calls += 1

        def close(self) -> None:
            return None

    class FakeDriver:
        @staticmethod
        def connect(url: str) -> FakeConnection:
            assert url == "postgresql://user:pass@localhost:5432/clawlite"
            return FakeConnection()

    monkeypatch.setattr(type(backend), "_detect_driver", lambda self: ("psycopg", FakeDriver))

    backend.initialize(tmp_path)

    details = backend.diagnostics()
    assert details["supported"] is True
    assert details["sql_similarity_available"] is True
    assert details["vector_index"] is False
    assert details["vector_index_kind"] == ""
    assert "pgvector ANN index unavailable" in str(details["vector_index_error"])


def test_pgvector_upsert_embedding_casts_literal_to_vector(monkeypatch) -> None:
    backend = resolve_memory_backend(
        "pgvector",
        pgvector_url="postgresql://user:pass@localhost:5432/clawlite",
    )

    class FakeCursor:
        def __init__(self) -> None:
            self.executed_query: str = ""
            self.executed_params: tuple[object, ...] = ()

        def execute(self, query: str, params: tuple[object, ...]) -> None:
            self.executed_query = query
            self.executed_params = params

        def close(self) -> None:
            return None

    class FakeConnection:
        def __init__(self) -> None:
            self.cursor_instance = FakeCursor()
            self.commit_calls = 0

        def cursor(self) -> FakeCursor:
            return self.cursor_instance

        def commit(self) -> None:
            self.commit_calls += 1

        def rollback(self) -> None:
            return None

        def close(self) -> None:
            return None

    fake_conn = FakeConnection()
    monkeypatch.setattr(type(backend), "_open_connection", lambda self: fake_conn)

    backend.upsert_embedding("alpha", [1.0, 0.0], "2026-03-01T00:00:00+00:00", "seed")

    assert "VALUES (%s, %s::vector, %s, %s)" in fake_conn.cursor_instance.executed_query
    assert fake_conn.cursor_instance.executed_params[1] == "[1.0,0.0]"
    assert fake_conn.commit_calls == 1


def test_backends_share_module_level_embedding_and_similarity_helpers(monkeypatch, tmp_path: Path) -> None:
    normalize_calls: list[object] = []
    cosine_calls: list[tuple[list[float], list[float]]] = []

    def fake_normalize(raw: object) -> list[float] | None:
        normalize_calls.append(raw)
        if raw == [0.0]:
            return [0.0]
        if isinstance(raw, str):
            return [1.0]
        if isinstance(raw, list):
            return [float(item) for item in raw]
        return None

    def fake_cosine(left: list[float], right: list[float]) -> float:
        cosine_calls.append((list(left), list(right)))
        return 0.123

    monkeypatch.setattr(memory_backend_module, "_normalize_embedding", fake_normalize)
    monkeypatch.setattr(memory_backend_module, "_cosine_similarity", fake_cosine)

    sqlite_backend = resolve_memory_backend("sqlite")
    sqlite_backend.initialize(tmp_path)
    sqlite_backend.upsert_embedding("alpha", [1.0], "2026-03-01T00:00:00+00:00", "seed")
    sqlite_hits = sqlite_backend.query_similar_embeddings([1.0], limit=1)
    assert sqlite_hits == [{"record_id": "alpha", "score": 0.123}]

    pgvector_backend = resolve_memory_backend(
        "pgvector",
        pgvector_url="postgresql://user:pass@localhost:5432/clawlite",
    )
    monkeypatch.setattr(type(pgvector_backend), "_open_connection", lambda self: None)
    monkeypatch.setattr(
        type(pgvector_backend),
        "fetch_embeddings",
        lambda self, record_ids=None, limit=5000: {"beta": [1.0]},
    )
    pgvector_hits = pgvector_backend.query_similar_embeddings([1.0], limit=1)
    assert pgvector_hits == [{"record_id": "beta", "score": 0.123}]

    assert normalize_calls
    assert cosine_calls


def test_sqlite_fts5_search_text(tmp_path):
    from clawlite.core.memory_backend import resolve_memory_backend
    backend = resolve_memory_backend("sqlite")
    backend.initialize(tmp_path)

    backend.upsert_layer_record(
        layer="item", record_id="r1",
        payload={"text": "python is a great language"},
        category="knowledge",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    backend.upsert_layer_record(
        layer="item", record_id="r2",
        payload={"text": "rust is fast and safe"},
        category="knowledge",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )

    results = backend.search_text("python language", limit=5)
    assert results, "Expected at least one FTS5 result"
    assert results[0]["record_id"] == "r1"
    assert results[0].get("score") is not None


def test_sqlite_fts5_search_text_empty_query(tmp_path):
    from clawlite.core.memory_backend import resolve_memory_backend
    backend = resolve_memory_backend("sqlite")
    backend.initialize(tmp_path)
    results = backend.search_text("", limit=5)
    assert results == []


# ── PgvectorMemoryBackend.search_text ─────────────────────────────────────────
# PgvectorMemoryBackend uses @dataclass(slots=True), so instance attributes
# are read-only. We patch at the class level and restore in teardown.

def test_pgvector_search_text_returns_empty_on_blank_query(monkeypatch) -> None:
    """search_text with blank query never opens a connection."""
    from clawlite.core.memory_backend import PgvectorMemoryBackend

    opened = []

    def _no_conn(self):  # noqa: ANN001
        opened.append(1)
        return None

    monkeypatch.setattr(PgvectorMemoryBackend, "_open_connection", _no_conn)
    backend = PgvectorMemoryBackend(pgvector_url="postgresql://fake/db")

    result = backend.search_text("", limit=5)
    assert result == []
    assert not opened, "must not open connection for blank query"


def test_pgvector_search_text_returns_empty_when_connection_unavailable(monkeypatch) -> None:
    """search_text returns [] gracefully when _open_connection returns None."""
    from clawlite.core.memory_backend import PgvectorMemoryBackend

    monkeypatch.setattr(PgvectorMemoryBackend, "_open_connection", lambda self: None)
    backend = PgvectorMemoryBackend(pgvector_url="postgresql://fake/db")

    result = backend.search_text("python language", limit=5)
    assert result == []


def test_pgvector_search_text_executes_fts_query_and_returns_hits(monkeypatch) -> None:
    """search_text executes plainto_tsquery SQL and maps rows to {record_id, score}."""
    from unittest.mock import MagicMock
    from clawlite.core.memory_backend import PgvectorMemoryBackend

    fake_cursor = MagicMock()
    fake_cursor.fetchall.return_value = [("rec_abc", 0.75), ("rec_xyz", 0.42)]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    monkeypatch.setattr(PgvectorMemoryBackend, "_open_connection", lambda self: fake_conn)
    backend = PgvectorMemoryBackend(pgvector_url="postgresql://fake/db")

    results = backend.search_text("hello world", limit=10)

    assert len(results) == 2
    assert results[0] == {"record_id": "rec_abc", "score": 0.75}
    assert results[1] == {"record_id": "rec_xyz", "score": 0.42}

    executed_sql = fake_cursor.execute.call_args[0][0]
    assert "plainto_tsquery" in executed_sql
    assert "to_tsvector" in executed_sql
    assert "ts_rank" in executed_sql


def test_pgvector_search_text_with_layer_filter(monkeypatch) -> None:
    """search_text passes layer filter to SQL when layer is specified."""
    from unittest.mock import MagicMock
    from clawlite.core.memory_backend import PgvectorMemoryBackend

    fake_cursor = MagicMock()
    fake_cursor.fetchall.return_value = [("r1", 0.9)]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    monkeypatch.setattr(PgvectorMemoryBackend, "_open_connection", lambda self: fake_conn)
    backend = PgvectorMemoryBackend(pgvector_url="postgresql://fake/db")

    results = backend.search_text("knowledge", layer="item", limit=5)

    assert len(results) == 1
    assert results[0]["record_id"] == "r1"

    executed_sql = fake_cursor.execute.call_args[0][0]
    assert "layer" in executed_sql.lower()


def test_pgvector_search_text_returns_empty_on_sql_error(monkeypatch) -> None:
    """search_text catches SQL errors and returns [] without propagating."""
    from unittest.mock import MagicMock
    from clawlite.core.memory_backend import PgvectorMemoryBackend

    fake_cursor = MagicMock()
    fake_cursor.execute.side_effect = RuntimeError("syntax error near 'plainto'")
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    monkeypatch.setattr(PgvectorMemoryBackend, "_open_connection", lambda self: fake_conn)
    backend = PgvectorMemoryBackend(pgvector_url="postgresql://fake/db")

    result = backend.search_text("query", limit=5)
    assert result == []
