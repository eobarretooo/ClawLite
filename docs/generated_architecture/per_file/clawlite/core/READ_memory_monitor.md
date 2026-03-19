# READ clawlite/core/memory_monitor.py

## Identity

- Path: `clawlite/core/memory_monitor.py`
- Area: `core`
- Extension: `.py`
- Lines: 578
- Size bytes: 24931
- SHA1: `5f783302da533db38013668f5d5ad1c34593a136`

## Summary

`clawlite.core.memory_monitor` is a Python module in the `core` area. It defines 2 class(es), led by `MemoryMonitor`, `MemorySuggestion`. It exposes 33 function(s), including `__init__`, `_all_records`, `_atomic_write_pending_text`, `scan`. It depends on 13 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 32
- Async functions: 1
- Constants: 6
- Internal imports: 1
- Imported by: 7
- Matching tests: 2

## Classes

- `MemoryMonitor`
- `MemorySuggestion`

## Functions

- `__init__`
- `_all_records`
- `_atomic_write_pending_text`
- `_coerce_priority`
- `_deliverable_suggestions`
- `_delivery_route_from_source`
- `_extract_event_date`
- `_extract_tokens`
- `_flush_and_fsync`
- `_latest_delivery_timestamp`
- `_parse_time`
- `_persist_pending`
- `_read_pending_payload`
- `_retry_delay_seconds`
- `_row_failure_count`
- `_row_is_deliverable`
- `_row_status`
- `_suggestion_from_row`
- `_trigger_pending_tasks`
- `_trigger_recurring_birthdays`
- `_trigger_repeated_topics`
- `_trigger_upcoming_events`
- `_write_pending_payload`
- `deliverable`
- `mark_delivered`
- `mark_failed`
- `pending`
- `semantic_key`
- `should_deliver`
- `suggestion_id`
- `telemetry`
- `to_payload`
- `scan` (async)

## Constants

- `_BIRTHDAY_RE`
- `_DATE_RE`
- `_DONE_RE`
- `_MONTH_DAY_RE`
- `_TASK_RE`
- `_TRAVEL_RE`

## Notable String Markers

- `test_delivery_timestamp`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/core/memory_monitor.py`.
- Cross-reference `CONNECTIONS_memory_monitor.md` to see how this file fits into the wider system.
