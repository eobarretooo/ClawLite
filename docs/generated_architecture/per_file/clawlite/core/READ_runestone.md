# READ clawlite/core/runestone.py

## Identity

- Path: `clawlite/core/runestone.py`
- Area: `core`
- Extension: `.py`
- Lines: 301
- Size bytes: 10535
- SHA1: `770bed7fed7f8c2707b66d7796f414642db030de`

## Summary

`clawlite.core.runestone` is a Python module in the `core` area. It defines 2 class(es), led by `RunestoneLog`, `RunestoneRecord`. It exposes 13 function(s), including `__init__`, `_hash_record`, `_restore_state`. It depends on 8 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 13
- Async functions: 0
- Constants: 3
- Internal imports: 0
- Imported by: 5
- Matching tests: 1

## Classes

- `RunestoneLog`
- `RunestoneRecord`

## Functions

- `__init__`
- `_hash_record`
- `_restore_state`
- `_rotate`
- `_utc_now`
- `_write_line`
- `append`
- `audit`
- `set_on_append`
- `set_runestone`
- `tail`
- `to_dict`
- `verify_chain`

## Constants

- `_GENESIS_PREV`
- `_MAX_FILE_BYTES`
- `_RUNE_EVENT`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/core/runestone.py`.
- Cross-reference `CONNECTIONS_runestone.md` to see how this file fits into the wider system.
