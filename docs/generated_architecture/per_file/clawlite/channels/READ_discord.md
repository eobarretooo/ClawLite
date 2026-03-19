# READ clawlite/channels/discord.py

## Identity

- Path: `clawlite/channels/discord.py`
- Area: `channels`
- Extension: `.py`
- Lines: 2343
- Size bytes: 92085
- SHA1: `9344f71e9b5cc1703308b32b0000e7193d680ff5`

## Summary

`clawlite.channels.discord` is a Python module in the `channels` area. It defines 4 class(es), led by `DiscordChannel`, `_DiscordGuildChannelPolicy`, `_DiscordGuildPolicy`, `_DiscordSendTarget`. It exposes 78 function(s), including `__init__`, `_binding_expiration_reason`, `_build_presence_payload`, `_ack_interaction`, `_apply_bound_session`, `_auto_presence_loop`. It depends on 18 import statement target(s).

## Structural Data

- Classes: 4
- Functions: 36
- Async functions: 42
- Constants: 6
- Internal imports: 1
- Imported by: 3
- Matching tests: 3

## Classes

- `DiscordChannel`
- `_DiscordGuildChannelPolicy`
- `_DiscordGuildPolicy`
- `_DiscordSendTarget`

## Functions

- `__init__`
- `_binding_expiration_reason`
- `_build_presence_payload`
- `_derive_auto_presence`
- `_derive_interaction_session_id`
- `_derive_session_id`
- `_extract_retry_after`
- `_generate_placeholder_waveform`
- `_guild_policy`
- `_is_allowed_sender`
- `_is_payload_authorized`
- `_load_thread_bindings`
- `_looks_like_snowflake`
- `_matches_role_entries`
- `_matches_sender_entries`
- `_message_mentions_bot`
- `_message_mentions_others`
- `_normalize_allow_bots`
- `_normalize_allow_from`
- `_normalize_attachment_rows`
- `_normalize_dm_policy`
- `_normalize_group_policy`
- `_normalize_guild_policies`
- `_normalize_reply_to_mode`
- `_normalize_string_list`
- `_parse_retry_after`
- `_parse_send_target`
- `_parse_utc_timestamp`
- `_presence_payload`
- `_role_ids_from_payload`
- `_sender_candidates`
- `_task_state`
- `_utc_now`
- `_write_thread_bindings`
- `operator_status`
- `resolve_bound_session`
- `_ack_interaction` (async)
- `_apply_bound_session` (async)
- `_auto_presence_loop` (async)
- `_download_attachment` (async)
- `_ensure_dm_channel_id` (async)
- `_ensure_thread_bindings_loaded` (async)
- `_gateway_loop` (async)
- `_gateway_runner` (async)
- `_generate_waveform_from_audio` (async)
- `_handle_gateway_payload` (async)
- `_handle_interaction_create` (async)
- `_handle_message_create` (async)
- `_handle_message_reaction_add` (async)
- `_heartbeat_loop` (async)
- `_identify` (async)
- `_patch_json` (async)
- `_post_json` (async)
- `_prune_expired_thread_binding` (async)
- `_resume` (async)
- `_send_ws_json` (async)
- `_start_heartbeat` (async)
- `_start_typing` (async)
- `_stop_typing` (async)
- `_typing_loop` (async)
- `_update_presence` (async)
- `add_reaction` (async)
- `bind_thread` (async)
- `create_poll` (async)
- `create_thread` (async)
- `create_webhook` (async)
- `execute_webhook` (async)
- `list_slash_commands` (async)
- `operator_refresh_presence` (async)
- `operator_refresh_transport` (async)
- `register_slash_command` (async)
- `reply_interaction` (async)
- `send` (async)
- `send_streaming` (async)
- `send_voice_message` (async)
- `start` (async)
- `stop` (async)
- `unbind_thread` (async)

## Constants

- `DISCORD_DEFAULT_API_BASE`
- `DISCORD_DEFAULT_GATEWAY_INTENTS`
- `DISCORD_DEFAULT_GATEWAY_URL`
- `DISCORD_TYPING_INTERVAL_S`
- `DISCORD_VOICE_MESSAGE_FLAG`
- `DISCORD_VOICE_WAVEFORM_SAMPLES`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `clawlite/channels/discord.py`.
- Cross-reference `CONNECTIONS_discord.md` to see how this file fits into the wider system.
