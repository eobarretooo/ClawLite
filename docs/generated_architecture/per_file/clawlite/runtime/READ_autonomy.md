# READ clawlite/runtime/autonomy.py

## Identity

- Path: `clawlite/runtime/autonomy.py`
- Area: `runtime`
- Extension: `.py`
- Lines: 865
- Size bytes: 35992
- SHA1: `712d9b3ee79b094e56d6e7206caf14a76562ace1`

## Summary

`clawlite.runtime.autonomy` is a Python module in the `runtime` area. It defines 4 class(es), led by `AutonomyService`, `AutonomyWakeCoordinator`, `_WakeKindPolicy`, `_WakeQueueEntry`. It exposes 32 function(s), including `__init__`, `_build_kind_policies`, `_classify_run_error`, `_persist_journal_locked`, `_read_snapshot`, `_restore_journal_locked`. It depends on 12 import statement target(s).

## Structural Data

- Classes: 4
- Functions: 23
- Async functions: 9
- Constants: 0
- Internal imports: 1
- Imported by: 3
- Matching tests: 4

## Classes

- `AutonomyService`
- `AutonomyWakeCoordinator`
- `_WakeKindPolicy`
- `_WakeQueueEntry`

## Functions

- `__init__`
- `_build_kind_policies`
- `_classify_run_error`
- `_clear_no_progress`
- `_consume_background_future`
- `_excerpt`
- `_journal_rows_locked`
- `_kind_limits_status`
- `_kind_policy_status`
- `_merge_payload_for_policy`
- `_no_progress_backoff_s`
- `_pending_by_kind_status`
- `_pending_count_for_kind`
- `_policy_for_kind`
- `_read_journal_rows`
- `_stable_signature`
- `_task_snapshot`
- `_track_kind`
- `_track_no_progress`
- `_trim_snapshot`
- `_utc_now_iso`
- `_write_journal_rows`
- `status`
- `_persist_journal_locked` (async)
- `_read_snapshot` (async)
- `_restore_journal_locked` (async)
- `_run_loop` (async)
- `_worker_loop` (async)
- `run_once` (async)
- `start` (async)
- `stop` (async)
- `submit` (async)

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/runtime/autonomy.py`.
- Cross-reference `CONNECTIONS_autonomy.md` to see how this file fits into the wider system.
