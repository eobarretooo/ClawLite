# READ clawlite/tools/process.py

## Identity

- Path: `clawlite/tools/process.py`
- Area: `tools`
- Extension: `.py`
- Lines: 378
- Size bytes: 14517
- SHA1: `ddc29473ed76cba5c9cbbf1b1c5a45e9cd0adff5`

## Summary

`clawlite.tools.process` is a Python module in the `tools` area. It defines 2 class(es), led by `ProcessSession`, `ProcessTool`. It exposes 20 function(s), including `__init__`, `_clamp_timeout_ms`, `_get_session`, `_append_output`, `_capture_stream`, `_clear`. It depends on 11 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 10
- Async functions: 10
- Constants: 5
- Internal imports: 2
- Imported by: 2
- Matching tests: 2

## Classes

- `ProcessSession`
- `ProcessTool`

## Functions

- `__init__`
- `_clamp_timeout_ms`
- `_get_session`
- `_json`
- `_list`
- `_missing_session_response`
- `_prune_finished_sessions`
- `_remove`
- `_resolve_session_id`
- `args_schema`
- `_append_output` (async)
- `_capture_stream` (async)
- `_clear` (async)
- `_kill` (async)
- `_log` (async)
- `_poll` (async)
- `_start` (async)
- `_watch_process` (async)
- `_write` (async)
- `run` (async)

## Constants

- `DEFAULT_LOG_LIMIT`
- `DEFAULT_MAX_FINISHED_SESSIONS`
- `DEFAULT_MAX_OUTPUT_CHARS`
- `MAX_POLL_WAIT_MS`
- `OUTPUT_TRUNCATION_MARKER`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/tools/process.py`.
- Cross-reference `CONNECTIONS_process.md` to see how this file fits into the wider system.
