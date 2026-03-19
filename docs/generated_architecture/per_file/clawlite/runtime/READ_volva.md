# READ clawlite/runtime/volva.py

## Identity

- Path: `clawlite/runtime/volva.py`
- Area: `runtime`
- Extension: `.py`
- Lines: 335
- Size bytes: 13900
- SHA1: `4824dd747d11c7319c74febd742de309e0a5af09`

## Summary

`clawlite.runtime.volva` is a Python module in the `runtime` area. It defines 1 class(es), led by `VolvaOracle`. It exposes 13 function(s), including `__init__`, `_audit`, `_fetch_category_records`, `_loop`, `_tend_category`, `_tick`. It depends on 5 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 8
- Async functions: 5
- Constants: 7
- Internal imports: 1
- Imported by: 2
- Matching tests: 1

## Classes

- `VolvaOracle`

## Functions

- `__init__`
- `_audit`
- `_fetch_category_records`
- `_hours_since`
- `_identify_targets`
- `_utc_now`
- `start`
- `status`
- `_loop` (async)
- `_tend_category` (async)
- `_tick` (async)
- `stop` (async)
- `tick_from_snapshot` (async)

## Constants

- `_BACKOFF_BASE_S`
- `_BACKOFF_MAX_S`
- `_CONSOLIDATION_THRESHOLD`
- `_DEFAULT_INTERVAL_S`
- `_MAX_CATEGORIES_PER_TICK`
- `_STALE_H`
- `_VOLVA_RUNE`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/runtime/volva.py`.
- Cross-reference `CONNECTIONS_volva.md` to see how this file fits into the wider system.
