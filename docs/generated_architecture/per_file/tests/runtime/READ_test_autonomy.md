# READ tests/runtime/test_autonomy.py

## Identity

- Path: `tests/runtime/test_autonomy.py`
- Area: `tests`
- Extension: `.py`
- Lines: 333
- Size bytes: 11184
- SHA1: `4c82e13af659385950a6a8e910d8f02779da1d1b`

## Summary

`tests.runtime.test_autonomy` is a Python module in the `tests` area. It defines 1 class(es), led by `_Clock`. It exposes 14 function(s), including `__init__`, `monotonic`, `test_autonomy_backlog_skip_increments_counter_and_skips_callback`, `_crash`, `_run`, `_scenario`. It depends on 3 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 10
- Async functions: 4
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Classes

- `_Clock`

## Functions

- `__init__`
- `monotonic`
- `test_autonomy_backlog_skip_increments_counter_and_skips_callback`
- `test_autonomy_failed_run_updates_failure_counters_and_error`
- `test_autonomy_provider_backoff_skips_until_window_expires`
- `test_autonomy_repeated_idle_snapshot_enters_no_progress_backoff`
- `test_autonomy_snapshot_change_clears_no_progress_backoff`
- `test_autonomy_start_is_idempotent_with_healthy_running_task`
- `test_autonomy_start_restarts_when_previous_task_crashed`
- `test_autonomy_success_updates_excerpt_and_cooldown_skip`
- `_crash` (async)
- `_run` (async)
- `_scenario` (async)
- `_snapshot` (async)

## Notable String Markers

- `test_autonomy_backlog_skip_increments_counter_and_skips_callback`
- `test_autonomy_failed_run_updates_failure_counters_and_error`
- `test_autonomy_provider_backoff_skips_until_window_expires`
- `test_autonomy_repeated_idle_snapshot_enters_no_progress_backoff`
- `test_autonomy_snapshot_change_clears_no_progress_backoff`
- `test_autonomy_start_is_idempotent_with_healthy_running_task`
- `test_autonomy_start_restarts_when_previous_task_crashed`
- `test_autonomy_success_updates_excerpt_and_cooldown_skip`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/runtime/test_autonomy.py`.
- Cross-reference `CONNECTIONS_test_autonomy.md` to see how this file fits into the wider system.
