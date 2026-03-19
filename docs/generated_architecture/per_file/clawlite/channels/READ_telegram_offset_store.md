# READ clawlite/channels/telegram_offset_store.py

## Identity

- Path: `clawlite/channels/telegram_offset_store.py`
- Area: `channels`
- Extension: `.py`
- Lines: 400
- Size bytes: 15012
- SHA1: `94c6c6aedac130e2eee9c71d71872d7d0aa88124`

## Summary

`clawlite.channels.telegram_offset_store` is a Python module in the `channels` area. It defines 2 class(es), led by `TelegramOffsetSnapshot`, `TelegramOffsetStore`. It exposes 24 function(s), including `__init__`, `_advance_safe_watermark_locked`, `_coerce_optional_update_id`. It depends on 9 import statement target(s).

## Structural Data

- Classes: 2
- Functions: 24
- Async functions: 0
- Constants: 1
- Internal imports: 0
- Imported by: 3
- Matching tests: 2

## Classes

- `TelegramOffsetSnapshot`
- `TelegramOffsetStore`

## Functions

- `__init__`
- `_advance_safe_watermark_locked`
- `_coerce_optional_update_id`
- `_coerce_update_id`
- `_extract_bot_id`
- `_identity_matches`
- `_now_iso`
- `_prune_sets_locked`
- `_read_state`
- `_token_fingerprint`
- `_write_state`
- `begin`
- `force_commit`
- `is_pending`
- `is_safe_committed`
- `mark_completed`
- `min_pending_update_id`
- `next_offset`
- `pending_count`
- `refresh_from_disk`
- `reset_runtime_state`
- `resolve_path`
- `snapshot`
- `sync_next_offset`

## Constants

- `STORE_SCHEMA_VERSION`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/channels/telegram_offset_store.py`.
- Cross-reference `CONNECTIONS_telegram_offset_store.md` to see how this file fits into the wider system.
