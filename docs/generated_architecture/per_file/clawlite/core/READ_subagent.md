# READ clawlite/core/subagent.py

## Identity

- Path: `clawlite/core/subagent.py`
- Area: `core`
- Extension: `.py`
- Lines: 964
- Size bytes: 39197
- SHA1: `2c704d09e8f172908640bff40a529564e85b6a4e`

## Summary

`clawlite.core.subagent` is a Python module in the `core` area. It defines 3 class(es), led by `SubagentLimitError`, `SubagentManager`, `SubagentRun`. It exposes 50 function(s), including `__init__`, `_bind_loop`, `_cancel_locked`, `_worker`, `cancel_async`, `cancel_session_async`. It depends on 10 import statement target(s).

## Structural Data

- Classes: 3
- Functions: 43
- Async functions: 7
- Constants: 2
- Internal imports: 0
- Imported by: 11
- Matching tests: 3

## Classes

- `SubagentLimitError`
- `SubagentManager`
- `SubagentRun`

## Functions

- `__init__`
- `_bind_loop`
- `_cancel_locked`
- `_clear_synthesis_metadata`
- `_default_expires_at`
- `_drain_queue_locked`
- `_empty_sweep_stats`
- `_ensure_limits`
- `_ensure_run_defaults`
- `_from_payload`
- `_load_state`
- `_mark_queued`
- `_mark_running`
- `_mark_terminal`
- `_metadata_int`
- `_normalize_run_metadata`
- `_orchestration_depth`
- `_parse_utc`
- `_prune_completed_locked`
- `_remove_from_queue_locked`
- `_run_heartbeat_source`
- `_run_is_expired`
- `_run_is_stale`
- `_run_sync`
- `_running_count`
- `_save_state`
- `_session_outstanding`
- `_start_worker_locked`
- `_sweep_locked`
- `_sync_retry_metadata`
- `_to_payload`
- `_touch_run_locked`
- `_utc_now`
- `cancel`
- `cancel_session`
- `get_run`
- `list_completed_unsynthesized`
- `list_resumable_runs`
- `list_runs`
- `maintenance_interval_seconds`
- `mark_synthesized`
- `status`
- `sweep`
- `_worker` (async)
- `cancel_async` (async)
- `cancel_session_async` (async)
- `mark_synthesized_async` (async)
- `resume` (async)
- `spawn` (async)
- `sweep_async` (async)

## Constants

- `_MAX_COMPLETED_RUNS`
- `_T`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/core/subagent.py`.
- Cross-reference `CONNECTIONS_subagent.md` to see how this file fits into the wider system.
