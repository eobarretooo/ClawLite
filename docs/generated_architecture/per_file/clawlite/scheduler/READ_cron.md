# READ clawlite/scheduler/cron.py

## Identity

- Path: `clawlite/scheduler/cron.py`
- Area: `scheduler`
- Extension: `.py`
- Lines: 1144
- Size bytes: 49759
- SHA1: `6e2a4ea16b9c6cf6c2dc8a801f74c71ec6461543`

## Summary

`clawlite.scheduler.cron` is a Python module in the `scheduler` area. It defines 1 class(es), led by `CronService`. It exposes 49 function(s), including `__init__`, `_cleanup`, `_clear_lease`, `_cancel_running_tasks`, `_loop`, `_run_claimed_job`. It depends on 18 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 41
- Async functions: 8
- Constants: 8
- Internal imports: 2
- Imported by: 5
- Matching tests: 2

## Classes

- `CronService`

## Functions

- `__init__`
- `_cleanup`
- `_clear_lease`
- `_commit_job_result`
- `_completed_job_at`
- `_compute_loop_sleep_seconds`
- `_compute_next`
- `_is_lease_active`
- `_job_from_row`
- `_load`
- `_lock_backend_name`
- `_mark_schedule_error`
- `_normalize_datetime`
- `_normalize_timezone`
- `_now`
- `_owned_job`
- `_parse_expression`
- `_path_lock`
- `_read_jobs_unlocked`
- `_read_rows_unlocked`
- `_record_cleanup`
- `_record_job_snapshot`
- `_recover_corrupt_store_unlocked`
- `_release_owned_leases`
- `_rows_to_jobs`
- `_run_cleanup_pass`
- `_save`
- `_schedule_to_expression`
- `_should_prune_completed_job`
- `_store_lock`
- `_sweep_jobs`
- `_task_snapshot`
- `_track_running_task`
- `_try_claim_due_job`
- `_try_claim_job`
- `_write_rows_unlocked`
- `enable_job`
- `get_job`
- `list_jobs`
- `remove_job`
- `status`
- `_cancel_running_tasks` (async)
- `_loop` (async)
- `_run_claimed_job` (async)
- `_save_async` (async)
- `add_job` (async)
- `run_job` (async)
- `start` (async)
- `stop` (async)

## Constants

- `DEFAULT_CALLBACK_TIMEOUT_SECONDS`
- `DEFAULT_COMPLETED_JOB_RETENTION_SECONDS`
- `_LOOP_SLEEP_MAX_SECONDS`
- `_LOOP_SLEEP_MIN_SECONDS`
- `_MAX_CLEANUP_WAIT_SECONDS`
- `_OVERDUE_THRESHOLD_SECONDS`
- `_PATH_LOCKS`
- `_PATH_LOCKS_GUARD`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/scheduler/cron.py`.
- Cross-reference `CONNECTIONS_cron.md` to see how this file fits into the wider system.
