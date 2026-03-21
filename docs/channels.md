# Channels

ClawLite can send and receive messages through multiple channel adapters. Today, Telegram is the most complete adapter. Discord, Email, WhatsApp, Slack, and IRC are usable to different degrees. Several extra channel names are still registered as placeholders but are not implemented yet.

## Quick Start

1. Add your channel config to `~/.clawlite/config.json`.
2. Start the gateway with `clawlite gateway`.
3. Run `clawlite validate channels` for static checks.
4. For Telegram tokens, you can also run `clawlite validate preflight --telegram-live`.
5. Inspect live channel state in `/v1/diagnostics` under `channels`, `channels_dispatcher`, `channels_delivery`, `channels_inbound`, and `channels_recovery`.

Quickstart note: `clawlite configure --flow quickstart` only offers Telegram. Discord, Email, WhatsApp, Slack, and IRC are manual config today.

Prompting note: inbound adapters already normalize rich metadata for routing and delivery, but the agent prompt only sees a compact allowlisted subset of that metadata as untrusted runtime context. That allowlist now includes structural hints such as message/thread ids, Slack thread timestamps, Telegram forum state, Discord DM state, signed callback/button ids, and lightweight media markers, while still excluding raw webhook payloads and large channel-specific blobs. Inbound text also normalizes real CRLF/CR newlines and neutralizes obvious spoof markers like `[System Message]`, bracketed `[Developer]`, or line-leading `System:` before it reaches the agent loop.

## Channel Matrix

| Channel | Inbound | Outbound | Status | Notes |
| --- | --- | --- | --- | --- |
| Telegram | Yes | Yes | Most complete | Polling and webhook, pairing, reactions, topics, typing keepalive, media download, voice/audio transcription |
| Discord | Yes | Yes | Usable | Gateway websocket inbound, REST outbound, reactions (send+receive), buttons/select menus, embeds, thread creation, attachment download, voice/audio transcription, focus bindings |
| Email | Yes | Yes | Usable | IMAP polling inbound plus SMTP replies |
| WhatsApp | Yes | Yes | Usable | Inbound webhook, outbound retry, bridge typing keepalive |
| Slack | Yes | Yes | Usable | Socket Mode inbound, outbound `chat.postMessage`, reversible working indicator |
| Signal | No | No | Placeholder | Passive stub only |
| Google Chat | No | No | Placeholder | Passive stub only |
| Matrix | No | No | Placeholder | Passive stub only |
| IRC | Yes | Yes | Minimal | Asyncio transport, JOIN, PING/PONG, PRIVMSG |
| iMessage | No | No | Placeholder | Passive stub only |
| DingTalk | No | No | Placeholder | Passive stub only |
| Feishu | No | No | Placeholder | Passive stub only |
| Mochat | No | No | Placeholder | Passive stub only |
| QQ | No | No | Placeholder | Passive stub only |

## Shared `channels` Settings

These top-level keys are part of the typed config schema and are safe to use with `clawlite validate config`:

```json
{
  "channels": {
    "send_progress": false,
    "send_tool_hints": false,
    "recovery_enabled": true,
    "recovery_interval_s": 15.0,
    "recovery_cooldown_s": 30.0,
    "replay_dead_letters_on_startup": true,
    "replay_dead_letters_limit": 50,
    "replay_dead_letters_reasons": ["send_failed", "channel_unavailable"],
    "delivery_persistence_path": ""
  }
}
```

What they do:

- `send_progress`: lets the runtime emit progress updates back to channels.
- `send_tool_hints`: lets the runtime surface tool-hint notices on channel replies.
- `recovery_*`: enables the recovery supervisor that restarts failed channel workers.
- `replay_dead_letters_*`: replays retryable outbound failures on startup.
- `delivery_persistence_path`: overrides the dead-letter journal path.

Operator note: `ChannelManager` also consumes additional raw tuning knobs for dispatcher concurrency, idempotency, inbound replay, and persistence. Those knobs exist in code, but some are not part of the strict config schema yet, so `clawlite validate config` can flag them.

## Telegram

