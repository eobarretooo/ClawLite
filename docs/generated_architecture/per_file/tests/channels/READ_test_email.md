# READ tests/channels/test_email.py

## Identity

- Path: `tests/channels/test_email.py`
- Area: `tests`
- Extension: `.py`
- Lines: 228
- Size bytes: 7892
- SHA1: `e8c6f7e9d47e4c86389592c64bfe80063f38fb69`

## Summary

`tests.channels.test_email` is a Python module in the `tests` area. It defines 3 class(es), led by `FailingSMTPSSL`, `FakeIMAP`, `FakeSMTP`. It exposes 22 function(s), including `__enter__`, `__exit__`, `__init__`, `_on_message`, `_scenario`, `_sleep`. It depends on 8 import statement target(s).

## Structural Data

- Classes: 3
- Functions: 18
- Async functions: 4
- Constants: 0
- Internal imports: 1
- Imported by: 0
- Matching tests: 0

## Classes

- `FailingSMTPSSL`
- `FakeIMAP`
- `FakeSMTP`

## Functions

- `__enter__`
- `__exit__`
- `__init__`
- `_fetch_once`
- `_raw_email`
- `_smtp_factory`
- `fetch`
- `login`
- `logout`
- `search`
- `select`
- `send_message`
- `starttls`
- `store`
- `test_email_channel_poll_emits_new_messages`
- `test_email_extract_text_body_falls_back_to_html`
- `test_email_fetch_new_messages_dedupes_uid_and_marks_seen`
- `test_email_send_falls_back_from_ssl_to_starttls`
- `_on_message` (async)
- `_scenario` (async)
- `_sleep` (async)
- `_to_thread` (async)

## Notable String Markers

- `test_email_channel_poll_emits_new_messages`
- `test_email_extract_text_body_falls_back_to_html`
- `test_email_fetch_new_messages_dedupes_uid_and_marks_seen`
- `test_email_send_falls_back_from_ssl_to_starttls`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/channels/test_email.py`.
- Cross-reference `CONNECTIONS_test_email.md` to see how this file fits into the wider system.
