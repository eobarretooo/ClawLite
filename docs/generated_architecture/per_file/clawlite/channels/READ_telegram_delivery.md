# READ clawlite/channels/telegram_delivery.py

## Identity

- Path: `clawlite/channels/telegram_delivery.py`
- Area: `channels`
- Extension: `.py`
- Lines: 288
- Size bytes: 9027
- SHA1: `bbc0f14b789c942147b9c30e4e8b06bf2cb45dd4`

## Summary

`clawlite.channels.telegram_delivery` is a Python module in the `channels` area. It defines 3 class(es), led by `TelegramAuthCircuitBreaker`, `TelegramCircuitOpenError`, `TelegramRetryPolicy`. It exposes 21 function(s), including `__init__`, `coerce_retry_after_seconds`, `coerce_thread_id`. It depends on 8 import statement target(s).

## Structural Data

- Classes: 3
- Functions: 21
- Async functions: 0
- Constants: 0
- Internal imports: 0
- Imported by: 3
- Matching tests: 2

## Classes

- `TelegramAuthCircuitBreaker`
- `TelegramCircuitOpenError`
- `TelegramRetryPolicy`

## Functions

- `__init__`
- `coerce_retry_after_seconds`
- `coerce_thread_id`
- `exception_text`
- `is_auth_failure`
- `is_formatting_error`
- `is_open`
- `is_thread_not_found_error`
- `is_transient_failure`
- `normalize_api_message_thread_id`
- `normalized`
- `on_auth_failure`
- `on_success`
- `parse_target`
- `retry_after_delay_s`
- `retry_delay_s`
- `status_code_from_exc`
- `sync_auth_breaker_signal_transition`
- `threadless_retry_allowed`
- `typing_key`
- `typing_task_is_active`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/channels/telegram_delivery.py`.
- Cross-reference `CONNECTIONS_telegram_delivery.md` to see how this file fits into the wider system.