Telegram is the most feature-complete adapter in ClawLite.

What it supports:

- Polling or webhook mode.
- DM, group, and forum-topic routing.
- Context-aware access policies.
- Pairing-based DM approval.
- Typing keepalive during long turns.
- Media downloads into the Telegram media directory, with saved-file references and best-effort OCR/PDF text snippets injected into inbound text when local dependencies are available.
- Voice/audio transcription through a Groq-compatible OpenAI endpoint.
- Reaction forwarding and inline keyboard callbacks.
- Inline approval/review buttons for approval-gated tools and self-evolution review.
- Telegram-specific message actions through the `message` tool: reply, edit, delete, react, and create topic.
- Outbound markdown cleanup for inline lists, headings, and simple pipe tables before Telegram HTML rendering.
- Streaming edits use the same HTML renderer path as normal outbound sends, and fall back to plain text if Telegram rejects formatted markup.

Important config keys:

- `token`
- `mode`, `webhook_enabled`, `webhook_url`, `webhook_secret`, `webhook_path`
- `allow_from`
- `dm_policy`, `group_policy`, `topic_policy`
- `dm_allow_from`, `group_allow_from`, `topic_allow_from`
- `group_overrides`
- `poll_interval_s`, `poll_timeout_s`
- `send_*`, `typing_*`
- `reaction_notifications`
- `transcribe_voice`, `transcribe_audio`, `transcription_api_key`, `transcription_base_url`, `transcription_model`, `transcription_language`
- `pairing_state_path`, `pairing_notice_cooldown_s`
- `callback_signing_enabled`, `callback_signing_secret`, `callback_require_signed`

Policy values:

- `open`: allow traffic.
- `allowlist`: only allow IDs or handles in the matching allowlist.
- `disabled`: block that context.
- `pairing`: private chats only; unknown users receive a pairing code that an operator approves with `clawlite pairing approve telegram <code>`.

