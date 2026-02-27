# Gateway API

## Subir gateway

```bash
clawlite gateway --host 0.0.0.0 --port 8787
```

## Endpoints

- `GET /health`
- `GET /dashboard`
- `GET /api/status` (Bearer token)
- `WS /ws?token=<token>`

## Auth

Use token do gateway no header:

```text
Authorization: Bearer <token>
```
