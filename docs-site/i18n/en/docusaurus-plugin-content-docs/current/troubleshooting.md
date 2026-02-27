---
title: Troubleshooting
---

## Skill syntax errors (`IndentationError`)

If skills like `aws`, `ssh`, or `supabase` fail to import, run:

```bash
python -m compileall -q clawlite/skills
```

Fix the indentation reported by Python and run the command again.

## `agents`: worker not found

Error:
```text
❌ Falha no comando 'agents': worker <id> não encontrado
```

Fix:
```bash
clawlite agents register --channel telegram --chat-id 123 --label general --cmd 'clawlite run "{text}"'
clawlite agents list
clawlite agents start <id>
```

## `cron`: invalid interval

Error:
```text
❌ Falha no comando 'cron': interval_seconds deve ser maior que 0
```

Fix:
```bash
clawlite cron add --channel telegram --chat-id 123 --label general --name heartbeat --text "ping" --every-seconds 60
```

## `skill`: marketplace/publish failure

For `skill install/update/publish` failures, validate:
- `--index-url`
- `--allow-host`
- `--manifest-path`
- `--allow-file-urls` (local trusted scenarios only)

## `auth`: not authenticated

If `clawlite auth status` shows `não autenticado`, run:

```bash
clawlite auth login openai
clawlite auth status
```

## `battery`: unexpected throttle values

Inspect current config:
```bash
clawlite battery status
```

Update mode:
```bash
clawlite battery set --enabled true --throttle-seconds 8
```

## Dashboard/Gateway token errors

Common responses:
- `401 Missing bearer token`
- `403 Invalid token`

Use `gateway.token` from `~/.clawlite/config.json`:

```text
Authorization: Bearer <token>
```
