# READ clawlite/tools/sessions.py

## Identity

- Path: `clawlite/tools/sessions.py`
- Area: `tools`
- Extension: `.py`
- Lines: 1190
- Size bytes: 44703
- SHA1: `79291f7fdfb449d221a22d05d225ab87910de022`

## Summary

`clawlite.tools.sessions` is a Python module in the `tools` area. It defines 7 class(es), led by `SessionStatusTool`, `SessionsHistoryTool`, `SessionsListTool`, `SessionsSendTool`. It exposes 33 function(s), including `__init__`, `_accepts_parameter`, `_apply_continuation_context`, `_lookup_continuation_context`, `_target_runner`, `run`. It depends on 11 import statement target(s).

## Structural Data

- Classes: 7
- Functions: 30
- Async functions: 3
- Constants: 0
- Internal imports: 3
- Imported by: 3
- Matching tests: 2

## Classes

- `SessionStatusTool`
- `SessionsHistoryTool`
- `SessionsListTool`
- `SessionsSendTool`
- `SessionsSpawnTool`
- `SubagentsTool`
- `_ContinuationContext`

## Functions

- `__init__`
- `_accepts_parameter`
- `_apply_continuation_context`
- `_coerce_bool`
- `_coerce_limit`
- `_coerce_string_list`
- `_coerce_timeout`
- `_compact`
- `_continuation_from_metadata`
- `_continuation_payload`
- `_count_session_messages`
- `_default_target_session_ids`
- `_json`
- `_last_message_preview`
- `_merge_session_timeline`
- `_message_timeline_event`
- `_parallel_group_id`
- `_parallel_group_summaries`
- `_preview`
- `_read_session_messages`
- `_recent_subagent_runs`
- `_resolve_session_id`
- `_run_to_payload`
- `_session_file_path`
- `_subagent_status_counts`
- `_subagent_timeline_event`
- `_timeline_timestamp`
- `applied`
- `args_schema`
- `build_task_with_continuation_metadata`
- `_lookup_continuation_context` (async)
- `_target_runner` (async)
- `run` (async)

## Notable String Markers

- `test_subagent`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/tools/sessions.py`.
- Cross-reference `CONNECTIONS_sessions.md` to see how this file fits into the wider system.
