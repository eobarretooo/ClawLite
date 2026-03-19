# READ tests/core/test_memory_backend.py

## Identity

- Path: `tests/core/test_memory_backend.py`
- Area: `tests`
- Extension: `.py`
- Lines: 658
- Size bytes: 23026
- SHA1: `554c2227137ba9c31fbe193e1e160c9fe79fd57e`

## Summary

`tests.core.test_memory_backend` is a Python module in the `tests` area. It defines 6 class(es), led by `BrokenConnection`, `BrokenCursor`, `FakeConnection`, `FakeCursor`. It exposes 36 function(s), including `__init__`, `_fake_connect`, `_no_conn`. It depends on 6 import statement target(s).

## Structural Data

- Classes: 6
- Functions: 36
- Async functions: 0
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Classes

- `BrokenConnection`
- `BrokenCursor`
- `FakeConnection`
- `FakeCursor`
- `FakeDriver`
- `FakeResult`

## Functions

- `__init__`
- `_fake_connect`
- `_no_conn`
- `close`
- `commit`
- `connect`
- `cursor`
- `execute`
- `fail_if_fallback_called`
- `fake_cosine`
- `fake_import_module`
- `fake_normalize`
- `fetchall`
- `fetchone`
- `rollback`
- `test_backends_share_module_level_embedding_and_similarity_helpers`
- `test_pgvector_backend_remains_graceful_when_unsupported`
- `test_pgvector_initialize_migrates_embedding_column_to_vector`
- `test_pgvector_query_similar_embeddings_falls_back_when_sql_fails`
- `test_pgvector_query_similar_embeddings_uses_sql_path`
- `test_pgvector_search_text_executes_fts_query_and_returns_hits`
- `test_pgvector_search_text_returns_empty_on_blank_query`
- `test_pgvector_search_text_returns_empty_on_sql_error`
- `test_pgvector_search_text_returns_empty_when_connection_unavailable`
- `test_pgvector_search_text_with_layer_filter`
- `test_pgvector_support_detection_reports_missing_vector_extension`
- `test_pgvector_support_detection_requires_connection_and_vector_extension`
- `test_pgvector_support_detection_requires_valid_url_and_driver`
- `test_pgvector_upsert_embedding_casts_literal_to_vector`
- `test_sqlite_embedding_roundtrip`
- `test_sqlite_fts5_search_text`
- `test_sqlite_fts5_search_text_empty_query`
- `test_sqlite_memory_backend_roundtrip`
- `test_sqlite_query_similar_embeddings_returns_best_match`
- `test_sqlite_vec_backend_falls_back_to_sqlite_when_extension_unavailable`
- `test_sqlite_vec_backend_uses_sql_distance_when_extension_available`

## Notable String Markers

- `test_backends_share_module_level_embedding_and_similarity_helpers`
- `test_pgvector_backend_remains_graceful_when_unsupported`
- `test_pgvector_initialize_migrates_embedding_column_to_vector`
- `test_pgvector_query_similar_embeddings_falls_back_when_sql_fails`
- `test_pgvector_query_similar_embeddings_uses_sql_path`
- `test_pgvector_search_text_executes_fts_query_and_returns_hits`
- `test_pgvector_search_text_returns_empty_on_blank_query`
- `test_pgvector_search_text_returns_empty_on_sql_error`
- `test_pgvector_search_text_returns_empty_when_connection_unavailable`
- `test_pgvector_search_text_with_layer_filter`
- `test_pgvector_support_detection_reports_missing_vector_extension`
- `test_pgvector_support_detection_requires_connection_and_vector_extension`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/core/test_memory_backend.py`.
- Cross-reference `CONNECTIONS_test_memory_backend.md` to see how this file fits into the wider system.