Example webhook config:

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "123456:TEST_TOKEN",
      "mode": "webhook",
      "webhook_enabled": true,
      "webhook_url": "https://example.com/api/webhooks/telegram",
      "webhook_secret": "telegram-secret",
      "webhook_path": "/api/webhooks/telegram",
      "allow_from": ["@owner", "123456789"],
      "dm_policy": "pairing",
      "group_policy": "allowlist",
      "topic_policy": "allowlist",
      "group_allow_from": ["@owner"],
      "topic_allow_from": ["@owner", "123456789"],
      "transcribe_voice": true,
      "transcribe_audio": true,
      "transcription_api_key": "",
      "transcription_base_url": "https://api.groq.com/openai/v1",
      "transcription_model": "whisper-large-v3-turbo",
      "transcription_language": "pt",
      "typing_enabled": true,
      "reaction_notifications": "own"
    }
  }
}
```

Notes:

- For polling, set `mode` to `polling` and omit `webhook_url` and `webhook_secret`.
- Webhook mode only becomes active when both `webhook_url` and `webhook_secret` are present and Telegram webhook registration succeeds. Otherwise ClawLite falls back to polling.
- If `transcription_api_key` is empty, Telegram transcription falls back to `GROQ_API_KEY`.
- `group_overrides` can override policy per chat and per topic.
- Inline keyboards are also used for operator review flows such as approval-gated tools and self-evolution review.
- The renderer normalizes “flat” inline lists like `Passos: 1. ... 2. ...` into readable multi-line output before send/edit.
- Outbound send/edit sanitizes replacement characters and control bytes before Telegram rendering so malformed `��` artifacts do not leak through.

`group_overrides` example:

```json
{
  "channels": {
    "telegram": {
      "group_overrides": {
        "-100123456": {
          "policy": "open",
          "allow_from": ["@owner"],
          "topics": {
            "42": {
              "policy": "allowlist",
              "allow_from": ["@alice", "123456789"]
            }
          }
        }
      }
    }
  }
}
```

Useful commands:

```bash
clawlite validate preflight --telegram-live
clawlite pairing list telegram
clawlite pairing approve telegram ABC123
```

## Discord

Discord uses the gateway websocket for inbound messages and the REST API for outbound sends.

Important config keys:

- `token`
- `api_base`
- `timeout_s`
- `gateway_url`
- `gateway_intents`
- `gateway_backoff_base_s`, `gateway_backoff_max_s`
- `typing_enabled`, `typing_interval_s`
- `transcribe_voice`, `transcribe_audio`
- `transcription_api_key`, `transcription_base_url`, `transcription_model`, `transcription_language`, `transcription_timeout_s`
- `allow_from`
- `dm_policy`
- `group_policy`
- `allow_bots`
- `require_mention`, `ignore_other_mentions`
- `status`, `activity`, `activity_type`, `activity_url`
- `auto_presence`
- `guilds`
- `reply_to_mode`, `slash_isolated_sessions`
- `thread_bindings_enabled`, `thread_binding_state_path`
- `thread_binding_idle_timeout_s`, `thread_binding_max_age_s`

Example config:

```json
{
  "channels": {
    "discord": {
      "enabled": true,
      "token": "discord-bot-token",
      "api_base": "https://discord.com/api/v10",
      "timeout_s": 10.0,
      "gateway_url": "wss://gateway.discord.gg/?v=10&encoding=json",
      "gateway_intents": 46593,
      "gateway_backoff_base_s": 2.0,
      "gateway_backoff_max_s": 30.0,
      "typing_enabled": true,
      "typing_interval_s": 8.0,
      "transcribe_voice": true,
      "transcribe_audio": true,
      "transcription_api_key": "",
      "transcription_base_url": "https://api.groq.com/openai/v1",
      "transcription_model": "whisper-large-v3-turbo",
      "transcription_language": "pt",
      "transcription_timeout_s": 90.0,
      "allow_from": ["123456789012345678", "@ownername"],
      "dm_policy": "allowlist",
      "group_policy": "allowlist",
      "allow_bots": "mentions",
      "status": "idle",
      "activity": "Focus time",
      "activity_type": 4,
      "auto_presence": {
        "enabled": true,
        "interval_s": 30,
        "min_update_interval_s": 15,
        "healthy_text": "all systems nominal",
        "degraded_text": "warming up",
        "exhausted_text": "offline"
      },
      "reply_to_mode": "first",
      "slash_isolated_sessions": true,
      "thread_bindings_enabled": true,
      "thread_binding_state_path": "~/.clawlite/channels/discord-thread-bindings.json",
      "thread_binding_idle_timeout_s": 1800,
      "thread_binding_max_age_s": 28800,
      "guilds": {
        "123456789012345678": {
          "require_mention": true,
          "roles": ["987654321098765432"],
          "channels": {
            "111111111111111111": {
              "allow": true
            }
          }
        }
      }
    }
  }
}
```

Notes:

- `allow_from` can contain stable user IDs or usernames, but IDs are safer. Username-only entries are convenience compatibility, not the safest mode.
- `dm_policy` supports `open`, `allowlist`, and `disabled`.
- `group_policy` supports `open`, `mention`, `allowlist`, and `disabled`.
- `allow_bots` supports `disabled`, `mentions`, and `all`.
- `reply_to_mode` supports `off`, `first`, and `all`.
- `guilds.<guild_id>.channels` is an allowlist when present. If the map exists, non-listed channels are denied.
- `guilds.<guild_id>.users` and `roles` can further restrict who is allowed inside that guild or channel.
- Bot/self messages are ignored by default. If `allow_bots="mentions"` or `"all"` is set, non-self bot traffic can pass policy checks.
- Native slash commands default to isolated session keys (`discord:guild:<guild>:channel:<channel>:slash:<user>` or `discord:dm:<user>:slash`). Set `slash_isolated_sessions=false` to keep the legacy shared channel session behavior.
- Discord thread/channel focus bindings are now persisted locally. Discord treats threads as channels, so `/focus <session_id>` and `/unfocus` work naturally inside a thread or any dedicated channel.
- By default, `ChannelManager` injects `thread_binding_state_path` under `state_path/channels/discord-thread-bindings.json` when the path is not set explicitly.
- Focus bindings can expire automatically with `thread_binding_idle_timeout_s` and/or `thread_binding_max_age_s`. When a binding goes stale, ClawLite drops it fail-closed and routes the next inbound event back to the live Discord channel session.
- Attachments are downloaded concurrently from the Discord CDN; raw bytes are available in the `attachment_data` metadata key. Each entry mirrors the `attachments` row with an added `data` field (bytes or `None` on failure).
- Inbound Discord audio/voice attachments can now reuse the same Groq-compatible transcription path as Telegram. When `transcribe_voice` or `transcribe_audio` is enabled and a `transcription_api_key` (or `GROQ_API_KEY`) is available, ClawLite appends compact `[voice transcription: ...]` or `[audio transcription: ...]` lines to the inbound turn and exposes `media_transcription_count` / `media_transcription_error_count` in Discord operator status.
- **Reactions**: `add_reaction(channel_id, message_id, emoji)` sends a reaction. Incoming `MESSAGE_REACTION_ADD` events are emitted as metadata-only events with `event_type: "reaction_add"` and `emoji`.
- **Embeds**: pass a list of embed dicts under `metadata["discord_embeds"]` (or `"embeds"`) in `send()`. Discord accepts up to 10 embeds per message, and ClawLite now normalizes embed-field `inline` flags plus embed `timestamp` values before posting/replying so stats-style embeds render consistently.
- **Webhooks**: `execute_webhook(...)` now also accepts `thread_id` for thread-targeted delivery, reuses the same embed normalization path, and clamps component rows to Discord's five-row limit. The normal `send()` path also accepts `metadata["discord_webhook"]` with `id`, `token`, and optional `username` / `avatar_url` / `thread_id` / `wait` to route an outbound message through a Discord webhook instead of the bot token path. That shortcut is intentionally limited to normal text/embed/component delivery today; native reply references and Discord polls still fail closed on the webhook route.
- **Voice messages**: pass `metadata["discord_voice"]` through the normal `send()` path to route a channel/DM reply as a native Discord voice note. The payload accepts `audio_bytes`, `audio_base64`, or local `audio_path` / `path`, plus `duration_secs` and optional `waveform` / `silent`. When that send happens in Discord interaction context, ClawLite now reuses the source `message_id` as a native reply anchor when available, still fails closed for unsupported `discord_ephemeral` or `discord_followup` voice-response requests, and now also rejects mixed text/embed/component/webhook/modal/poll payloads instead of silently dropping that extra outbound context.
- The Discord voice-note upload path now reuses the adapter's normal `429` / `Retry-After` retry discipline for attachment reservation and binary upload, instead of treating voice uploads as a one-shot side path.
- **Modal forms**: pass `metadata["discord_modal"]` with `title`, `fields`, and optional `trigger_label` / `trigger_style`. ClawLite appends a trigger button to the outbound message and opens the modal on click; this slice supports Discord text-input modal fields.
- **Thread creation**: use `await channel.create_thread(channel_id=..., name=..., message_id=...)`. Omit `message_id` for a standalone (forum-style) thread. Returns the new thread ID or empty string on failure. `auto_archive_duration` defaults to 1440 minutes.
- Discord-specific send retry knobs exist in code but are not part of the typed schema.
- For proactive sends, prefer typed targets: `channel:<discord_channel_id>` for guild channels/threads and `user:<discord_user_id>` for DMs.
- Bare numeric Discord targets are ambiguous. ClawLite now tries them as channel IDs first and only falls back to DM creation if Discord returns `404`.
- Session routing is now explicit: DMs resolve to `discord:dm:<user_id>`, while guild traffic resolves to `discord:guild:<guild_id>:channel:<channel_id>`.
- Bound Discord channels keep replying to the live thread/channel while reusing the focused session key for engine context. The original route is preserved in metadata as `discord_source_session_key`.
- Automatic replies to inbound Discord messages still route back to the originating `channel_id` and preserve native reply references when Discord provides a `message_id`. Use `reply_to_mode=off|first|all` to control whether ClawLite replies to every Discord chunk, only the first outbound message in a turn, or never attaches a native reply reference.
- When inbound traffic arrived via a Discord interaction, normal agent replies now reuse the deferred interaction response path instead of always posting a second channel message. Ephemeral interaction replies now go through the Discord follow-up webhook route so `flags=64` is applied on a valid send path instead of being ignored on a late `@original` edit, the Discord adapter now also caches `application_id` from live interaction payloads so replies still work even if the gateway has not seen `READY` first, built-in operator/approval interactions now ACK ephemerally up front instead of creating a public deferred placeholder first, callers can now opt into a non-ephemeral follow-up message with `metadata["discord_followup"]` when they want a second interaction response instead of editing `@original`, and both deferred `@original` edits plus follow-up webhook sends now reuse the adapter's normal `429` / `Retry-After` retry handling.
- Deferred Discord interaction replies now also stream through the native `@original` response path when the runtime uses `stream_run()`, so slash/component turns can render progressive edits instead of waiting for a second non-streamed channel message. That streaming slice stays fail-closed: explicit `discord_followup` interaction sends still use the normal non-streaming follow-up path.
- Approval-gated tool calls and self-evolution reviews now reuse Discord buttons/components so operators can approve or reject directly from the same conversation flow.
- Inbound Discord interactions now distinguish buttons, string/user/role/channel/mentionable selects, and modal submits. Selects preserve selected values/labels in emitted metadata, while modal submits are routed as fresh inbound turns with compact field text plus `modal_field_ids` / `modal_field_labels`. Outbound `discord_modal` messages register a namespaced trigger button and open the modal with a native Discord interaction callback instead of leaking that trigger click back into the agent loop.
- Static presence is now supported with `status` plus optional `activity` / `activity_type` / `activity_url`, following the same basic contract documented by OpenClaw.
- `auto_presence` is now available as a lightweight runtime loop. It maps healthy Discord transport to `online`, degraded transport to `idle`, and unavailable/exhausted transport to `dnd`, with optional custom text overrides. It only pushes `op 3` presence updates when the effective state changes or the minimum update interval allows it.
- If you want the agent to build or reorganize a server, the bot also needs Discord permissions like `View Channels`, `Send Messages`, `Manage Channels`, and `Manage Roles`.
- Server-building requests are now handled through the `discord_admin` tool, which can list guilds/channels/roles, create roles, create channels/categories, and apply a full layout template.

Focus commands:

```text
/focus discord:guild:123456789012345678:channel:222222222222222222
/unfocus
```

These commands are intercepted before the message reaches the agent runtime. They update the Discord channel/thread binding store and reply back ephemerally when the command came from a native Discord interaction.

Operator commands:

```text
/discord-status
/discord-refresh
/discord-presence
/discord-presence-refresh
```

These are also intercepted before the agent loop. `discord-status` returns the live transport/policy snapshot for the running Discord channel instance, `discord-refresh` triggers the same transport restart path exposed by the operator surface, `discord-presence` shows the effective static/auto presence state, and `discord-presence-refresh` forces an immediate `op 3` status update when the gateway is connected.

## Email

Email is the built-in mailbox adapter.

Important config keys:

- `imap_host`, `imap_port`, `imap_user`, `imap_password`, `imap_use_ssl`
- `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `smtp_use_ssl`, `smtp_use_starttls`
- `poll_interval_s`
- `mailbox`
- `mark_seen`
- `dedupe_state_path`
- `max_body_chars`
- `from_address`
- `allow_from`

