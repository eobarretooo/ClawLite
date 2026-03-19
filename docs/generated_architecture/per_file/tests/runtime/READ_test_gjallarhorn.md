# READ tests/runtime/test_gjallarhorn.py

## Identity

- Path: `tests/runtime/test_gjallarhorn.py`
- Area: `tests`
- Extension: `.py`
- Lines: 168
- Size bytes: 6401
- SHA1: `73119e68037dd445cef939609e8136a7dc0c02b3`

## Summary

`tests.runtime.test_gjallarhorn` is a Python module in the `tests` area. It exposes 16 function(s), including `_make_horn`, `test_status_fields`, `fake_send`, `test_autonomy_below_threshold_no_alert`, `test_autonomy_errors_trigger_alert`. It depends on 4 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 2
- Async functions: 14
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Functions

- `_make_horn`
- `test_status_fields`
- `fake_send` (async)
- `test_autonomy_below_threshold_no_alert` (async)
- `test_autonomy_errors_trigger_alert` (async)
- `test_below_threshold_no_alert` (async)
- `test_block_events_accumulate` (async)
- `test_consecutive_high_huginn_triggers_alert` (async)
- `test_cooldown_suppresses_repeat_alerts` (async)
- `test_medium_priority_does_not_trigger` (async)
- `test_non_block_events_ignored` (async)
- `test_non_high_resets_counter` (async)
- `test_ring_no_target_no_send` (async)
- `test_ring_sends_to_target` (async)
- `test_volva_failure_triggers_alert` (async)
- `test_volva_single_error_no_alert` (async)

## Notable String Markers

- `test_autonomy_below_threshold_no_alert`
- `test_autonomy_errors_trigger_alert`
- `test_below_threshold_no_alert`
- `test_block_events_accumulate`
- `test_consecutive_high_huginn_triggers_alert`
- `test_cooldown_suppresses_repeat_alerts`
- `test_medium_priority_does_not_trigger`
- `test_non_block_events_ignored`
- `test_non_high_resets_counter`
- `test_reason`
- `test_ring_no_target_no_send`
- `test_ring_sends_to_target`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/runtime/test_gjallarhorn.py`.
- Cross-reference `CONNECTIONS_test_gjallarhorn.md` to see how this file fits into the wider system.
