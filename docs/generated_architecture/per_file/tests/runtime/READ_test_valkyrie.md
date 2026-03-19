# READ tests/runtime/test_valkyrie.py

## Identity

- Path: `tests/runtime/test_valkyrie.py`
- Area: `tests`
- Extension: `.py`
- Lines: 133
- Size bytes: 4737
- SHA1: `7f8fac0885c0397b3e473aa8df073327d5ee2e4d`

## Summary

`tests.runtime.test_valkyrie` is a Python module in the `tests` area. It defines 1 class(es), led by `FakeStore`. It exposes 15 function(s), including `__init__`, `_make_store`, `archive_session`, `test_reap_once_archives_idle_sessions`, `test_reap_once_empty_store`, `test_reap_once_increments_stats`. It depends on 4 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 11
- Async functions: 4
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Classes

- `FakeStore`

## Functions

- `__init__`
- `_make_store`
- `archive_session`
- `list_sessions`
- `purge_session`
- `test_archived_session_purged_after_dead_window`
- `test_fresh_session_skipped`
- `test_idle_session_archived`
- `test_purged_session_skipped`
- `test_status_fields`
- `test_very_old_session_purged`
- `test_reap_once_archives_idle_sessions` (async)
- `test_reap_once_empty_store` (async)
- `test_reap_once_increments_stats` (async)
- `test_reap_once_purges_very_old` (async)

## Notable String Markers

- `test_archived_session_purged_after_dead_window`
- `test_fresh_session_skipped`
- `test_idle_session_archived`
- `test_purged_session_skipped`
- `test_reap_once_archives_idle_sessions`
- `test_reap_once_empty_store`
- `test_reap_once_increments_stats`
- `test_reap_once_purges_very_old`
- `test_status_fields`
- `test_very_old_session_purged`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/runtime/test_valkyrie.py`.
- Cross-reference `CONNECTIONS_test_valkyrie.md` to see how this file fits into the wider system.
