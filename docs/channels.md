# Channels

ClawLite can send and receive messages through multiple channel adapters. Today, Telegram is the most complete adapter. Discord, Email, and WhatsApp are usable. Slack is outbound-only. Several extra channel names are registered as placeholders but are not implemented yet.

## Quick Start

1. Add your channel config to `~/.clawlite/config.json`.
2. Start the gateway with `clawlite gateway`.
3. Run `clawlite validate channels` for static checks.
4. For Telegram tokens, you can also run `clawlite validate preflight --telegram-live`.
5. Inspect live channel state in `/v1/diagnostics` under `channels`, `channels_dispatcher`, `channels_delivery`, `channels_inbound`, and `channels_recovery`.

Quickstart note: `clawlite configure --flow quickstart` only offers Telegram. Discord, Email, WhatsApp, and Slack are manual config today.

## Channel Matrix

| Channel | Inbound | Outbound | Status | Notes |
| --- | --- | --- | --- | --- |
| Telegram | Yes | Yes | Most complete | Polling and webhook, pairing, reactions, topics, typing keepalive, voice/audio transcription |
| Discord | Yes | Yes | Usable | Gateway websocket inbound, REST outbound, attachments become text placeholders |
| Email | Yes | Yes | Usable | IMAP polling inbound plus SMTP replies |
| WhatsApp | Yes | Yes | Usable | Inbound webhook plus outbound bridge `/send` |
| Slack | No | Yes | Send-only | Outbound `chat.postMessage`; no inbound event loop yet |
| Signal | No | No | Placeholder | Passive stub only |
| Google Chat | No | No | Placeholder | Passive stub only |
| Matrix | No | No | Placeholder | Passive stub only |
| IRC | No | No | Placeholder | Passive stub only |
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
- Voice/audio transcription through a Groq-compatible OpenAI endpoint.
- Reaction forwarding and inline keyboard callbacks.
- Telegram-specific message actions through the `message` tool: reply, edit, delete, react, and create topic.

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
- `allow_from`

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
      "gateway_intents": 37377,
      "gateway_backoff_base_s": 2.0,
      "gateway_backoff_max_s": 30.0,
      "typing_enabled": true,
      "typing_interval_s": 8.0,
      "allow_from": ["123456789012345678", "@ownername"]
    }
  }
}
```

Notes:

- `allow_from` can contain user IDs or usernames.
- Bot/self messages are ignored.
- Attachments are surfaced as placeholders in the forwarded text; ClawLite does not download them.
- Discord-specific send retry knobs exist in code but are not part of the typed schema.
- For proactive sends, prefer typed targets: `channel:<discord_channel_id>` for guild channels/threads and `user:<discord_user_id>` for DMs.
- Bare numeric Discord targets are ambiguous. ClawLite now tries them as channel IDs first and only falls back to DM creation if Discord returns `404`.
- Automatic replies to inbound Discord messages now route back to the originating `channel_id` and preserve native reply references when Discord provides a `message_id`.
- If you want the agent to build or reorganize a server, the bot also needs Discord permissions like `View Channels`, `Send Messages`, `Manage Channels`, and `Manage Roles`.
- Server-building requests are now handled through the `discord_admin` tool, which can list guilds/channels/roles, create roles, create channels/categories, and apply a full layout template.

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
- Media arrives as placeholders such as `[whatsapp image]`; ClawLite does not download media files.

## Slack

Slack is currently outbound-only.

Important config keys:

- `bot_token`
- `app_token`
- `api_base`
- `timeout_s`
- `allow_from`

Example config:

```json
{
  "channels": {
    "slack": {
      "enabled": true,
      "bot_token": "xoxb-test",
      "app_token": "",
      "api_base": "https://slack.com/api",
      "timeout_s": 10.0,
      "allow_from": []
    }
  }
}
```

Notes:

- Outbound sends use `chat.postMessage` with rate-limit retry handling.
- There is no inbound event or Socket Mode worker yet.
- `validate channels` warns when `app_token` is empty, but runtime outbound send only needs `bot_token`.

## Placeholder Channels

These names are registered in the channel manager, but they are passive stubs and not production-ready adapters:

- `signal`
- `googlechat`
- `matrix`
- `irc`
- `imessage`
- `dingtalk`
- `feishu`
- `mochat`
- `qq`

If you add them as `channels.<name>.enabled = true`, ClawLite can instantiate them, but `send()` still raises `<name>_not_implemented`.
