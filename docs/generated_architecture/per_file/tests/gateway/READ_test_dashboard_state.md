# READ tests/gateway/test_dashboard_state.py

## Identity

- Path: `tests/gateway/test_dashboard_state.py`
- Area: `tests`
- Extension: `.py`
- Lines: 150
- Size bytes: 5368
- SHA1: `5dc5784ee655b8fca9599113a00b2c13cf4fb144`

## Summary

`tests.gateway.test_dashboard_state` is a Python module in the `tests` area. It defines 3 class(es), led by `_FakeCron`, `_FakeSessions`, `_FakeSubagents`. It exposes 11 function(s), including `__init__`, `_restore_session_id`, `list_jobs`. It depends on 4 import statement target(s).

## Structural Data

- Classes: 3
- Functions: 11
- Async functions: 0
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Classes

- `_FakeCron`
- `_FakeSessions`
- `_FakeSubagents`

## Functions

- `__init__`
- `_restore_session_id`
- `list_jobs`
- `list_runs`
- `read`
- `status`
- `test_dashboard_channel_helpers_shape_operational_rows`
- `test_dashboard_cron_and_self_evolution_summaries`
- `test_dashboard_preview_normalizes_and_truncates`
- `test_dashboard_state_payload_assembles_sections`
- `test_recent_dashboard_sessions_builds_rows`

## Notable String Markers

- `test_dashboard_channel_helpers_shape_operational_rows`
- `test_dashboard_cron_and_self_evolution_summaries`
- `test_dashboard_preview_normalizes_and_truncates`
- `test_dashboard_state_payload_assembles_sections`
- `test_recent_dashboard_sessions_builds_rows`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/gateway/test_dashboard_state.py`.
- Cross-reference `CONNECTIONS_test_dashboard_state.md` to see how this file fits into the wider system.
