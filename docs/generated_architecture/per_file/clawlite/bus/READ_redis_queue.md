# READ clawlite/bus/redis_queue.py

## Identity

- Path: `clawlite/bus/redis_queue.py`
- Area: `bus`
- Extension: `.py`
- Lines: 164
- Size bytes: 6141
- SHA1: `5cadbdf879633a09b8d12e762bf0c62e71c3739b`

## Summary

`clawlite.bus.redis_queue` is a Python module in the `bus` area. It defines 1 class(es), led by `RedisMessageQueue`. It exposes 13 function(s), including `__init__`, `_build_client`, `_coerce_blpop_payload`, `close`, `connect`, `next_inbound`. It depends on 8 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 7
- Async functions: 6
- Constants: 0
- Internal imports: 2
- Imported by: 3
- Matching tests: 3

## Classes

- `RedisMessageQueue`

## Functions

- `__init__`
- `_build_client`
- `_coerce_blpop_payload`
- `_ensure_client`
- `inbound_key`
- `outbound_key`
- `stats`
- `close` (async)
- `connect` (async)
- `next_inbound` (async)
- `next_outbound` (async)
- `publish_inbound` (async)
- `publish_outbound` (async)

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/bus/redis_queue.py`.
- Cross-reference `CONNECTIONS_redis_queue.md` to see how this file fits into the wider system.
