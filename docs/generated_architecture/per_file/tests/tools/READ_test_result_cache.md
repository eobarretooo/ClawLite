# READ tests/tools/test_result_cache.py

## Identity

- Path: `tests/tools/test_result_cache.py`
- Area: `tests`
- Extension: `.py`
- Lines: 121
- Size bytes: 3555
- SHA1: `c5c50dc91b91fdb11363d4eedd332cfff31e8cea`

## Summary

`tests.tools.test_result_cache` is a Python module in the `tests` area. It defines 2 class(es), led by `CacheableTool`, `NonCacheableTool`. It exposes 9 function(s), including `__init__`, `args_schema`, `test_cache_key_is_consistent`, `run`, `test_cacheable_tool_different_args_not_cached`, `test_cacheable_tool_second_call_uses_cache`. It depends on 8 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 5
- Async functions: 4
- Constants: 0
- Internal imports: 2
- Imported by: 0
- Matching tests: 0

## Classes

- `CacheableTool`
- `NonCacheableTool`

## Functions

- `__init__`
- `args_schema`
- `test_cache_key_is_consistent`
- `test_cache_lru_eviction`
- `test_cache_ttl_expiry`
- `run` (async)
- `test_cacheable_tool_different_args_not_cached` (async)
- `test_cacheable_tool_second_call_uses_cache` (async)
- `test_non_cacheable_tool_always_calls_run` (async)

## Notable String Markers

- `test_cache_key_is_consistent`
- `test_cache_lru_eviction`
- `test_cache_ttl_expiry`
- `test_cacheable_tool_different_args_not_cached`
- `test_cacheable_tool_second_call_uses_cache`
- `test_non_cacheable_tool_always_calls_run`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/tools/test_result_cache.py`.
- Cross-reference `CONNECTIONS_test_result_cache.md` to see how this file fits into the wider system.
