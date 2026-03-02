# Gateway API

Base URL padrão: `http://127.0.0.1:8787`

## Iniciar

```bash
clawlite start --host 127.0.0.1 --port 8787
```

## Endpoints principais

- `GET /health`
- `POST /v1/chat`
- `POST /v1/cron/add`
- `GET /v1/cron/list?session_id=...`
- `DELETE /v1/cron/{job_id}`
- `WS /v1/ws`

## Exemplo de chat

```bash
curl -sS http://127.0.0.1:8787/v1/chat \
  -H 'content-type: application/json' \
  -d '{"session_id":"cli:api","text":"resuma o estado do projeto"}'
```

## Exemplo de cron

```bash
curl -sS http://127.0.0.1:8787/v1/cron/add \
  -H 'content-type: application/json' \
  -d '{"session_id":"cli:ops","expression":"every 300","prompt":"status rapido"}'
```

➡️ Próxima página: [Operações](/operations)
