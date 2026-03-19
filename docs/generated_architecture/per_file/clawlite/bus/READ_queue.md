# READ clawlite/bus/queue.py

## Identity

- Path: `clawlite/bus/queue.py`
- Area: `bus`
- Extension: `.py`
- Lines: 446
- Size bytes: 16880
- SHA1: `dceedbce222936b34ff53dc143c3dd7d0b90d16e`

## Summary

`clawlite.bus.queue` is a Python module in the `bus` area. It defines 2 class(es), led by `BusFullError`, `MessageQueue`. It exposes 25 function(s), including `__init__`, `_dead_letter_idempotency_key`, `_dead_letter_matches`, `_enqueue_dead_letter`, `close`, `connect`. It depends on 8 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 12
- Async functions: 13
- Constants: 3
- Internal imports: 1
- Imported by: 8
- Matching tests: 3

## Classes

- `BusFullError`
- `MessageQueue`

## Functions

- `__init__`
- `_dead_letter_idempotency_key`
- `_dead_letter_matches`
- `_dead_letter_recent`
- `_dequeue_dead_letter_nowait`
- `_oldest_age_seconds`
- `_prune_stop_events`
- `clear_stop`
- `dead_letter_snapshot`
- `request_stop`
- `stats`
- `stop_event`
- `_enqueue_dead_letter` (async)
- `close` (async)
- `connect` (async)
- `drain_dead_letters` (async)
- `next_dead_letter` (async)
- `next_inbound` (async)
- `next_outbound` (async)
- `publish_dead_letter` (async)
- `publish_inbound` (async)
- `publish_outbound` (async)
- `replay_dead_letters` (async)
- `restore_dead_letters` (async)
- `subscribe` (async)

## Constants

- `DEFAULT_STOP_EVENT_TTL_S`
- `DEFAULT_SUBSCRIBER_QUEUE_MAXSIZE`
- `_WILDCARD`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/bus/queue.py`.
- Cross-reference `CONNECTIONS_queue.md` to see how this file fits into the wider system.
