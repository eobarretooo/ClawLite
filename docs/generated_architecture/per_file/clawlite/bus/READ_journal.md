# READ clawlite/bus/journal.py

## Identity

- Path: `clawlite/bus/journal.py`
- Area: `bus`
- Extension: `.py`
- Lines: 237
- Size bytes: 8012
- SHA1: `97cff0e825371592b0e41d7b5ee7895aa5ea4cd7`

## Summary

`clawlite.bus.journal` is a Python module in the `bus` area. It defines 1 class(es), led by `BusJournal`. It exposes 12 function(s), including `__init__`, `_row_to_inbound`, `_row_to_outbound`. It depends on 8 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 12
- Async functions: 0
- Constants: 1
- Internal imports: 1
- Imported by: 2
- Matching tests: 2

## Classes

- `BusJournal`

## Functions

- `__init__`
- `_row_to_inbound`
- `_row_to_outbound`
- `_utc_now`
- `ack_inbound`
- `ack_outbound`
- `append_inbound`
- `append_outbound`
- `close`
- `open`
- `unacked_inbound`
- `unacked_outbound`

## Constants

- `_SCHEMA`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/bus/journal.py`.
- Cross-reference `CONNECTIONS_journal.md` to see how this file fits into the wider system.
