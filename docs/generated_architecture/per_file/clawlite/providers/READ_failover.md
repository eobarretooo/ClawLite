# READ clawlite/providers/failover.py

## Identity

- Path: `clawlite/providers/failover.py`
- Area: `providers`
- Extension: `.py`
- Lines: 333
- Size bytes: 14140
- SHA1: `18aec5f1f8cdcada4546d1af969b690e3e3812e2`

## Summary

`clawlite.providers.failover` is a Python module in the `providers` area. It defines 3 class(es), led by `FailoverCandidate`, `FailoverCooldownError`, `FailoverProvider`. It exposes 15 function(s), including `__init__`, `_activate_cooldown`, `_all_in_cooldown_error`, `_attempt_candidate`, `complete`. It depends on 6 import statement target(s).

## Structural Data

- Classes: 3
- Functions: 13
- Async functions: 2
- Constants: 1
- Internal imports: 2
- Imported by: 3
- Matching tests: 1

## Classes

- `FailoverCandidate`
- `FailoverCooldownError`
- `FailoverProvider`

## Functions

- `__init__`
- `_activate_cooldown`
- `_all_in_cooldown_error`
- `_cooldown_duration_for_error_class`
- `_cooldown_remaining`
- `_now`
- `_sanitize`
- `_should_failover`
- `diagnostics`
- `fallback`
- `get_default_model`
- `operator_clear_suppression`
- `primary`
- `_attempt_candidate` (async)
- `complete` (async)

## Constants

- `_HARD_SUPPRESSION_S`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/providers/failover.py`.
- Cross-reference `CONNECTIONS_failover.md` to see how this file fits into the wider system.