Example config:

```json
{
  "channels": {
    "email": {
      "enabled": true,
      "allow_from": ["user@example.com"],
      "imap_host": "imap.example.com",
      "imap_port": 993,
      "imap_user": "bot@example.com",
      "imap_password": "imap-password",
      "imap_use_ssl": true,
      "smtp_host": "smtp.example.com",
      "smtp_port": 465,
      "smtp_user": "bot@example.com",
      "smtp_password": "smtp-password",
      "smtp_use_ssl": true,
      "smtp_use_starttls": true,
      "poll_interval_s": 30.0,
      "mailbox": "INBOX",
      "mark_seen": true,
      "dedupe_state_path": "",
      "max_body_chars": 12000,
      "from_address": "bot@example.com"
    }
  }
}
```

Notes:

- In normal runtime, ClawLite expects IMAP receive config so it can poll inbound mail.
- Outbound send/reply additionally requires the SMTP fields.
- `allow_from` matches exact sender email addresses.
- Email attachments are not downloaded or sent today.

## WhatsApp

WhatsApp is split across two surfaces:

- Inbound: the gateway webhook route.
- Outbound: an HTTP bridge that accepts POSTs to `/send`.

Important config keys:

- `bridge_url`
- `bridge_token`
- `timeout_s`
- `webhook_path`
- `webhook_secret`
- `allow_from`
- `send_retry_attempts`
- `send_retry_after_default_s`
- `typing_enabled`
- `typing_interval_s`

