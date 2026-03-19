# READ tests/bus/test_redis_queue.py

## Identity

- Path: `tests/bus/test_redis_queue.py`
- Area: `tests`
- Extension: `.py`
- Lines: 66
- Size bytes: 2237
- SHA1: `e053a381ee3ba01a8c4b1f91eefa69b8b82cd53e`

## Summary

`tests.bus.test_redis_queue` is a Python module in the `tests` area. It defines 1 class(es), led by `_FakeRedisListClient`. It exposes 7 function(s), including `__init__`, `test_redis_message_queue_roundtrip_and_stats`, `_scenario`, `aclose`, `blpop`. It depends on 5 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 2
- Async functions: 5
- Constants: 0
- Internal imports: 2
- Imported by: 0
- Matching tests: 0

## Classes

- `_FakeRedisListClient`

## Functions

- `__init__`
- `test_redis_message_queue_roundtrip_and_stats`
- `_scenario` (async)
- `aclose` (async)
- `blpop` (async)
- `ping` (async)
- `rpush` (async)

## Notable String Markers

- `test_redis_message_queue_roundtrip_and_stats`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/bus/test_redis_queue.py`.
- Cross-reference `CONNECTIONS_test_redis_queue.md` to see how this file fits into the wider system.
