# Gateway API

O ClawLite pode operar como servidor com autenticação por token.

## Subir gateway

```bash
clawlite gateway --host 0.0.0.0 --port 8787
```

## Endpoints HTTP

### `GET /health`
Retorna status de saúde e uptime.

**Resposta exemplo**

```json
{
  "ok": true,
  "service": "clawlite-gateway",
  "uptime_seconds": 42,
  "connections": 1
}
```

### `GET /dashboard`
Dashboard web básico para inspeção.

### `GET /api/status`
Protegido por bearer token.

Header:

```text
Authorization: Bearer <gateway-token>
```

## WebSocket

### `WS /ws?token=<gateway-token>`

Mensagens suportadas:

- `{"type":"ping"}` → `{"type":"pong",...}`
- payloads genéricos → `{"type":"echo",...}`

## Segurança mínima recomendada

- nunca expor token em público
- usar proxy reverso em produção
- restringir origem/rede quando possível
