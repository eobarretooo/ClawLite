# READ tests/utils/test_logging.py

## Identity

- Path: `tests/utils/test_logging.py`
- Area: `tests`
- Extension: `.py`
- Lines: 114
- Size bytes: 3613
- SHA1: `f5f68e772739b7e1496f33fbab5263701c7b4ed1`

## Summary

`tests.utils.test_logging` is a Python module in the `tests` area. It exposes 8 function(s), including `_reset_logging_state`, `test_cron_and_telegram_plain_logger_calls_work`, `test_logger_patcher_backfills_missing_extra_fields`, `_on_job`, `_run`. It depends on 9 import statement target(s).

## Structural Data

- Classes: 0
- Functions: 6
- Async functions: 2
- Constants: 0
- Internal imports: 3
- Imported by: 0
- Matching tests: 0

## Functions

- `_reset_logging_state`
- `test_cron_and_telegram_plain_logger_calls_work`
- `test_logger_patcher_backfills_missing_extra_fields`
- `test_plain_logger_uses_default_extra_fields`
- `test_text_formatter_applies_level_and_event_colors`
- `test_text_formatter_handles_braces_in_message_and_exception`
- `_on_job` (async)
- `_run` (async)

## Notable String Markers

- `test_cron_and_telegram_plain_logger_calls_work`
- `test_logger_patcher_backfills_missing_extra_fields`
- `test_plain_logger_uses_default_extra_fields`
- `test_text_formatter_applies_level_and_event_colors`
- `test_text_formatter_handles_braces_in_message_and_exception`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/utils/test_logging.py`.
- Cross-reference `CONNECTIONS_test_logging.md` to see how this file fits into the wider system.
