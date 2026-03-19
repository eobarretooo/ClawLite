# READ tests/runtime/test_volva.py

## Identity

- Path: `tests/runtime/test_volva.py`
- Area: `tests`
- Extension: `.py`
- Lines: 184
- Size bytes: 5843
- SHA1: `7ac67182e6a15f88a8d46fd5b7b1e2ad3a7651bb`

## Summary

`tests.runtime.test_volva` is a Python module in the `tests` area. It defines 2 class(es), led by `FakeConsolidator`, `FakeMemory`. It exposes 17 function(s), including `__init__`, `_make_consolidator`, `_make_memory`, `consolidate`, `fake_purge`, `purge_decayed`. It depends on 4 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 10
- Async functions: 7
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Classes

- `FakeConsolidator`
- `FakeMemory`

## Functions

- `__init__`
- `_make_consolidator`
- `_make_memory`
- `fake_recall`
- `list_categories`
- `test_identify_falls_back_to_memory_store`
- `test_identify_no_targets_empty_snapshot`
- `test_identify_oversize_from_muninn_and_meta`
- `test_identify_stale_from_muninn`
- `test_status_fields`
- `consolidate` (async)
- `fake_purge` (async)
- `purge_decayed` (async)
- `test_max_categories_per_tick_respected` (async)
- `test_tick_consolidates_oversize_category` (async)
- `test_tick_no_targets_logs_healthy` (async)
- `test_tick_prunes_stale_category` (async)

## Notable String Markers

- `test_identify_falls_back_to_memory_store`
- `test_identify_no_targets_empty_snapshot`
- `test_identify_oversize_from_muninn_and_meta`
- `test_identify_stale_from_muninn`
- `test_max_categories_per_tick_respected`
- `test_status_fields`
- `test_tick_consolidates_oversize_category`
- `test_tick_no_targets_logs_healthy`
- `test_tick_prunes_stale_category`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/runtime/test_volva.py`.
- Cross-reference `CONNECTIONS_test_volva.md` to see how this file fits into the wider system.
