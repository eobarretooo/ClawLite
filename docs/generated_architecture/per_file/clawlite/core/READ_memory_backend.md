# READ clawlite/core/memory_backend.py

## Identity

- Path: `clawlite/core/memory_backend.py`
- Area: `core`
- Extension: `.py`
- Lines: 1399
- Size bytes: 52997
- SHA1: `de2a5e6b4726a15494a36eeceb52faa5ad72910b`

## Summary

`clawlite.core.memory_backend` is a Python module in the `core` area. It defines 4 class(es), led by `MemoryBackend`, `PgvectorMemoryBackend`, `SQLiteMemoryBackend`, `SQLiteVecMemoryBackend`. It exposes 38 function(s), including `__post_init__`, `_connect`, `_cosine_similarity`. It depends on 12 import statement target(s).

## Structural Data

- Classes: 4
- Functions: 38
- Async functions: 0
- Constants: 0
- Internal imports: 0
- Imported by: 3
- Matching tests: 2

## Classes

- `MemoryBackend`
- `PgvectorMemoryBackend`
- `SQLiteMemoryBackend`
- `SQLiteVecMemoryBackend`

## Functions

- `__post_init__`
- `_connect`
- `_cosine_similarity`
- `_default_status`
- `_detect_driver`
- `_ensure_embeddings_vector_column`
- `_is_valid_pg_url`
- `_load_sqlite_vec`
- `_normalize_embedding`
- `_open_connection`
- `_probe_vector_extension`
- `_row_first_value`
- `_set_status`
- `_to_vector_literal`
- `delete_embeddings`
- `delete_layer_records`
- `delete_resource`
- `delete_ttl_entries`
- `diagnostics`
- `fetch_all_resources`
- `fetch_embeddings`
- `fetch_expired_record_ids`
- `fetch_layer_records`
- `fetch_records_by_resource`
- `fetch_resource`
- `get_ttl`
- `initialize`
- `is_supported`
- `link_record_resource`
- `name`
- `query_similar_embeddings`
- `resolve_memory_backend`
- `search_text`
- `set_ttl`
- `support_error`
- `upsert_embedding`
- `upsert_layer_record`
- `upsert_resource`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/core/memory_backend.py`.
- Cross-reference `CONNECTIONS_memory_backend.md` to see how this file fits into the wider system.
