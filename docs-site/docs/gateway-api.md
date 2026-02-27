# Gateway API

## Endpoints

### `GET /health`
Health probe.

### `GET /dashboard`
Web dashboard.

### `GET /api/status`
Requires `Authorization: Bearer <token>`.

### `WS /ws?token=<token>`
WebSocket interface.

## Run gateway

```bash
clawlite gateway --host 0.0.0.0 --port 8787
```
