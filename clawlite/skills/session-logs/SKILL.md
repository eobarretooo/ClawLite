---
name: session-logs
description: Search and inspect ClawLite JSONL session logs for prior conversation context.
metadata: {"clawlite":{"emoji":"📜"}}
script: session_logs
---

# Session logs

Use this skill when the user asks about older conversations, earlier decisions, or historical prompts/responses.

## Default location

`~/.clawlite/state/sessions/`

Each session is stored as `<session-id>.jsonl`.

## JSONL fields (ClawLite)

- `session_id`
- `role` (`system`, `user`, `assistant`, `tool`)
- `content`
- `ts` (ISO timestamp)
- `metadata` (object)

## Common queries

List session files:

```bash
ls -1 ~/.clawlite/state/sessions/*.jsonl
```

Search for a keyword across all sessions:

```bash
rg -i "keyword" ~/.clawlite/state/sessions/*.jsonl
```

Read user messages from one session:

```bash
jq -r 'select(.role=="user") | .ts + " | " + .content' ~/.clawlite/state/sessions/<session-id>.jsonl
```

Read assistant messages with metadata:

```bash
jq -r 'select(.role=="assistant") | {ts, content, metadata}' ~/.clawlite/state/sessions/<session-id>.jsonl
```

Filter by metadata key/value:

```bash
jq -r 'select(.metadata.channel=="telegram") | .ts + " | " + .role + " | " + .content' ~/.clawlite/state/sessions/<session-id>.jsonl
```

Count messages per role in one session:

```bash
jq -r '.role' ~/.clawlite/state/sessions/<session-id>.jsonl | sort | uniq -c
```
