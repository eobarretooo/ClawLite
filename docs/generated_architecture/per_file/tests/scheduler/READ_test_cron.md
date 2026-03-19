# READ tests/scheduler/test_cron.py

## Identity

- Path: `tests/scheduler/test_cron.py`
- Area: `tests`
- Extension: `.py`
- Lines: 855
- Size bytes: 29484
- SHA1: `bbc36c3fd6f626d2669ae3f5004bd8f8aebd985f`

## Summary

`tests.scheduler.test_cron` is a Python module in the `tests` area. It defines 1 class(es), led by `_FakePortalocker`. It exposes 42 function(s), including `_compute_next_with_failure`, `_flaky_replace`, `_slow_claim`, `_blocking`, `_blocking_on_job`, `_crash`. It depends on 10 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 31
- Async functions: 11
- Constants: 1
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Classes

- `_FakePortalocker`

## Functions

- `_compute_next_with_failure`
- `_flaky_replace`
- `_slow_claim`
- `_tracked_fsync`
- `_tracked_replace`
- `lock`
- `test_cron_cleanup_prunes_old_completed_jobs_and_expired_leases`
- `test_cron_load_recovers_corrupt_store`
- `test_cron_loop_claim_path_does_not_block_event_loop`
- `test_cron_loop_runs_due_jobs_concurrently_up_to_limit`
- `test_cron_loop_survives_callback_failure_and_tracks_job_health`
- `test_cron_loop_times_out_slow_callback_and_keeps_processing`
- `test_cron_manual_run_applies_callback_timeout`
- `test_cron_manual_run_rejects_job_with_active_lease`
- `test_cron_multi_instance_claims_due_job_once`
- `test_cron_save_retry_diagnostics_and_persisted_store`
- `test_cron_schedule_failure_isolated_per_job`
- `test_cron_service_add_and_run`
- `test_cron_service_enable_disable_and_manual_run`
- `test_cron_service_enforces_session_scope_for_mutations`
- `test_cron_service_run_once_is_auto_removed_in_loop`
- `test_cron_service_run_once_is_auto_removed_in_manual_run`
- `test_cron_service_timezone_validation_and_next_run`
- `test_cron_stale_lease_is_recovered`
- `test_cron_start_restarts_when_previous_task_crashed`
- `test_cron_status_reports_lock_backend`
- `test_cron_status_tracks_overdue_lag_for_due_job`
- `test_cron_stop_releases_owned_lease_for_immediate_restart_replay`
- `test_cron_store_lock_uses_portalocker_when_fcntl_unavailable`
- `test_cron_write_rows_durable_path_calls_replace_and_fsync`
- `unlock`
- `_blocking` (async)
- `_blocking_on_job` (async)
- `_crash` (async)
- `_on_job` (async)
- `_replayed_on_job` (async)
- `_scenario` (async)
- `_slow` (async)
- `_ticker` (async)
- `_wait_for_committed_run` (async)
- `_wait_for_runs` (async)
- `_wait_for_slow_timeout` (async)

## Constants

- `LOCK_EX`

## Notable String Markers

- `test_cron_cleanup_prunes_old_completed_jobs_and_expired_leases`
- `test_cron_load_recovers_corrupt_store`
- `test_cron_loop_claim_path_does_not_block_event_loop`
- `test_cron_loop_runs_due_jobs_concurrently_up_to_limit`
- `test_cron_loop_survives_callback_failure_and_tracks_job_health`
- `test_cron_loop_times_out_slow_callback_and_keeps_processing`
- `test_cron_manual_run_applies_callback_timeout`
- `test_cron_manual_run_rejects_job_with_active_lease`
- `test_cron_multi_instance_claims_due_job_once`
- `test_cron_save_retry_diagnostics_and_persisted_store`
- `test_cron_schedule_failure_isolated_per_job`
- `test_cron_service_add_and_run`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/scheduler/test_cron.py`.
- Cross-reference `CONNECTIONS_test_cron.md` to see how this file fits into the wider system.
