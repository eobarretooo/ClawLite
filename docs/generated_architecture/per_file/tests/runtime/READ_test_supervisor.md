# READ tests/runtime/test_supervisor.py

## Identity

- Path: `tests/runtime/test_supervisor.py`
- Area: `tests`
- Extension: `.py`
- Lines: 341
- Size bytes: 11325
- SHA1: `b9a4b0ff446c672a4eef3c3cfdb7b28748b9e8cf`

## Summary

`tests.runtime.test_supervisor` is a Python module in the `tests` area. It defines 1 class(es), led by `_Clock`. It exposes 17 function(s), including `__init__`, `monotonic`, `test_supervisor_component_budget_limits_recovery_attempts_per_window`, `_checks`, `_crash`, `_on_incident`. It depends on 4 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 12
- Async functions: 5
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Classes

- `_Clock`

## Functions

- `__init__`
- `monotonic`
- `test_supervisor_component_budget_limits_recovery_attempts_per_window`
- `test_supervisor_component_specific_cooldown_overrides_global_cooldown`
- `test_supervisor_cron_down_recovery_counters`
- `test_supervisor_heartbeat_recovery_then_cooldown_skip`
- `test_supervisor_operator_recover_component_bypasses_cooldown_when_forced`
- `test_supervisor_operator_recover_component_respects_budget_without_force`
- `test_supervisor_provider_circuit_open_tracks_incident_without_recovery`
- `test_supervisor_run_once_handles_check_exceptions`
- `test_supervisor_start_is_idempotent_with_healthy_running_task`
- `test_supervisor_start_restarts_when_previous_task_crashed`
- `_checks` (async)
- `_crash` (async)
- `_on_incident` (async)
- `_recover` (async)
- `_scenario` (async)

## Notable String Markers

- `test_supervisor_component_budget_limits_recovery_attempts_per_window`
- `test_supervisor_component_specific_cooldown_overrides_global_cooldown`
- `test_supervisor_cron_down_recovery_counters`
- `test_supervisor_heartbeat_recovery_then_cooldown_skip`
- `test_supervisor_operator_recover_component_bypasses_cooldown_when_forced`
- `test_supervisor_operator_recover_component_respects_budget_without_force`
- `test_supervisor_provider_circuit_open_tracks_incident_without_recovery`
- `test_supervisor_run_once_handles_check_exceptions`
- `test_supervisor_start_is_idempotent_with_healthy_running_task`
- `test_supervisor_start_restarts_when_previous_task_crashed`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/runtime/test_supervisor.py`.
- Cross-reference `CONNECTIONS_test_supervisor.md` to see how this file fits into the wider system.
