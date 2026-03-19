# READ tests/config/test_watcher.py

## Identity

- Path: `tests/config/test_watcher.py`
- Area: `tests`
- Extension: `.py`
- Lines: 109
- Size bytes: 3202
- SHA1: `9cd9c07b25381376ace14d5b005c90533b11317a`

## Summary

`tests.config.test_watcher` is a Python module in the `tests` area. It exposes 6 function(s), including `_write_config`, `_fake_loop`, `test_watcher_bad_json_keeps_old_config`, `test_watcher_calls_callback_on_change`. It depends on 10 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 1
- Async functions: 5
- Constants: 0
- Internal imports: 3
- Imported by: 0
- Matching tests: 0

## Functions

- `_write_config`
- `_fake_loop` (async)
- `test_watcher_bad_json_keeps_old_config` (async)
- `test_watcher_calls_callback_on_change` (async)
- `test_watcher_no_watchfiles_does_not_crash` (async)
- `test_watcher_start_stop_idempotent` (async)

## Notable String Markers

- `test_watcher_bad_json_keeps_old_config`
- `test_watcher_calls_callback_on_change`
- `test_watcher_no_watchfiles_does_not_crash`
- `test_watcher_start_stop_idempotent`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/config/test_watcher.py`.
- Cross-reference `CONNECTIONS_test_watcher.md` to see how this file fits into the wider system.
