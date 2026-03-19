# READ clawlite/channels/email.py

## Identity

- Path: `clawlite/channels/email.py`
- Area: `channels`
- Extension: `.py`
- Lines: 522
- Size bytes: 19852
- SHA1: `7506a3e0a0a832616e20698e9703f7e8fc340dac`

## Summary

`clawlite.channels.email` is a Python module in the `channels` area. It defines 1 class(es), led by `EmailChannel`. It exposes 25 function(s), including `__init__`, `_connect_imap`, `_decode_header_value`, `_poll_loop`, `send`, `start`. It depends on 15 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 21
- Async functions: 4
- Constants: 0
- Internal imports: 1
- Imported by: 2
- Matching tests: 1

## Classes

- `EmailChannel`

## Functions

- `__init__`
- `_connect_imap`
- `_decode_header_value`
- `_extract_message_bytes`
- `_extract_text_body`
- `_extract_uid`
- `_fetch_messages`
- `_fetch_new_messages`
- `_html_to_text`
- `_is_allowed_sender`
- `_load_dedupe_state`
- `_mark_seen`
- `_normalize_allow_from`
- `_normalize_dedupe_state_path`
- `_remember_uid`
- `_reply_subject`
- `_save_dedupe_state`
- `_smtp_send`
- `_trim_processed_uids`
- `_validate_receive_config`
- `_validate_send_config`
- `_poll_loop` (async)
- `send` (async)
- `start` (async)
- `stop` (async)

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/channels/email.py`.
- Cross-reference `CONNECTIONS_email.md` to see how this file fits into the wider system.
