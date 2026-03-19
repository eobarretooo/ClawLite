# READ tests/runtime/test_autonomy_wake.py

## Identity

- Path: `tests/runtime/test_autonomy_wake.py`
- Area: `tests`
- Extension: `.py`
- Lines: 403
- Size bytes: 14943
- SHA1: `fe53a22208118f32f12bccc1fa61d8a1f32f79bd`

## Summary

`tests.runtime.test_autonomy_wake` is a Python module in the `tests` area. It exposes 11 function(s), including `test_autonomy_wake_backpressure_returns_fallback_for_new_key`, `test_autonomy_wake_coalesces_same_key_and_shares_result`, `test_autonomy_wake_heartbeat_replace_latest_drops_stale_payload_keys`, `_first_on_wake`, `_on_wake`, `_restored_on_wake`. It depends on 5 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 7
- Async functions: 4
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Functions

- `test_autonomy_wake_backpressure_returns_fallback_for_new_key`
- `test_autonomy_wake_coalesces_same_key_and_shares_result`
- `test_autonomy_wake_heartbeat_replace_latest_drops_stale_payload_keys`
- `test_autonomy_wake_kind_quota_reserves_room_for_heartbeat`
- `test_autonomy_wake_prioritizes_high_before_low_after_blocker`
- `test_autonomy_wake_replays_pending_entries_from_journal_after_restart`
- `test_autonomy_wake_upgrades_queued_priority_and_payload_on_coalesce`
- `_first_on_wake` (async)
- `_on_wake` (async)
- `_restored_on_wake` (async)
- `_scenario` (async)

## Notable String Markers

- `test_autonomy_wake_backpressure_returns_fallback_for_new_key`
- `test_autonomy_wake_coalesces_same_key_and_shares_result`
- `test_autonomy_wake_heartbeat_replace_latest_drops_stale_payload_keys`
- `test_autonomy_wake_kind_quota_reserves_room_for_heartbeat`
- `test_autonomy_wake_prioritizes_high_before_low_after_blocker`
- `test_autonomy_wake_replays_pending_entries_from_journal_after_restart`
- `test_autonomy_wake_upgrades_queued_priority_and_payload_on_coalesce`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/runtime/test_autonomy_wake.py`.
- Cross-reference `CONNECTIONS_test_autonomy_wake.md` to see how this file fits into the wider system.