Example config:

```json
{
  "channels": {
    "whatsapp": {
      "enabled": true,
      "allow_from": ["5511999999999"],
      "bridge_url": "ws://localhost:3001",
      "bridge_token": "bridge-secret",
      "timeout_s": 10.0,
      "webhook_path": "/api/webhooks/whatsapp",
      "webhook_secret": "webhook-secret"
    }
  }
}
```

Notes:

- `bridge_url` may be `ws://` or `wss://`; ClawLite normalizes it to `http(s)://.../send` for outbound calls.
- Inbound webhook auth requires `webhook_secret`; the gateway accepts it through `X-Webhook-Secret` or a bearer token.
- Outbound sends retry on `429`, bridge 5xx, and transport failures using `send_retry_*`.
- Typing keepalive uses the bridge `/typing` endpoint when `typing_enabled` is true.
- Media arrives as placeholders such as `[whatsapp image]`; ClawLite does not download media files.

## Slack

Slack supports inbound Socket Mode plus outbound delivery.

Important config keys:

- `bot_token`
- `app_token`
- `api_base`
- `timeout_s`
- `allow_from`
- `send_retry_attempts`
- `send_retry_after_default_s`
- `socket_mode_enabled`
- `socket_backoff_base_s`
- `socket_backoff_max_s`
- `typing_enabled`
- `working_indicator_enabled`
- `working_indicator_emoji`

