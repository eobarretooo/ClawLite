# READ clawlite/session/store.py

## Identity

- Path: `clawlite/session/store.py`
- Area: `session`
- Extension: `.py`
- Lines: 514
- Size bytes: 20303
- SHA1: `38a05ef241084dc7d620ba5ba4aa78a796100561`

## Summary

`clawlite.session.store` is a Python module in the `session` area. It defines 2 class(es), led by `SessionMessage`, `SessionStore`. It exposes 26 function(s), including `__init__`, `_append_once`, `_atomic_rewrite`. It depends on 9 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 26
- Async functions: 0
- Constants: 0
- Internal imports: 0
- Imported by: 7
- Matching tests: 1

## Classes

- `SessionMessage`
- `SessionStore`

## Functions

- `__init__`
- `_append_once`
- `_atomic_rewrite`
- `_compact_session_file`
- `_filter_assistant_tool_calls`
- `_get_line_estimate`
- `_legacy_safe_session_id`
- `_legalize_transcript_rows`
- `_maybe_compact_session_file`
- `_metadata_allows_empty_content`
- `_normalize_tool_calls`
- `_overflow_budget`
- `_path`
- `_payload_to_message_row`
- `_repair_file`
- `_restore_session_id`
- `_safe_session_id`
- `_utc_now`
- `append`
- `delete`
- `diagnostics`
- `flush_pending`
- `list_sessions`
- `prune_expired`
- `read`
- `read_messages`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/session/store.py`.
- Cross-reference `CONNECTIONS_store.md` to see how this file fits into the wider system.
