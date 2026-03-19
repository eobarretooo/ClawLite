# READ clawlite/gateway/autonomy_notice.py

## Identity

- Path: `clawlite/gateway/autonomy_notice.py`
- Area: `gateway`
- Extension: `.py`
- Lines: 220
- Size bytes: 6261
- SHA1: `13784de12a75ad17ca32d2af91e8b88a4e4baeca`

## Summary

`clawlite.gateway.autonomy_notice` is a Python module in the `gateway` area. It exposes 5 function(s), including `_record_autonomy_event`, `default_heartbeat_route`, `latest_route_from_history_tail`, `latest_memory_route`, `send_autonomy_notice`. It depends on 8 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 3
- Async functions: 2
- Constants: 1
- Internal imports: 2
- Imported by: 2
- Matching tests: 1

## Functions

- `_record_autonomy_event`
- `default_heartbeat_route`
- `latest_route_from_history_tail`
- `latest_memory_route` (async)
- `send_autonomy_notice` (async)

## Constants

- `LATEST_MEMORY_ROUTE_CACHE_TTL_S`

## Notable String Markers

- `test_memory_route`
- `test_route`
- `test_route_from_history_tail`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/gateway/autonomy_notice.py`.
- Cross-reference `CONNECTIONS_autonomy_notice.md` to see how this file fits into the wider system.
