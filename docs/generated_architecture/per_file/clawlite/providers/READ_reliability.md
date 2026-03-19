# READ clawlite/providers/reliability.py

## Identity

- Path: `clawlite/providers/reliability.py`
- Area: `providers`
- Extension: `.py`
- Lines: 128
- Size bytes: 3985
- SHA1: `27425be929205028462a531ec9ccf1d13373249e`

## Summary

`clawlite.providers.reliability` is a Python module in the `providers` area. It defines 1 class(es), led by `ReliabilitySettings`. It exposes 5 function(s), including `classify_provider_error`, `is_quota_429_error`, `is_retryable_error`. It depends on 4 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 5
- Async functions: 0
- Constants: 1
- Internal imports: 0
- Imported by: 7
- Matching tests: 1

## Classes

- `ReliabilitySettings`

## Functions

- `classify_provider_error`
- `is_quota_429_error`
- `is_retryable_error`
- `parse_http_status`
- `parse_retry_after_seconds`

## Constants

- `QUOTA_429_SIGNALS`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/providers/reliability.py`.
- Cross-reference `CONNECTIONS_reliability.md` to see how this file fits into the wider system.
