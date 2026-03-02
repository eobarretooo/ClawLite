# API (Gateway)

Base URL padrão: `http://127.0.0.1:8787`

## `GET /health`

Retorna status geral do runtime:
- `ok`
- `channels`
- `queue`

## `POST /v1/chat`

Request:

```json
{
  "session_id": "telegram:123",
  "text": "me lembra de beber agua"
}
```

Response:

```json
{
  "text": "...",
  "model": "gemini-2.5-flash"
}
```

## `POST /v1/cron/add`

Cria job agendado:

```json
{
  "session_id": "telegram:123",
  "expression": "every 120",
  "prompt": "me lembra de alongar"
}
```

## `GET /v1/cron/list?session_id=...`

Lista jobs da sessão.

## `DELETE /v1/cron/{job_id}`

Remove job.

## `WS /v1/ws`

Canal websocket para chat em tempo real.
Payload por mensagem:

```json
{"session_id":"cli:ws","text":"oi"}
```
