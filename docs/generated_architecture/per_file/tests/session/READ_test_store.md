# READ tests/session/test_store.py

## Identity

- Path: `tests/session/test_store.py`
- Area: `tests`
- Extension: `.py`
- Lines: 290
- Size bytes: 9920
- SHA1: `ae9ad4b62e2e439567369a71b9d86f797e99d77a`

## Summary

`tests.session.test_store` is a Python module in the `tests` area. It exposes 14 function(s), including `_boom`, `_flaky_append_once`, `test_session_store_append_retries_once_on_transient_oserror`. It depends on 7 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 14
- Async functions: 0
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Functions

- `_boom`
- `_flaky_append_once`
- `test_session_store_append_retries_once_on_transient_oserror`
- `test_session_store_batches_compaction_for_larger_limits`
- `test_session_store_compaction_preserves_order_and_latest_messages`
- `test_session_store_compaction_updates_diagnostics_counters`
- `test_session_store_compacts_to_keep_last_n_messages`
- `test_session_store_list_sessions_prefers_most_recent_mtime`
- `test_session_store_persists_jsonl`
- `test_session_store_prune_expired_deletes_stale_session_files`
- `test_session_store_prune_expired_is_noop_when_ttl_disabled`
- `test_session_store_read_messages_drops_orphan_tool_results_and_incomplete_tool_calls`
- `test_session_store_read_messages_preserves_legal_tool_history`
- `test_session_store_read_recovers_from_malformed_json_and_repairs_file`

## Notable String Markers

- `test_session_store_append_retries_once_on_transient_oserror`
- `test_session_store_batches_compaction_for_larger_limits`
- `test_session_store_compaction_preserves_order_and_latest_messages`
- `test_session_store_compaction_updates_diagnostics_counters`
- `test_session_store_compacts_to_keep_last_n_messages`
- `test_session_store_list_sessions_prefers_most_recent_mtime`
- `test_session_store_persists_jsonl`
- `test_session_store_prune_expired_deletes_stale_session_files`
- `test_session_store_prune_expired_is_noop_when_ttl_disabled`
- `test_session_store_read_messages_drops_orphan_tool_results_and_incomplete_tool_calls`
- `test_session_store_read_messages_preserves_legal_tool_history`
- `test_session_store_read_recovers_from_malformed_json_and_repairs_file`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/session/test_store.py`.
- Cross-reference `CONNECTIONS_test_store.md` to see how this file fits into the wider system.
