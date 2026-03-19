# READ clawlite/runtime/valkyrie.py

## Identity

- Path: `clawlite/runtime/valkyrie.py`
- Area: `runtime`
- Extension: `.py`
- Lines: 313
- Size bytes: 12055
- SHA1: `56c71783263120a637fed05acd5f14f9286f9186`

## Summary

`clawlite.runtime.valkyrie` is a Python module in the `runtime` area. It defines 1 class(es), led by `ValkyrieReaper`. It exposes 15 function(s), including `__init__`, `_audit`, `_classify`, `_archive`, `_loop`, `_maybe_await`. It depends on 5 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 9
- Async functions: 6
- Constants: 5
- Internal imports: 1
- Imported by: 2
- Matching tests: 1

## Classes

- `ValkyrieReaper`

## Functions

- `__init__`
- `_audit`
- `_classify`
- `_hours_since`
- `_list_sessions`
- `_sess_id`
- `_utc_now`
- `start`
- `status`
- `_archive` (async)
- `_loop` (async)
- `_maybe_await` (async)
- `_purge` (async)
- `reap_once` (async)
- `stop` (async)

## Constants

- `_DEAD_DAYS`
- `_DEFAULT_INTERVAL_S`
- `_HISTORY_TAIL_ON_ARCHIVE`
- `_IDLE_DAYS`
- `_VALKYRIE_RUNE`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/runtime/valkyrie.py`.
- Cross-reference `CONNECTIONS_valkyrie.md` to see how this file fits into the wider system.
