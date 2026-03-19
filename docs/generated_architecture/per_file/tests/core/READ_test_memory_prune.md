# READ tests/core/test_memory_prune.py

## Identity

- Path: `tests/core/test_memory_prune.py`
- Area: `tests`
- Extension: `.py`
- Lines: 146
- Size bytes: 4932
- SHA1: `f2bc2f78b8dd15868da7ad19d348e2c0f6ce63e2`

## Summary

`tests.core.test_memory_prune` is a Python module in the `tests` area. It exposes 5 function(s), including `_flush_and_fsync`, `_locked_file`, `test_cleanup_expired_ephemeral_records_collects_scope_rows_and_updates_audit`. It depends on 7 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 5
- Async functions: 0
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Functions

- `_flush_and_fsync`
- `_locked_file`
- `test_cleanup_expired_ephemeral_records_collects_scope_rows_and_updates_audit`
- `test_prune_item_and_category_layers_rewrites_item_payload_and_summary`
- `test_prune_jsonl_records_for_ids_keeps_invalid_lines_and_deletes_matches`

## Notable String Markers

- `test_cleanup_expired_ephemeral_records_collects_scope_rows_and_updates_audit`
- `test_prune_item_and_category_layers_rewrites_item_payload_and_summary`
- `test_prune_jsonl_records_for_ids_keeps_invalid_lines_and_deletes_matches`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/core/test_memory_prune.py`.
- Cross-reference `CONNECTIONS_test_memory_prune.md` to see how this file fits into the wider system.
