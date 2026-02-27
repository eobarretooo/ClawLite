# Guia de configuração

## Arquivo de config

O arquivo principal fica em `~/.clawlite/config.json`.

Exemplo completo:

- `docs/config.example.json`

## Onboarding

```bash
clawlite onboarding
```

## Menu interativo

```bash
clawlite configure
```

## Blocos novos

### 1) Offline automático com Ollama

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

### 2) Cron por conversa

```bash
clawlite cron list
clawlite cron add --channel telegram --chat-id 123 --label general --name heartbeat --text "ping" --every-seconds 300
clawlite cron run
clawlite cron remove 1
```

### 3) Notificações (prioridade + dedupe)

```json
"notifications": {
  "enabled": true,
  "dedupe_window_seconds": 300
}
```

Prioridades usadas no runtime:

- `high`: falhas (provedor/cron)
- `normal`: fallback offline
- `low`: sucesso de cron enfileirado

### 4) Modo bateria com throttling

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
