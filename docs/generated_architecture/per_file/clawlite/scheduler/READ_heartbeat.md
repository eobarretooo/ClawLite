# READ clawlite/scheduler/heartbeat.py

## Identity

- Path: `clawlite/scheduler/heartbeat.py`
- Area: `scheduler`
- Extension: `.py`
- Lines: 425
- Size bytes: 18368
- SHA1: `a32b075ed99c921505519fe06577544e54cea0fa`

## Summary

`clawlite.scheduler.heartbeat` is a Python module in the `scheduler` area. It defines 2 class(es), led by `HeartbeatDecision`, `HeartbeatService`. It exposes 19 function(s), including `__init__`, `_bound_excerpt`, `_is_heartbeat_ok_ack`, `_execute_tick`, `_loop`, `_next_trigger_source`. It depends on 10 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 12
- Async functions: 7
- Constants: 3
- Internal imports: 1
- Imported by: 5
- Matching tests: 1

## Classes

- `HeartbeatDecision`
- `HeartbeatService`

## Functions

- `__init__`
- `_bound_excerpt`
- `_is_heartbeat_ok_ack`
- `_load_state`
- `_migrate_state`
- `_reset_stale_task`
- `_save_state`
- `_task_snapshot`
- `_utc_now_iso`
- `from_result`
- `last_decision`
- `status`
- `_execute_tick` (async)
- `_loop` (async)
- `_next_trigger_source` (async)
- `_save_state_async` (async)
- `start` (async)
- `stop` (async)
- `trigger_now` (async)

## Constants

- `DEFAULT_ACTIONABLE_EXCERPT_MAX_CHARS`
- `DEFAULT_HEARTBEAT_ACK_MAX_CHARS`
- `HEARTBEAT_TOKEN`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/scheduler/heartbeat.py`.
- Cross-reference `CONNECTIONS_heartbeat.md` to see how this file fits into the wider system.
