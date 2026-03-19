# READ tests/providers/test_streaming_recovery.py

## Identity

- Path: `tests/providers/test_streaming_recovery.py`
- Area: `tests`
- Extension: `.py`
- Lines: 180
- Size bytes: 6775
- SHA1: `62d0c01bcc95dfb17c847f87ae53a33ec11938b8`

## Summary

`tests.providers.test_streaming_recovery` is a Python module in the `tests` area. It exposes 8 function(s), including `_make_provider`, `_collect_chunks`, `fake_aiter_lines`, `refreshed_aiter_lines`. It depends on 7 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 1
- Async functions: 7
- Constants: 0
- Internal imports: 2
- Imported by: 0
- Matching tests: 0

## Functions

- `_make_provider`
- `_collect_chunks` (async)
- `fake_aiter_lines` (async)
- `refreshed_aiter_lines` (async)
- `test_stream_degraded_recovery_on_mid_stream_error` (async)
- `test_stream_error_before_any_chunks_propagates_as_error_chunk` (async)
- `test_stream_no_degraded_on_clean_finish` (async)
- `test_stream_refreshes_oauth_once_on_401_before_emitting_chunks` (async)

## Notable String Markers

- `test_stream_degraded_recovery_on_mid_stream_error`
- `test_stream_error_before_any_chunks_propagates_as_error_chunk`
- `test_stream_no_degraded_on_clean_finish`
- `test_stream_refreshes_oauth_once_on_401_before_emitting_chunks`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/providers/test_streaming_recovery.py`.
- Cross-reference `CONNECTIONS_test_streaming_recovery.md` to see how this file fits into the wider system.