Example config:

```json
{
  "channels": {
    "slack": {
      "enabled": true,
      "bot_token": "xoxb-test",
      "app_token": "xapp-test",
      "api_base": "https://slack.com/api",
      "timeout_s": 10.0,
      "allow_from": []
    }
  }
}
```

Notes:

- Outbound sends use `chat.postMessage` with rate-limit retry handling.
- Inbound uses Slack Socket Mode when `app_token` is present and `socket_mode_enabled` is true.
- The working indicator adds and later removes a reaction on the latest inbound message for that channel.
- `validate channels` still treats `bot_token` as the required minimum; `app_token` is required only for inbound Socket Mode.

## IRC

IRC is a minimal but functional asyncio adapter.

Important config keys:

- `host`
- `port`
- `nick`
- `username`
- `realname`
- `channels_to_join`
- `use_ssl`
- `connect_timeout_s`

Example config:

```json
{
  "channels": {
    "irc": {
      "enabled": true,
      "host": "irc.libera.chat",
      "port": 6697,
      "nick": "clawlite-bot",
      "channels_to_join": ["#clawlite"],
      "use_ssl": true
    }
  }
}
```

Notes:

- The current implementation supports connect, JOIN, PING/PONG, inbound `PRIVMSG`, outbound `PRIVMSG`, and clean shutdown.
- It does not yet implement SASL, nickname recovery, CTCP helpers, or reconnect persistence.

## Placeholder Channels

These names are registered in the channel manager, but they are passive stubs and not production-ready adapters:

- `signal`
- `googlechat`
- `matrix`
- `imessage`
- `dingtalk`
- `feishu`
- `mochat`
- `qq`

If you add them as `channels.<name>.enabled = true`, ClawLite can instantiate them, but `send()` still raises `<name>_not_implemented`.
