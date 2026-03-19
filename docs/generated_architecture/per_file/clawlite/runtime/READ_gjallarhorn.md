# READ clawlite/runtime/gjallarhorn.py

## Identity

- Path: `clawlite/runtime/gjallarhorn.py`
- Area: `runtime`
- Extension: `.py`
- Lines: 262
- Size bytes: 11707
- SHA1: `6293c80d1bf35e52cba865bf7580580843fc2e8e`

## Summary

`clawlite.runtime.gjallarhorn` is a Python module in the `runtime` area. It defines 1 class(es), led by `GjallarhornWatch`. It exposes 13 function(s), including `__init__`, `_count_recent_blocks`, `_utc_now`, `_idle_loop`, `_maybe_ring`, `ring`. It depends on 6 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 9
- Async functions: 4
- Constants: 7
- Internal imports: 1
- Imported by: 2
- Matching tests: 1

## Classes

- `GjallarhornWatch`

## Functions

- `__init__`
- `_count_recent_blocks`
- `_utc_now`
- `observe_autonomy`
- `observe_ravens`
- `observe_runestone`
- `observe_volva`
- `start`
- `status`
- `_idle_loop` (async)
- `_maybe_ring` (async)
- `ring` (async)
- `stop` (async)

## Constants

- `_AUTONOMY_ERR_THRESHOLD`
- `_BLOCK_THRESHOLD`
- `_BLOCK_WINDOW_S`
- `_COOLDOWN_S`
- `_GJALLARHORN_RUNE`
- `_HIGH_TICK_THRESHOLD`
- `_VOLVA_FAIL_THRESHOLD`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/runtime/gjallarhorn.py`.
- Cross-reference `CONNECTIONS_gjallarhorn.md` to see how this file fits into the wider system.
