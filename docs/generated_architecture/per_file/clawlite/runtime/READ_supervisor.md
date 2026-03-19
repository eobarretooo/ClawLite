# READ clawlite/runtime/supervisor.py

## Identity

- Path: `clawlite/runtime/supervisor.py`
- Area: `runtime`
- Extension: `.py`
- Lines: 464
- Size bytes: 19706
- SHA1: `70881cfda073e910f3ee8266a770d788e07e19ab`

## Summary

`clawlite.runtime.supervisor` is a Python module in the `runtime` area. It defines 3 class(es), led by `RuntimeSupervisor`, `SupervisorComponentPolicy`, `SupervisorIncident`. It exposes 22 function(s), including `__init__`, `_budget_remaining`, `_coerce_component_policy`, `_notify_incident`, `_recover_component`, `_run_loop`. It depends on 8 import statement target(s).

## Structural Data

- Classes: 3
- Functions: 15
- Async functions: 7
- Constants: 0
- Internal imports: 1
- Imported by: 3
- Matching tests: 4

## Classes

- `RuntimeSupervisor`
- `SupervisorComponentPolicy`
- `SupervisorIncident`

## Functions

- `__init__`
- `_budget_remaining`
- `_coerce_component_policy`
- `_consume_recovery_budget`
- `_ensure_component_recovery`
- `_incident_from_any`
- `_normalize_component_name`
- `_normalize_component_policies`
- `_policy_for_component`
- `_record_error`
- `_record_incident`
- `_recovery_window`
- `_resolved_cooldown_s`
- `_task_snapshot`
- `status`
- `_notify_incident` (async)
- `_recover_component` (async)
- `_run_loop` (async)
- `operator_recover_components` (async)
- `run_once` (async)
- `start` (async)
- `stop` (async)

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/runtime/supervisor.py`.
- Cross-reference `CONNECTIONS_supervisor.md` to see how this file fits into the wider system.
