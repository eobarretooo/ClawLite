# Guia de configuração

## Arquivo de config

O arquivo principal fica em `~/.clawlite/config.json`.

Exemplo completo:

- `docs/config.example.json`

## UX atual de configuração

### 1) Onboarding wizard guiado

```bash
clawlite onboarding
```

Fluxo por etapas com barra de progresso, salvamento automático e resumo final.

### 2) Configure estilo OpenClaw

```bash
clawlite configure
```

Menu seccional com autosave: **Model, Channels, Skills, Hooks, Gateway, Web Tools, Language, Security** + preview JSON final.

## Operação local

### Doctor / Status / Start

```bash
clawlite doctor
clawlite status
clawlite start --port 8787
```

- `doctor`: valida ambiente, dependências e config mínima.
- `status`: mostra estado de gateway/workers/cron/reddit.
- `start`: sobe o gateway HTTP/WebSocket (atalho para `clawlite gateway`).

## Learning stats (telemetria local)

```bash
clawlite stats --period all
clawlite stats --period month --skill github
```

Métricas: total de tasks, taxa de sucesso, tempo médio, tokens, streak, top skills e preferências aprendidas.

## Reddit (web tool + automação)

```bash
clawlite reddit status
clawlite reddit auth-url
clawlite reddit exchange-code "SEU_CODE"
clawlite reddit post-milestone --title "ClawLite v0.4.0" --text "..."
clawlite reddit monitor-once
```

Guia detalhado: `docs/REDDIT_INTEGRATION.md`

## Blocos avançados de runtime

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
