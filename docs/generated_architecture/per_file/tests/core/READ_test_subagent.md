# READ tests/core/test_subagent.py

## Identity

- Path: `tests/core/test_subagent.py`
- Area: `tests`
- Extension: `.py`
- Lines: 703
- Size bytes: 24298
- SHA1: `cbafa84ded2c0e52eeabe2d90813d4f103dd4b7e`

## Summary

`tests.core.test_subagent` is a Python module in the `tests` area. It exposes 30 function(s), including `_tracking_fsync`, `test_list_completed_unsynthesized_filters_status_and_metadata`, `test_mark_synthesized_persists_across_reload`, `_blocking_runner`, `_cancel_some`, `_mark_synthesized_loop`. It depends on 7 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 20
- Async functions: 10
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Functions

- `_tracking_fsync`
- `test_list_completed_unsynthesized_filters_status_and_metadata`
- `test_mark_synthesized_persists_across_reload`
- `test_orchestration_depth_blocks_at_max`
- `test_orchestration_depth_increments_on_child_spawn`
- `test_orchestration_depth_unlimited_when_zero`
- `test_orchestration_depth_zero_means_no_parent`
- `test_status_exposes_max_orchestration_depth`
- `test_subagent_manager_concurrent_spawn_cancel_and_synthesize`
- `test_subagent_manager_enforces_retry_budget_on_resume`
- `test_subagent_manager_queue_limits_and_session_quota`
- `test_subagent_manager_restart_clears_phantom_queue_entries`
- `test_subagent_manager_restores_resumable_state`
- `test_subagent_manager_resume_rejects_already_queued_run`
- `test_subagent_manager_save_state_uses_durable_atomic_write`
- `test_subagent_manager_spawn_and_list`
- `test_subagent_manager_spawn_persists_custom_metadata`
- `test_subagent_manager_status_reports_maintenance_and_heartbeat`
- `test_subagent_manager_sweeps_expired_and_orphaned_runs`
- `test_subagent_resume_clears_stale_synthesis_metadata`
- `_blocking_runner` (async)
- `_cancel_some` (async)
- `_mark_synthesized_loop` (async)
- `_resume_runner` (async)
- `_resumed_runner` (async)
- `_runner` (async)
- `_scenario` (async)
- `_slow_runner` (async)
- `_spawn_more` (async)
- `runner` (async)

## Notable String Markers

- `test_list_completed_unsynthesized_filters_status_and_metadata`
- `test_mark_synthesized_persists_across_reload`
- `test_orchestration_depth_blocks_at_max`
- `test_orchestration_depth_increments_on_child_spawn`
- `test_orchestration_depth_unlimited_when_zero`
- `test_orchestration_depth_zero_means_no_parent`
- `test_status_exposes_max_orchestration_depth`
- `test_subagent_manager_concurrent_spawn_cancel_and_synthesize`
- `test_subagent_manager_enforces_retry_budget_on_resume`
- `test_subagent_manager_queue_limits_and_session_quota`
- `test_subagent_manager_restart_clears_phantom_queue_entries`
- `test_subagent_manager_restores_resumable_state`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/core/test_subagent.py`.
- Cross-reference `CONNECTIONS_test_subagent.md` to see how this file fits into the wider system.
