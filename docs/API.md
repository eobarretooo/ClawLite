# API (Gateway)

Base URL padrão: `http://127.0.0.1:8787`

## `GET /`

Entrypoint leve do gateway (HTML estático e determinístico) com visão rápida dos endpoints disponíveis.

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

Alias compatível: `POST /api/message` (mesma request/response e mesma política de autenticação).

## `GET /v1/status`

Estado do control-plane do gateway.

Campos de contrato estavel:
- `contract_version`: versao do contrato HTTP do gateway.
- `server_time`: timestamp UTC ISO-8601 gerado no servidor.

Alias compatível: `GET /api/status` (mesmo payload e mesma política de autenticação).

## `GET /v1/diagnostics`

Snapshot operacional do gateway para debug e operacao.

Campos baseline de contrato:
- `generated_at`: timestamp UTC ISO-8601 da geracao do snapshot.
- `uptime_s`: uptime do processo do gateway em segundos.
- `contract_version`: versao estavel do contrato HTTP do gateway.

Alias compatível: `GET /api/diagnostics` (mesmo payload e mesma política de autenticação).

## `GET /api/token`

Diagnóstico de autenticação do gateway.
- Nunca retorna token em texto puro.
- Retorna apenas estado (`token_configured`) e versão mascarada determinística (`token_masked`).
- Segue a mesma política de autenticação dos endpoints de control-plane.

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

Alias compatível: `WS /ws` (mesmo comportamento, incluindo autenticação).

## Envelope de erro HTTP

Para erros HTTP, o gateway retorna envelope estavel com:
- `error`
- `status`
- `code` (quando `error` for string, `code` repete esse valor)
