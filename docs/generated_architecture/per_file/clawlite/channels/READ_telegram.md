# READ clawlite/channels/telegram.py

## Identity

- Path: `clawlite/channels/telegram.py`
- Area: `channels`
- Extension: `.py`
- Lines: 3903
- Size bytes: 155767
- SHA1: `c6d50355062eb0cc13bf4639fef9d8c86eaf7fa1`

## Summary

`clawlite.channels.telegram` is a Python module in the `channels` area. It defines 1 class(es), led by `TelegramChannel`. It exposes 136 function(s), including `__init__`, `_added_reaction_tokens`, `_apply_offset_snapshot`, `_activate_webhook_mode`, `_download_media_items`, `_drop_pending_updates`. It depends on 36 import statement target(s).

## Structural Data

- Classes: 1
- Functions: 103
- Async functions: 33
- Constants: 4
- Internal imports: 16
- Imported by: 5
- Matching tests: 9

## Classes

- `TelegramChannel`

## Functions

- `__init__`
- `_added_reaction_tokens`
- `_apply_offset_snapshot`
- `_authorization_decision`
- `_authorize_inbound_context`
- `_begin_safe_offset_update`
- `_buffer_media_group_message`
- `_build_inline_keyboard_reply_markup`
- `_build_media_item`
- `_build_media_placeholder`
- `_build_media_text_suffix_lines`
- `_build_metadata`
- `_build_reply_keyboard_reply_markup`
- `_build_update_dedupe_key`
- `_callback_sign_payload`
- `_callback_signing_active`
- `_callback_verify_payload`
- `_coerce_thread_id`
- `_coerce_update_id`
- `_commit_update_dedupe_key`
- `_compact_text`
- `_complete_safe_offset_update`
- `_compose_inbound_text`
- `_dedupe_state_payload`
- `_expand_inline_list_runs`
- `_expand_inline_markdown_tables`
- `_extract_media_info`
- `_field`
- `_force_commit_offset_update`
- `_is_allowed_sender`
- `_is_authorized_context`
- `_is_duplicate_update_dedupe_key`
- `_is_stale_offset_update`
- `_load_offset`
- `_load_update_dedupe_state`
- `_media_download_dir`
- `_media_download_extension`
- `_media_type_supports_caption`
- `_metadata_user_id`
- `_normalize_access_policy`
- `_normalize_allow_from_values`
- `_normalize_api_message_thread_id`
- `_normalize_mode`
- `_normalize_optional_path`
- `_normalize_outbound_media_items`
- `_normalize_outbound_parse_mode`
- `_normalize_reaction_notifications`
- `_normalize_state_path`
- `_normalize_telegram_markdown`
- `_normalize_webhook_path`
- `_normalize_webhook_payload`
- `_offset_path`
- `_on_send_auth_failure`
- `_on_send_auth_success`
- `_on_typing_auth_failure`
- `_on_typing_auth_success`
- `_outbound_runtime`
- `_pairing_allow_from_values`
- `_parse_target`
- `_persist_offset_operation`
- `_reaction_token`
- `_reaction_tokens`
- `_refresh_update_dedupe_state`
- `_remember_message_signature`
- `_remember_own_sent_message_ids`
- `_remember_update_dedupe_key`
- `_render_outbound_text`
- `_render_table_box`
- `_reserve_token`
- `_resolve_media_sender`
- `_resolve_transcription_provider`
- `_sanitize_telegram_text`
- `_save_offset`
- `_schedule_dedupe_state_persist`
- `_sender_candidates`
- `_sender_matches_allow_from`
- `_session_id_for_chat`
- `_should_begin_webhook_offset_tracking`
- `_should_send_pairing_notice`
- `_split_long_telegram_segment`
- `_split_media_caption`
- `_start_typing_keepalive`
- `_strip_markdown_inline`
- `_sync_auth_breaker_signal_transition`
- `_threadless_retry_allowed`
- `_to_namespace`
- `_transcription_requested_for`
- `_typing_key`
- `_typing_task_is_active`
- `_urlsafe_b64decode`
- `_webhook_offset_completion_policy`
- `_webhook_requested`
- `display_width`
- `draw_row`
- `markdown_to_telegram_html`
- `operator_status`
- `parse_command`
- `save_code_block`
- `save_heading`
- `save_inline_code`
- `signals`
- `split_message`
- `webhook_mode_active`
- `_activate_webhook_mode` (async)
- `_download_media_items` (async)
- `_drop_pending_updates` (async)
- `_edit_stream_text` (async)
- `_emit_aux_update_event` (async)
- `_ensure_bot` (async)
- `_flush_all_media_groups` (async)
- `_flush_media_group` (async)
- `_handle_pairing_required` (async)
- `_handle_update` (async)
- `_maybe_transcribe_media_item` (async)
- `_persist_update_dedupe_state` (async)
- `_poll_loop` (async)
- `_resolve_outbound_media_payload` (async)
- `_send_help_message` (async)
- `_send_media_items` (async)
- `_send_start_message` (async)
- `_send_text_chunks` (async)
- `_stop_all_typing_keepalive` (async)
- `_stop_typing_keepalive` (async)
- `_try_delete_webhook` (async)
- `_typing_loop` (async)
- `handle_webhook_update` (async)
- `operator_approve_pairing` (async)
- `operator_force_commit_offset` (async)
- `operator_refresh_transport` (async)
- `operator_reject_pairing` (async)
- `operator_revoke_pairing` (async)
- `operator_sync_next_offset` (async)
- `send` (async)
- `send_streaming` (async)
- `start` (async)
- `stop` (async)

## Constants

- `MAX_CAPTION_LEN`
- `MAX_MESSAGE_LEN`
- `MEDIA_GROUP_FLUSH_DELAY_S`
- `TELEGRAM_ALLOWED_UPDATES`

## Notable String Markers

- `clawlite pairing`
- `test_task`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/channels/telegram.py`.
- Cross-reference `CONNECTIONS_telegram.md` to see how this file fits into the wider system.
