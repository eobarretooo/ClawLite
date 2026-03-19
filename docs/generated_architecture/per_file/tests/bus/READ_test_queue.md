# READ tests/bus/test_queue.py

## Identity

- Path: `tests/bus/test_queue.py`
- Area: `tests`
- Extension: `.py`
- Lines: 357
- Size bytes: 12835
- SHA1: `d2379f501a52ad060de2366c6c40e14635938b6e`

## Summary

`tests.bus.test_queue` is a Python module in the `tests` area. It exposes 13 function(s), including `test_message_queue_dead_letter_reason_histogram_increments`, `test_message_queue_dead_letter_recent_snapshot_is_bounded_ordered_and_sanitized`, `test_message_queue_dead_letter_replay_filters_dry_run_marker_and_bounds`, `_consume_once`, `_scenario`. It depends on 4 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 11
- Async functions: 2
- Constants: 0
- Internal imports: 2
- Imported by: 0
- Matching tests: 0

## Functions

- `test_message_queue_dead_letter_reason_histogram_increments`
- `test_message_queue_dead_letter_recent_snapshot_is_bounded_ordered_and_sanitized`
- `test_message_queue_dead_letter_replay_filters_dry_run_marker_and_bounds`
- `test_message_queue_dead_letter_roundtrip`
- `test_message_queue_drain_and_restore_dead_letters_preserves_filtered_items`
- `test_message_queue_inbound_outbound_roundtrip`
- `test_message_queue_outbound_drop_when_full_is_non_blocking`
- `test_message_queue_publish_inbound_uses_snapshot_when_topics_mutate`
- `test_message_queue_stop_events_are_pruned_by_ttl`
- `test_message_queue_subscription`
- `test_message_queue_subscription_applies_backpressure_when_subscriber_queue_full`
- `_consume_once` (async)
- `_scenario` (async)

## Notable String Markers

- `test_message_queue_dead_letter_reason_histogram_increments`
- `test_message_queue_dead_letter_recent_snapshot_is_bounded_ordered_and_sanitized`
- `test_message_queue_dead_letter_replay_filters_dry_run_marker_and_bounds`
- `test_message_queue_dead_letter_roundtrip`
- `test_message_queue_drain_and_restore_dead_letters_preserves_filtered_items`
- `test_message_queue_inbound_outbound_roundtrip`
- `test_message_queue_outbound_drop_when_full_is_non_blocking`
- `test_message_queue_publish_inbound_uses_snapshot_when_topics_mutate`
- `test_message_queue_stop_events_are_pruned_by_ttl`
- `test_message_queue_subscription`
- `test_message_queue_subscription_applies_backpressure_when_subscriber_queue_full`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/bus/test_queue.py`.
- Cross-reference `CONNECTIONS_test_queue.md` to see how this file fits into the wider system.
