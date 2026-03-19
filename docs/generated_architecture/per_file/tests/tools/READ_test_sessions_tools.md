# READ tests/tools/test_sessions_tools.py

## Identity

- Path: `tests/tools/test_sessions_tools.py`
- Area: `tests`
- Extension: `.py`
- Lines: 1209
- Size bytes: 45603
- SHA1: `1e5bdf0ad6486ba4551ace1f02711cc9a4c77508`

## Summary

`tests.tools.test_sessions_tools` is a Python module in the `tests` area. It defines 1 class(es), led by `MemoryStub`. It exposes 31 function(s), including `__init__`, `_resume_runner_factory`, `set_working_memory_share_scope`, `_resume_runner`, `_runner`, `_scenario`. It depends on 8 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 26
- Async functions: 5
- Constants: 0
- Internal imports: 4
- Imported by: 0
- Matching tests: 0

## Classes

- `MemoryStub`

## Functions

- `__init__`
- `_resume_runner_factory`
- `set_working_memory_share_scope`
- `test_session_status_fields`
- `test_session_status_surfaces_recent_subagents`
- `test_session_status_sweeps_expired_subagents_and_reports_counts`
- `test_sessions_history_excludes_tools_before_limit_slice`
- `test_sessions_history_include_and_exclude_tool_messages`
- `test_sessions_history_surfaces_subagent_runs_and_timeline`
- `test_sessions_list`
- `test_sessions_list_surfaces_subagent_inventory`
- `test_sessions_send_applies_continuation_context_from_memory`
- `test_sessions_send_success_and_same_session_failure`
- `test_sessions_send_timeout_returns_deterministic_failed_json`
- `test_sessions_spawn_applies_continuation_context_and_persists_metadata`
- `test_sessions_spawn_applies_explicit_working_memory_share_scope`
- `test_sessions_spawn_fails_closed_when_share_scope_is_requested_without_memory_support`
- `test_sessions_spawn_fans_out_parallel_tasks_and_surfaces_group_status`
- `test_sessions_spawn_parallel_reports_partial_failure_when_quota_is_hit`
- `test_sessions_spawn_success_and_subagents_list_kill`
- `test_subagents_kill_and_resume_are_scoped_to_current_session`
- `test_subagents_list_and_sweep_surface_lifecycle_metadata`
- `test_subagents_resume_queue_limit_does_not_consume_retry_budget`
- `test_subagents_resume_reports_partial_when_group_has_mixed_outcome`
- `test_subagents_resume_restarts_parallel_group_by_group_id`
- `test_subagents_resume_restarts_resumable_runs`
- `_resume_runner` (async)
- `_runner` (async)
- `_scenario` (async)
- `_slow_runner` (async)
- `retrieve` (async)

## Notable String Markers

- `test_session_status_fields`
- `test_session_status_surfaces_recent_subagents`
- `test_session_status_sweeps_expired_subagents_and_reports_counts`
- `test_sessions_history_excludes_tools_before_limit_slice`
- `test_sessions_history_include_and_exclude_tool_messages`
- `test_sessions_history_surfaces_subagent_runs_and_timeline`
- `test_sessions_list`
- `test_sessions_list_surfaces_subagent_inventory`
- `test_sessions_send_applies_continuation_context_from_memory`
- `test_sessions_send_success_and_same_session_failure`
- `test_sessions_send_timeout_returns_deterministic_failed_json`
- `test_sessions_spawn_applies_continuation_context_and_persists_metadata`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/tools/test_sessions_tools.py`.
- Cross-reference `CONNECTIONS_test_sessions_tools.md` to see how this file fits into the wider system.
