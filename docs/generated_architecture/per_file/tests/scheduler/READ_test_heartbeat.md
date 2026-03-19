# READ tests/scheduler/test_heartbeat.py

## Identity

- Path: `tests/scheduler/test_heartbeat.py`
- Area: `tests`
- Extension: `.py`
- Lines: 402
- Size bytes: 13928
- SHA1: `313486b89b06562424985797b2c6f76fccf4ba01`

## Summary

`tests.scheduler.test_heartbeat` is a Python module in the `tests` area. It exposes 25 function(s), including `_replace_fail`, `_save_state_sync`, `test_actionable_response_updates_check_state`, `_crash`, `_flaky_next_trigger_source`, `_raise_timeout`. It depends on 5 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 19
- Async functions: 6
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Functions

- `_replace_fail`
- `_save_state_sync`
- `test_actionable_response_updates_check_state`
- `test_execute_tick_state_mutation_waits_for_tick_lock`
- `test_execute_tick_uses_async_state_save_wrapper`
- `test_heartbeat_loop_supervisor_recovers_from_outer_exceptions`
- `test_heartbeat_ok_token_semantics`
- `test_heartbeat_ok_updates_check_state`
- `test_heartbeat_service_survives_tick_errors`
- `test_heartbeat_service_ticks_and_persists_state`
- `test_heartbeat_service_tracks_wake_pressure_reasons`
- `test_heartbeat_service_trigger_now`
- `test_heartbeat_start_restarts_when_previous_task_crashed`
- `test_heartbeat_trigger_now_resets_stale_cancelled_task`
- `test_loads_legacy_flat_state_schema`
- `test_next_trigger_source_handles_asyncio_timeout`
- `test_next_trigger_source_handles_builtin_timeout`
- `test_preserves_unknown_state_keys_on_save`
- `test_save_state_atomic_replace_fail_soft`
- `_crash` (async)
- `_flaky_next_trigger_source` (async)
- `_raise_timeout` (async)
- `_save_state_async` (async)
- `_scenario` (async)
- `_tick` (async)

## Notable String Markers

- `test_actionable_response_updates_check_state`
- `test_execute_tick_state_mutation_waits_for_tick_lock`
- `test_execute_tick_uses_async_state_save_wrapper`
- `test_heartbeat_loop_supervisor_recovers_from_outer_exceptions`
- `test_heartbeat_ok_token_semantics`
- `test_heartbeat_ok_updates_check_state`
- `test_heartbeat_service_survives_tick_errors`
- `test_heartbeat_service_ticks_and_persists_state`
- `test_heartbeat_service_tracks_wake_pressure_reasons`
- `test_heartbeat_service_trigger_now`
- `test_heartbeat_start_restarts_when_previous_task_crashed`
- `test_heartbeat_trigger_now_resets_stale_cancelled_task`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/scheduler/test_heartbeat.py`.
- Cross-reference `CONNECTIONS_test_heartbeat.md` to see how this file fits into the wider system.
