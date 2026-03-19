# READ tests/channels/test_discord.py

## Identity

- Path: `tests/channels/test_discord.py`
- Area: `tests`
- Extension: `.py`
- Lines: 1608
- Size bytes: 56097
- SHA1: `98be10cbf681f9100e94687fee38b29a2a1135c9`

## Summary

`tests.channels.test_discord` is a Python module in the `tests` area. It defines 3 class(es), led by `_FakeClient`, `_FakeVoiceClient`, `_FakeWebSocket`. It exposes 65 function(s), including `__aiter__`, `__init__`, `_factory`, `__aenter__`, `__aexit__`, `__anext__`. It depends on 11 import statement target(s).

## Structural Data

- Classes: 3
- Functions: 39
- Async functions: 26
- Constants: 0
- Internal imports: 2
- Imported by: 0
- Matching tests: 0

## Classes

- `_FakeClient`
- `_FakeVoiceClient`
- `_FakeWebSocket`

## Functions

- `__aiter__`
- `__init__`
- `_factory`
- `_make_channel`
- `_response`
- `test_discord_allow_bots_mentions_requires_bot_mention`
- `test_discord_channel_reuses_persistent_client_across_sends`
- `test_discord_create_webhook_posts_to_channel`
- `test_discord_dm_policy_disabled_blocks_private_message`
- `test_discord_execute_webhook_sends_message`
- `test_discord_gateway_intents_include_reactions`
- `test_discord_gateway_loop_identifies_and_emits_message`
- `test_discord_group_policy_allowlist_honors_guild_channel_and_role_rules`
- `test_discord_group_policy_mention_requires_bot_mention`
- `test_discord_handle_interaction_create_button_emits_message`
- `test_discord_handle_interaction_create_slash_can_disable_isolated_sessions`
- `test_discord_handle_interaction_create_slash_emits_message`
- `test_discord_identify_includes_auto_presence_payload_when_enabled`
- `test_discord_identify_includes_presence_payload_when_configured`
- `test_discord_interaction_honors_allowlisted_guild_channel_without_mention`
- `test_discord_interaction_uses_bound_session_key`
- `test_discord_message_create_filters_self_and_acl`
- `test_discord_operator_refresh_presence_sends_status_update`
- `test_discord_operator_refresh_transport_resets_gateway_state`
- `test_discord_operator_status_reports_gateway_state`
- `test_discord_placeholder_waveform_is_base64`
- `test_discord_register_slash_command_posts_correct_payload`
- `test_discord_send_ambiguous_target_404_falls_back_to_dm`
- `test_discord_send_channel_target_accepts_prefix`
- `test_discord_send_includes_components_from_metadata`
- `test_discord_send_interaction_reply_uses_original_response_path`
- `test_discord_send_retries_429_using_retry_after`
- `test_discord_send_streaming_edits_message_in_place`
- `test_discord_send_user_target_creates_dm_channel`
- `test_discord_send_voice_message_builds_correct_payload`
- `test_discord_send_with_poll_metadata`
- `test_discord_thread_binding_idle_timeout_releases_stale_focus`
- `test_discord_thread_binding_max_age_releases_stale_focus`
- `test_discord_thread_binding_persists_and_routes_inbound_messages`
- `__aenter__` (async)
- `__aexit__` (async)
- `__anext__` (async)
- `_fake_patch` (async)
- `_fake_post` (async)
- `_fake_post_json` (async)
- `_fake_reply_interaction` (async)
- `_fake_send` (async)
- `_on_message` (async)
- `_scenario` (async)
- `aclose` (async)
- `close` (async)
- `fake_chunks` (async)
- `on_msg` (async)
- `post` (async)
- `put` (async)
- `send` (async)
- `test_add_reaction_empty_emoji_returns_false` (async)
- `test_add_reaction_not_running_returns_false` (async)
- `test_add_reaction_success` (async)
- `test_create_thread_from_message` (async)
- `test_create_thread_standalone` (async)
- `test_download_attachment_returns_none_for_non_https` (async)
- `test_gateway_handles_reaction_add_event` (async)
- `test_reaction_add_bot_user_ignored` (async)
- `test_send_with_embeds` (async)

## Notable String Markers

- `test_add_reaction_empty_emoji_returns_false`
- `test_add_reaction_not_running_returns_false`
- `test_add_reaction_success`
- `test_create_thread_from_message`
- `test_create_thread_standalone`
- `test_discord_allow_bots_mentions_requires_bot_mention`
- `test_discord_channel_reuses_persistent_client_across_sends`
- `test_discord_create_webhook_posts_to_channel`
- `test_discord_dm_policy_disabled_blocks_private_message`
- `test_discord_execute_webhook_sends_message`
- `test_discord_gateway_intents_include_reactions`
- `test_discord_gateway_loop_identifies_and_emits_message`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/channels/test_discord.py`.
- Cross-reference `CONNECTIONS_test_discord.md` to see how this file fits into the wider system.
