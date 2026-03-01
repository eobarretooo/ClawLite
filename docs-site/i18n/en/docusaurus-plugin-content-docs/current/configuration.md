# Configuration

## Config file

Main file path: `~/.clawlite/config.json`.

Complete example:

- `docs/config.example.json`

## Setup helpers

```bash
clawlite onboarding
clawlite configure
```

## New runtime blocks

### 1) Offline mode with Ollama fallback

```json
"offline_mode": {
  "enabled": true,
  "auto_fallback_to_ollama": true,
  "connectivity_timeout_sec": 1.5
},
"model_fallback": ["openrouter/auto", "ollama/llama3.1:8b"],
"ollama": {
  "model": "llama3.1:8b"
}
```

### 2) Conversation cron jobs

```bash
clawlite cron list
clawlite cron add --channel telegram --chat-id 123 --label general --name heartbeat --text "ping" --every-seconds 300
clawlite cron run
clawlite cron remove 1
```

### 3) Smart notifications (priority + dedupe)

```json
"notifications": {
  "enabled": true,
  "dedupe_window_seconds": 300
}
```

Runtime priorities:

- `high`: failures (provider/cron)
- `normal`: offline fallback events
- `low`: successful cron enqueue events

### 4) Battery mode with configurable throttling

```json
"battery_mode": {
  "enabled": false,
  "throttle_seconds": 6.0
}
```

CLI:

```bash
clawlite battery status
clawlite battery set --enabled true --throttle-seconds 8
```
