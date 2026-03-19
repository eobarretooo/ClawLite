# READ tests/bus/test_journal.py

## Identity

- Path: `tests/bus/test_journal.py`
- Area: `tests`
- Extension: `.py`
- Lines: 219
- Size bytes: 6715
- SHA1: `597ebb49042e4e24b225219a028c4b8a61e5e3e9`

## Summary

`tests.bus.test_journal` is a Python module in the `tests` area. It exposes 12 function(s), including `test_journal_ack_removes_from_replay`, `test_journal_append_and_replay_inbound`, `test_journal_closed_does_not_crash`, `collect`, `test_bus_full_blocks_without_nowait`, `test_bus_full_error_raised_on_nowait`. It depends on 7 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 5
- Async functions: 7
- Constants: 0
- Internal imports: 3
- Imported by: 0
- Matching tests: 0

## Functions

- `test_journal_ack_removes_from_replay`
- `test_journal_append_and_replay_inbound`
- `test_journal_closed_does_not_crash`
- `test_journal_outbound_append_and_ack`
- `test_journal_survives_restart`
- `collect` (async)
- `test_bus_full_blocks_without_nowait` (async)
- `test_bus_full_error_raised_on_nowait` (async)
- `test_queue_journal_replay_on_restart` (async)
- `test_queue_with_journal_acks_on_consume` (async)
- `test_queue_with_journal_acks_outbound_on_consume` (async)
- `test_wildcard_subscription_receives_all_channels` (async)

## Notable String Markers

- `test_bus_full_blocks_without_nowait`
- `test_bus_full_error_raised_on_nowait`
- `test_journal_ack_removes_from_replay`
- `test_journal_append_and_replay_inbound`
- `test_journal_closed_does_not_crash`
- `test_journal_outbound_append_and_ack`
- `test_journal_survives_restart`
- `test_queue_journal_replay_on_restart`
- `test_queue_with_journal_acks_on_consume`
- `test_queue_with_journal_acks_outbound_on_consume`
- `test_wildcard_subscription_receives_all_channels`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/bus/test_journal.py`.
- Cross-reference `CONNECTIONS_test_journal.md` to see how this file fits into the wider system.
