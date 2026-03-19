# READ tests/core/test_memory_monitor.py

## Identity

- Path: `tests/core/test_memory_monitor.py`
- Area: `tests`
- Extension: `.py`
- Lines: 306
- Size bytes: 10453
- SHA1: `dd0dec909d488498255dd215f13cae1eedd78b75`

## Summary

`tests.core.test_memory_monitor` is a Python module in the `tests` area. It exposes 13 function(s), including `_deliverable_probe`, `_mark`, `_persist_probe`, `_scenario`. It depends on 9 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 12
- Async functions: 1
- Constants: 0
- Internal imports: 2
- Imported by: 0
- Matching tests: 0

## Functions

- `_deliverable_probe`
- `_mark`
- `_persist_probe`
- `_seed_history`
- `_spy_replace`
- `test_memory_monitor_dedupe_and_cooldown_controls`
- `test_memory_monitor_mark_delivered_read_modify_write_is_lock_safe`
- `test_memory_monitor_pending_persistence_and_mark_delivered`
- `test_memory_monitor_replays_failed_suggestions_after_backoff`
- `test_memory_monitor_scan_offloads_persist_and_pending_to_threads`
- `test_memory_monitor_scan_triggers_required_coverage`
- `test_memory_monitor_writes_pending_atomically`
- `_scenario` (async)

## Notable String Markers

- `test_memory_monitor_dedupe_and_cooldown_controls`
- `test_memory_monitor_mark_delivered_read_modify_write_is_lock_safe`
- `test_memory_monitor_pending_persistence_and_mark_delivered`
- `test_memory_monitor_replays_failed_suggestions_after_backoff`
- `test_memory_monitor_scan_offloads_persist_and_pending_to_threads`
- `test_memory_monitor_scan_triggers_required_coverage`
- `test_memory_monitor_writes_pending_atomically`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/core/test_memory_monitor.py`.
- Cross-reference `CONNECTIONS_test_memory_monitor.md` to see how this file fits into the wider system.
